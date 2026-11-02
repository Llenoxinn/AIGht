import pytest
from aight_api.models import AnalysisDraft, ServiceError
from aight_api.parser import coverage, text_page
from aight_api.processing import analyze, chunks, citation_map, validate_facts, validate_statements


def test_unicode_offsets_resolve_exact_quotes():
    page = text_page("Scholarship 😀\ne\u0301ligibility: GWA 2.00 or lower.")
    assert "éligibility" in page["text"]
    for citation in citation_map("doc_synthetic", [page], chunks([page])).values():
        assert page["text"][citation["start"]:citation["end"]] == citation["quote"]


def test_fabricated_and_mismatched_citations_are_rejected():
    page = text_page("GWA must not exceed 2.00.")
    with pytest.raises(ServiceError):
        validate_statements({"text": "You qualify", "citation_ids": ["invented"]}, {})
    evidence = chunks([page])
    evidence[0]["quote"] = "A fabricated fee"
    with pytest.raises(ServiceError):
        citation_map("doc_synthetic", [page], evidence)


def test_relative_deadline_cannot_become_a_calendar_date():
    with pytest.raises(ServiceError):
        validate_facts({"deadlines": [{"kind": "relative", "date": "2026-11-17", "citation_ids": []}]}, {})


def test_partial_page_never_claims_a_missing_deadline():
    page = text_page("Scholarship guidelines")
    page["status"] = "partial"
    page["warnings"] = [{"code": "partial_page", "message": "Image-only body", "page_numbers": [1]}]
    content = {"pages": [page], "chunks": chunks([page]), "coverage": coverage([page]), "warnings": page["warnings"]}
    class Provider:
        def structured(self, *args):
            return AnalysisDraft(**{field: ["deadlines"] if field == "not_stated" else [] for field in AnalysisDraft.model_fields})
    class Config:
        chat_model = "synthetic-model"
    result = analyze({"id": "doc_synthetic"}, content, Provider(), Config())
    assert result["coverage"]["status"] == "partial" and result["coverage"]["partial_pages"] == [1]
    assert result["not_stated"] == []
    assert any("could not" in item["text"] for item in result["details_to_check"])
