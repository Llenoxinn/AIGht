import json
import os
import re
import socket
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

from redis import Redis

from .config import settings
from .models import ServiceError
from .parser import canonical, coverage, text_page
from .processing import analyze, answer, chunks
from .provider import OpenAIProvider
from .store import Store


def source_directory(data_dir: Path, sid: str, docid: str) -> Path:
    if not re.fullmatch(r"ses_[0-9a-f]{32}", sid) or not re.fullmatch(r"doc_[0-9a-f]{32}", docid):
        raise ServiceError("not_found", "This resource is unavailable.", 404)
    root = data_dir.resolve()
    directory = (root / sid / docid).resolve()
    if root not in directory.parents:
        raise ServiceError("not_found", "This resource is unavailable.", 404)
    return directory


def scan_pdf(path: Path, host: str, port: int) -> None:
    try:
        with socket.create_connection((host, port), timeout=10) as connection:
            connection.settimeout(25)
            connection.sendall(b"zINSTREAM\0")
            with path.open("rb") as source:
                while data := source.read(65_536):
                    connection.sendall(struct.pack("!I", len(data)) + data)
            connection.sendall(struct.pack("!I", 0))
            response = bytearray()
            while len(response) < 4_096:
                part = connection.recv(512)
                if not part:
                    break
                response.extend(part)
                if b"\0" in part:
                    break
        if not bytes(response).rstrip(b"\0\n").endswith(b": OK"):
            raise ServiceError("unsafe_file", "The file did not pass the safety scan.")
    except OSError:
        raise ServiceError("dependency_unavailable", "The file safety scanner is unavailable.", 503, True) from None


def isolated_pages(path: Path, config=settings) -> list[dict]:
    parser = Path(__file__).with_name("parser.py")
    safe_environment = {key: os.environ[key] for key in ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP") if key in os.environ}
    safe_environment.update(PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    try:
        with tempfile.TemporaryFile() as output:
            completed = subprocess.run([sys.executable, "-I", str(parser), str(path), str(config.max_pdf_pages), str(config.max_extracted_code_points)],
                                       cwd=path.parent, env=safe_environment, stdout=output, stderr=subprocess.DEVNULL, timeout=config.parser_timeout)
            if completed.returncode != 0 or output.tell() > 8 * 1024 * 1024:
                raise ServiceError("malformed_pdf", "The document could not be safely processed.")
            output.seek(0)
            value = json.load(output)
        if "error" in value:
            raise ServiceError(value["error"], "The document could not be safely read. Try a text-based PDF or paste its text.")
        return value["pages"]
    except subprocess.TimeoutExpired:
        raise ServiceError("processing_timeout", "The document took too long to read.") from None
    except (ValueError, KeyError):
        raise ServiceError("malformed_pdf", "The document could not be read.") from None


def ingest(document: dict, operation: dict, provider, store: Store) -> tuple[dict, dict, str]:
    directory = source_directory(store.settings.data_dir, document["session_id"], document["id"])
    source = directory / ("source.pdf" if document["input_type"] == "pdf" else "source.txt")
    if document["input_type"] == "pdf":
        scan_pdf(source, store.settings.clamav_host, store.settings.clamav_port)
        pages = isolated_pages(source, store.settings)
    else:
        pages = [text_page(source.read_text(encoding="utf-8"))]
    cov = coverage(pages)
    if not cov["readable_pages"]:
        raise ServiceError("no_extractable_text", "No usable text was found. OCR is not available; try pasting readable text.")
    warnings = [warning for page in pages for warning in page["warnings"]]
    passages = chunks(pages)
    for start in range(0, len(passages), 16):
        batch = passages[start:start + 16]
        try:
            vectors = provider.embeddings([chunk["quote"] for chunk in batch])
        except ServiceError as problem:
            if problem.code != "budget_exceeded":
                raise
            cov["status"] = "partial"
            cov["reasons"] = sorted(set(cov["reasons"] + ["retrieval_budget_exceeded"]))
            warnings.append({"code": "retrieval_budget_exceeded", "message": "Semantic indexing is partial; keyword retrieval remains available.", "page_numbers": []})
            break
        for passage, vector in zip(batch, vectors):
            passage["embedding"] = vector
    content = {"pages": pages, "chunks": passages, "coverage": cov, "warnings": warnings}
    candidate = store.stage_content(document["session_id"], operation, content)
    result = {"type": "ingestion", "document_id": document["id"], "coverage": cov, "warnings": warnings}
    update = {"status": "ready", "content_key": candidate, "page_count": len(pages), "coverage": cov, "warnings": warnings, "error": None}
    return result, update, candidate


def execute(sid: str, opid: str, *, store: Store | None = None, provider=None) -> str:
    store = store or Store(Redis.from_url(settings.redis_url), settings)
    claimed = store.claim(sid, opid)
    if not claimed:
        return "cancelled"
    operation, document = claimed
    budget = store.settings.question_provider_tokens if operation["kind"] == "question" else store.settings.operation_provider_tokens
    provider = provider or OpenAIProvider(store.settings, budget)
    candidate = None
    try:
        if operation["kind"] == "ingestion":
            result, update, candidate = ingest(document, operation, provider, store)
        elif operation["kind"] == "analysis":
            result = analyze(document, store.content(sid, document["id"]), provider, store.settings)
            update = None
        else:
            result = answer(document, store.content(sid, document["id"]), operation["request"]["question"], provider, store.settings)
            update = None
        if len(json.dumps(result, ensure_ascii=False).encode("utf-8")) > 262_144:
            raise ServiceError("invalid_model_output", "The result exceeded the safe output size.")
        if not store.finish(sid, operation, result=result, document=update) and candidate:
            store.redis.delete(candidate)
    except Exception as problem:
        safe = problem if isinstance(problem, ServiceError) else ServiceError("internal_error", "Processing failed safely. Try again later.", 500, True)
        update = {"status": "failed", "error": safe.safe(), "coverage": None} if operation["kind"] == "ingestion" else None
        store.finish(sid, operation, error=safe.safe(), document=update)
        if candidate:
            store.redis.delete(candidate)
    return opid
