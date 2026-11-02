import copy
import math
import re
from datetime import date
from decimal import Decimal, InvalidOperation

from .models import AnalysisDraft, AnswerDraft, ServiceError
from .parser import coverage


def chunks(pages: list[dict]) -> list[dict]:
    result = []
    for page in pages:
        text = page["text"]
        for start in range(0, len(text), 1_880):
            end = min(len(text), start + 2_000)
            if not text[start:end].strip():
                continue
            result.append({"id": f"cit_{page['page_number']}_{start}_{end}", "page_number": page["page_number"],
                           "start": start, "end": end, "quote": text[start:end], "embedding": None})
    return result


def citation_map(document_id: str, pages: list[dict], passages: list[dict]) -> dict:
    mapping, page_map = {}, {page["page_number"]: page for page in pages}
    for passage in passages:
        page = page_map.get(passage["page_number"])
        if not page or page["status"] == "unreadable" or not 0 <= passage["start"] < passage["end"] <= len(page["text"]) or page["text"][passage["start"]:passage["end"]] != passage["quote"]:
            raise ServiceError("evidence_validation_failed", "Source evidence could not be validated.")
        boxes = [box for span in page["layout_spans"] if span["start"] < passage["end"] and span["end"] > passage["start"] for box in span["boxes"]]
        mapping[passage["id"]] = {key: passage[key] for key in ("id", "page_number", "start", "end", "quote")}
        mapping[passage["id"]].update(document_id=document_id, boxes=boxes)
    return mapping


def prompt_passages(passages: list[dict]) -> list[dict]:
    return [{"citation_id": passage["id"], "page": passage["page_number"], "text": passage["quote"]} for passage in passages]


def validate_statements(value: dict, citations: dict, allow_empty: bool = False) -> None:
    if "text" in value and "citation_ids" in value:
        ids = value["citation_ids"]
        if (not ids and not allow_empty) or any(identifier not in citations for identifier in ids):
            raise ServiceError("evidence_validation_failed", "The explanation contained an unsupported source reference.")
    for child in value.values():
        if isinstance(child, list):
            for item in child:
                if isinstance(item, dict):
                    validate_statements(item, citations, allow_empty)


def validate_facts(draft: dict, mapping: dict) -> None:
    for deadline in draft.get("deadlines", []):
        if deadline["kind"] != "absolute" and deadline["date"] is not None:
            raise ServiceError("evidence_validation_failed", "A relative deadline was incorrectly turned into a date.")
        if deadline["date"]:
            try:
                parsed = date.fromisoformat(deadline["date"])
            except ValueError:
                raise ServiceError("evidence_validation_failed", "The deadline date is invalid.") from None
            source = " ".join(mapping[key]["quote"] for key in deadline["citation_ids"])
            forms = [parsed.isoformat(), parsed.strftime("%B %d, %Y"), parsed.strftime("%d %B %Y"), parsed.strftime("%m/%d/%Y")]
            source = re.sub(r"\b0(\d)\b", r"\1", source.casefold())
            if not any(re.sub(r"\b0(\d)\b", r"\1", form.casefold()) in source for form in forms):
                raise ServiceError("evidence_validation_failed", "The date was not explicitly supported by its source.")
    for fee in draft.get("fees", []):
        source = " ".join(mapping[key]["quote"] for key in fee["citation_ids"])
        if fee["currency"] and fee["currency"] not in source.upper():
            fee["currency"] = None
        if fee["amount"] is not None:
            try:
                amount = Decimal(fee["amount"])
                source_amounts = [Decimal(value.replace(",", "")) for value in re.findall(r"\d[\d,]*(?:\.\d+)?", source)]
                if not amount.is_finite() or amount not in source_amounts:
                    raise InvalidOperation()
            except (InvalidOperation, ValueError):
                raise ServiceError("evidence_validation_failed", "The fee was not supported by its source.") from None


def generation(settings, prompt: str) -> dict:
    return {"model_id": settings.chat_model, "prompt_version": prompt, "retrieval_version": "hybrid_v1",
            "extraction_version": "pdfplumber_v1", "schema_version": "2"}


