import importlib.util
import os
import time
from pathlib import Path

from aight_api.jobs import execute, source_directory
from aight_api.maintenance import sweep
from aight_api.models import AnalysisDraft, AnswerDraft
from aight_api.parser import parse_document
from aight_api.store import packed
from aight_api.store import identity
from conftest import import_text, session


class SyntheticProvider:
    """Deterministic test double. Never used by the running application."""
    def embeddings(self, texts):
        return [[1.0, 0.0] for _ in texts]

    def structured(self, task, passages, model, question=""):
        evidence = passages[0]["citation_id"]
        if model is AnswerDraft:
            return model(status="answered", statements=[{"text": "The GWA condition is 2.00 or better.", "citation_ids": [evidence]}])
        value = {field: [] for field in AnalysisDraft.model_fields}
        value["meaning"] = [{"text": "The GWA condition is 2.00 or better.", "citation_ids": [evidence]}]
        value["eligibility"] = [{"id": "gwa", "text": "GWA must not exceed 2.00.", "citation_ids": [evidence]}]
        return model(**value)


def run(client, store, current, headers, accepted):
    execute(current["session_id"], accepted["operation_id"], store=store, provider=SyntheticProvider())
    response = client.get(f"/api/v1/operations/{accepted['operation_id']}", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["state"] == "succeeded", response.text
    return response.json()["result"]


def test_complete_text_analysis_question_and_delete(environment):
    client, store = environment
    current, headers = session(client)
    accepted = import_text(client, headers, "GWA must not exceed 2.00.\nSynthetic source only.")
    result = run(client, store, current, headers, accepted)
    assert result["warnings"] == [] and result["coverage"]["partial_pages"] == []
    docid = accepted["document_id"]
    assert client.get(f"/api/v1/documents/{docid}/pages/1", headers=headers).json()["layout_spans"] == []
    assert len(client.get(f"/api/v1/documents/{docid}/pages", headers=headers).json()) == 1
    assert client.get(f"/api/v1/documents/{docid}/source", headers=headers).text.startswith("GWA")
    for suffix, payload in [("analyses", {"language": "en"}), ("questions", {"language": "en", "question": "What is the GWA condition?"})]:
        accepted = client.post(f"/api/v1/documents/{docid}/{suffix}", headers={**headers, "Idempotency-Key": "synthetic-" + suffix + "-0001"}, json=payload).json()
        result = run(client, store, current, headers, accepted)
        assert result["citations"][0]["quote"].startswith("GWA")
        assert result["citations"][0]["boxes"] == []
    directory = source_directory(store.settings.data_dir, current["session_id"], docid)
    client.delete(f"/api/v1/documents/{docid}", headers=headers)
    assert sweep(store)["removed_documents"] == 1
    assert not directory.exists()
    assert store.queue.get_job_ids() == []
    # A worker that crashed just after staging must not extend private retention.
    candidate = store.key(current["session_id"], f"doc:{docid}:candidate:late")
    store.redis.set(candidate, packed({"private": "synthetic"}), ex=60)
    sweep(store)
    assert not store.redis.exists(candidate)


def test_end_session_cleans_files_content_operations_and_jobs(environment):
    client, store = environment
    current, headers = session(client)
    accepted = import_text(client, headers)
    run(client, store, current, headers, accepted)
    assert client.delete("/api/v1/sessions/current", headers=headers).status_code == 202
    sweep(store)
    assert not list(store.settings.data_dir.glob("ses_*/doc_*"))
    assert not list(store.redis.scan_iter(match=store.key(current["session_id"], "doc:*")))
    assert not list(store.redis.scan_iter(match=store.key(current["session_id"], "op:*")))


def test_abandoned_staging_is_cleaned_even_with_broken_manifest(environment):
    client, store = environment
    current, _ = session(client)
    directory = source_directory(store.settings.data_dir, current["session_id"], identity("doc"))
    directory.mkdir(parents=True)
    (directory / "source.txt").write_text("Synthetic abandoned input")
    (directory / "manifest.json").write_text("{interrupted write")
    past = time.time() - 61
    os.utime(directory, (past, past))
    assert sweep(store)["removed_documents"] == 1
    assert not directory.exists()


def test_actual_pdf_extraction_and_codepoint_boxes(tmp_path):
    spec = importlib.util.spec_from_file_location("demo", Path(__file__).parents[2] / "scripts/create_demo.py")
    demo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(demo)
    path = tmp_path / "synthetic.pdf"
    path.write_bytes(demo.pdf_bytes(demo.PAGES))
    pages = parse_document(path)
    assert len(pages) == 5 and all(page["status"] == "readable" for page in pages)
    for page, original in zip(pages, demo.PAGES):
        assert " ".join(page["text"].split()) == " ".join(original.split())
        assert page["layout_spans"]
        for span in page["layout_spans"]:
            assert page["text"][span["start"]:span["end"]]
            assert all(0 <= coordinate <= 1 for box in span["boxes"] for coordinate in box)
