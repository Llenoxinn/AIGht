from fastapi.testclient import TestClient
from aight_api.config import Settings
from aight_api.main import create_app
from aight_api.store import packed
from conftest import import_text, session


def test_unconfigured_processing_is_closed():
    with TestClient(create_app(Settings(_env_file=None))) as client:
        assert client.get("/api/v1/capabilities").json()["processing_available"] is False
        assert client.post("/api/v1/sessions", json={"accept_processing": True, "processing_notice_version": "test"}).status_code == 503


def test_replay_recovers_one_accepted_operation(environment):
    client, store = environment
    current, headers = session(client)
    original = import_text(client, headers)
    assert import_text(client, headers) == original
    assert len(store.queue.get_job_ids()) == 1
    record = store.read(store.key(current["session_id"]))
    assert record["documents_created"] == 1 and record["outstanding"] == 1
    response = client.post("/api/v1/documents/text", headers={**headers, "Idempotency-Key": "synthetic-request-0001"}, json={"text": "Different", "title": "Synthetic scholarship"})
    assert response.status_code == 409 and response.json()["error"]["code"] == "idempotency_conflict"


def test_foreign_resources_never_disclose_documents_or_jobs(environment):
    client, _ = environment
    _, owner = session(client)
    _, outsider = session(client)
    value = import_text(client, owner)
    for suffix in ("", "/source", "/pages/1"):
        assert client.get(f"/api/v1/documents/{value['document_id']}{suffix}", headers=outsider).status_code == 404
    assert client.get(f"/api/v1/operations/{value['operation_id']}", headers=outsider).status_code == 404


def test_delete_first_blocks_late_result_and_releases_capacity(environment):
    client, store = environment
    current, headers = session(client)
    value = import_text(client, headers)
    operation, _ = store.claim(current["session_id"], value["operation_id"])
    assert client.delete(f"/api/v1/documents/{value['document_id']}", headers=headers).status_code == 202
    assert not store.finish(current["session_id"], operation, result={"private": "must not return"})
    assert client.get(f"/api/v1/operations/{value['operation_id']}", headers=headers).status_code == 404
    assert store.read(store.key(current["session_id"]))["outstanding"] == 0


def test_complete_first_then_delete_revokes_result(environment):
    client, store = environment
    current, headers = session(client)
    value = import_text(client, headers)
    operation, _ = store.claim(current["session_id"], value["operation_id"])
    assert store.finish(current["session_id"], operation, result={"type": "ingestion"})
    assert not store.finish(current["session_id"], operation, result={"duplicate": True})
    assert client.delete(f"/api/v1/documents/{value['document_id']}", headers=headers).status_code == 202
    assert client.get(f"/api/v1/operations/{value['operation_id']}", headers=headers).status_code == 404
    assert store.read(store.key(current["session_id"]))["outstanding"] == 0


def test_expiry_and_stale_attempt_cannot_publish(environment):
    client, store = environment
    current, headers = session(client)
    value = import_text(client, headers)
    operation, _ = store.claim(current["session_id"], value["operation_id"])
    newer = dict(operation, attempt_token="newer-attempt")
    store.redis.set(store.key(current["session_id"], f"op:{operation['id']}"), packed(newer))
    assert not store.finish(current["session_id"], operation, result={"stale": True})
    store.redis.delete(store.key(current["session_id"]))
    assert not store.finish(current["session_id"], newer, result={"expired": True})
    assert client.get("/api/v1/sessions/current", headers=headers).status_code == 401


def test_invalid_input_is_not_echoed(environment):
    client, _ = environment
    _, headers = session(client)
    response = client.post("/api/v1/documents/text", headers={**headers, "Idempotency-Key": "synthetic-large-0001"}, json={"text": "secret-value" * 10_000})
    assert response.status_code == 422 and "secret-value" not in response.text


def test_changed_notice_requires_fresh_agreement(environment):
    client, _ = environment
    response = client.post("/api/v1/sessions", json={"processing_notice_version": "old", "accept_processing": True})
    assert response.status_code == 409