def analyze(document: dict, content: dict, provider, settings) -> dict:
    page_map = {page["page_number"]: page for page in content["pages"]}
    result = {field: [] for field in AnalysisDraft.model_fields}
    mapping, analyzed, budget_hit = {}, set(), False
    # Whole-page batches preserve the meaning of analyzed_pages; no page is silently clipped.
    for batch_number, page in enumerate(content["pages"]):
        if not page["text"]:
            continue
        passages = [item for item in content["chunks"] if item["page_number"] == page["page_number"]]
        local = citation_map(document["id"], content["pages"], passages)
        try:
            draft = provider.structured("Explain this page and extract all explicit requirements, eligibility, fees, deadlines, actions and exceptions. Empty arrays are valid. All factual statements need supplied citation IDs. Do not calculate relative deadlines.", prompt_passages(passages), AnalysisDraft).model_dump()
        except ServiceError as problem:
            if problem.code == "budget_exceeded":
                budget_hit = True
                break
            raise
        validate_statements(draft, local)
        validate_facts(draft, local)
        fact_fields = ("requirements", "eligibility", "fees", "deadlines", "actions")
        old_ids = [fact["id"] for field in fact_fields for fact in draft[field]]
        if len(old_ids) != len(set(old_ids)):
            raise ServiceError("invalid_model_output", "The explanation contained ambiguous requirement references.")
        renamed = {old: f"fact_{batch_number}_{index}" for index, old in enumerate(old_ids)}
        for field in fact_fields:
            for fact in draft[field]:
                fact["id"] = renamed[fact["id"]]
                if "related_fact_ids" in fact:
                    if any(key not in renamed for key in fact["related_fact_ids"]):
                        raise ServiceError("invalid_model_output", "An action referenced a missing requirement.")
                    fact["related_fact_ids"] = [renamed[key] for key in fact["related_fact_ids"]]
        for field in result:
            if field != "not_stated":
                result[field].extend(draft[field])
        mapping.update(local)
        analyzed.add(page["page_number"])
    if not analyzed:
        raise ServiceError("budget_exceeded", "This document cannot be analyzed within the processing budget.")
    cov = copy.deepcopy(content["coverage"])
    cov["analyzed_pages"] = sorted(analyzed)
    warnings = copy.deepcopy(content["warnings"])
    if budget_hit or analyzed != set(cov["readable_pages"]):
        cov["status"] = "partial"
        cov["reasons"] = sorted(set(cov["reasons"] + ["analysis_budget_exceeded"]))
        warnings.append({"code": "analysis_budget_exceeded", "message": "Some pages were not analyzed within this operation's budget.", "page_numbers": sorted(set(cov["readable_pages"]) - analyzed)})
    result["not_stated"] = [field for field in ("requirements", "eligibility", "fees", "deadlines") if not result[field]] if cov["status"] == "complete" else []
    if cov["status"] == "partial":
        result["details_to_check"].append({"text": "Some source content could not be fully read or analyzed. Additional requirements, fees or deadlines may be present.", "citation_ids": []})
    used = {key for field, items in result.items() if field != "not_stated" for item in items if isinstance(item, dict) for key in item.get("citation_ids", [])}
    result.update(type="analysis", language="en", coverage=cov, citations=[mapping[key] for key in sorted(used)],
                  warnings=warnings, generation=generation(settings, "explain_v1"))
    return result


def retrieve(question: str, content: dict, provider) -> list[dict]:
    words = set(re.findall(r"\w+", question.casefold()))
    query_vector = provider.embeddings([question])[0]
    def score(chunk):
        text_words = set(re.findall(r"\w+", chunk["quote"].casefold()))
        lexical = len(words & text_words) / max(1, len(words))
        vector = chunk.get("embedding")
        semantic = 0
        if vector and len(vector) == len(query_vector):
            denominator = math.sqrt(sum(v*v for v in vector) * sum(v*v for v in query_vector))
            semantic = sum(a*b for a,b in zip(vector,query_vector)) / denominator if denominator else 0
        return lexical + semantic
    ranked = sorted(content["chunks"], key=score, reverse=True)
    selected, used = [], 0
    for passage in ranked:
        size = len(passage["quote"].encode("utf-8"))
        if used + size > 8_000:
            continue
        selected.append(passage)
        used += size
        if len(selected) == 6:
            break
    return selected


def answer(document: dict, content: dict, question: str, provider, settings) -> dict:
    passages = retrieve(question, content, provider)
    mapping = citation_map(document["id"], content["pages"], passages)
    draft = provider.structured("Answer only from this document evidence. Use insufficient_evidence when unsupported, conflicting_evidence for incompatible clauses, and answered otherwise. Preserve uncertainty and cite every factual statement.", prompt_passages(passages), AnswerDraft, question).model_dump()
    if draft["status"] == "insufficient_evidence":
        draft["statements"] = [{"text": "The readable evidence does not provide enough information to answer. Check the source and ask the issuing office; unreadable content may contain the answer." if content["coverage"]["status"] == "partial" else "I couldn't establish this from the document. Check with the issuing office.", "citation_ids": []}]
    else:
        validate_statements(draft, mapping)
        used = {key for statement in draft["statements"] for key in statement["citation_ids"]}
        if not used or (draft["status"] == "conflicting_evidence" and len(used) < 2):
            raise ServiceError("evidence_validation_failed", "The answer did not include enough source evidence.")
    used = {key for statement in draft["statements"] for key in statement["citation_ids"]}
    cov = copy.deepcopy(content["coverage"])
    cov["analyzed_pages"] = sorted({passage["page_number"] for passage in passages})
    draft.update(type="answer", language="en", citations=[mapping[key] for key in sorted(used)], coverage=cov,
                 warnings=content["warnings"], generation=generation(settings, "ask_v1"))
    return draft
