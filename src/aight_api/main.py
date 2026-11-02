import hashlib
import hmac
import json
import re
import secrets
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, File, Form, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from redis import Redis
from redis.exceptions import RedisError

from . import __version__
from .config import Settings, settings
from .jobs import source_directory
from .models import AnalysisRequest, QuestionRequest, ServiceError, SessionRequest, TextRequest
from .models import (Acknowledgment, Capabilities, Deleting, DeletingDocument, DocumentInfo,
                     ErrorEnvelope, OperationInfo, PageInfo, SessionCreated, SessionInfo)
from .store import Store, identity, iso, now_ms, packed


class BodyLimit:
    def __init__(self, app, maximum: int):
        self.app, self.maximum = app, maximum

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        count, started = 0, False
        async def limited_receive():
            nonlocal count
            message = await receive()
            count += len(message.get("body", b""))
            if count > self.maximum:
                raise ServiceError("file_too_large", "The request exceeds the upload limit.", 413)
            return message
        async def tracked_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)
        length = dict(scope.get("headers", [])).get(b"content-length", b"0")
        try:
            if int(length) > self.maximum:
                raise ServiceError("file_too_large", "The request exceeds the upload limit.", 413)
            await self.app(scope, limited_receive, tracked_send)
        except ServiceError as problem:
            if not started:
                await JSONResponse({"error": problem.safe()}, status_code=problem.status,
                                   headers={"Cache-Control": "no-store"})(scope, receive, send)


def create_app(config: Settings = settings, client: Redis | None = None) -> FastAPI:
    app = FastAPI(title="AIGht", version=__version__, docs_url=None, redoc_url=None,
                 responses={code: {"model": ErrorEnvelope} for code in (401, 404, 409, 413, 415, 422, 429, 503)})
    app.state.store = Store(client or Redis.from_url(config.redis_url), config)
    app.state.network_salt = (config.log_network_salt or secrets.token_hex(32)).encode()
    app.add_middleware(BodyLimit, maximum=config.max_pdf_bytes + 1_048_576)
    app.add_middleware(CORSMiddleware, allow_origins=config.origins, allow_credentials=False,
                       allow_methods=["GET", "POST", "DELETE"],
                       allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
                       expose_headers=["Location", "Retry-After", "X-Request-ID"])

    @app.middleware("http")
    async def private_headers(request: Request, call_next):
        request.state.request_id = identity("req")
        response = await call_next(request)
        response.headers.update({"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
                                 "Referrer-Policy": "no-referrer", "X-Request-ID": request.state.request_id})
        return response

    @app.exception_handler(ServiceError)
    async def service_error(request, problem):
        headers = {"Retry-After": "2"} if problem.retryable and problem.status in {409, 429, 503} else {}
        return JSONResponse({"error": problem.safe(getattr(request.state, "request_id", ""))}, status_code=problem.status, headers=headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, problem):
        safe = ServiceError("validation_error", "Check the input fields and documented limits.").safe(request.state.request_id)
        safe["details"] = [{"field": ".".join(str(item) for item in error["loc"]), "code": error["type"]} for error in problem.errors()]
        return JSONResponse({"error": safe}, status_code=422)

    @app.exception_handler(RedisError)
    async def unavailable(request, problem):
        return JSONResponse({"error": ServiceError("dependency_unavailable", "Temporary processing storage is unavailable.", 503, True).safe(request.state.request_id)}, status_code=503)

    def store(request: Request) -> Store:
        return request.app.state.store

    def rate(store: Store, key: str, maximum: int, seconds: int):
        slot = now_ms() // (seconds * 1000)
        counter = f"aight:rate:{key}:{slot}"
        with store.redis.pipeline(transaction=True) as pipe:
            pipe.incr(counter)
            pipe.expire(counter, seconds)
            count, _ = pipe.execute()
        if count > maximum:
            raise ServiceError("rate_limited", "Too many requests. Please wait before trying again.", 429, True)

    def session(request: Request, storage: Annotated[Store, Depends(store)]) -> dict:
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer ") or len(header) > 200:
            raise ServiceError("invalid_session", "Start a new temporary session.", 401)
        value = storage.authenticate(header[7:])
        rate(storage, value["id"] + (":read" if request.method == "GET" else ":work"), 60 if request.method == "GET" else 10, 60)
        return value

    def available():
        if not config.processing_available:
            raise ServiceError("processing_unavailable", "Processing is not configured. Explore the synthetic example instead.", 503)

    def idem(request: Request) -> str:
        value = request.headers.get("Idempotency-Key", "")
        if not re.fullmatch(r"[A-Za-z0-9_-]{16,128}", value):
            raise ServiceError("validation_error", "Provide a valid Idempotency-Key header.")
        return value

    def accepted(response: dict):
        return JSONResponse(response, status_code=202, headers={"Location": f"/api/v1/operations/{response['operation_id']}", "Retry-After": "2"})

    def public_document(document: dict) -> dict:
        return {key: value for key, value in document.items() if key not in {"session_id", "generation", "source_key", "content_key", "expires_ms"}}

    def import_source(storage, current, kind, title, filename, data, key):
        docid = identity("doc")
        directory = source_directory(config.data_dir, current["id"], docid)
        config.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        directory.parent.mkdir(exist_ok=True, mode=0o700)
        directory.mkdir(mode=0o700)
        source = directory / ("source.pdf" if kind == "pdf" else "source.txt")
        document = {"id": docid, "session_id": current["id"], "generation": secrets.token_hex(16),
                    "input_type": kind, "title": title, "filename": filename, "status": "queued",
                    "source_key": str(source), "page_count": None, "coverage": None, "warnings": [],
                    "error": None, "created_at": iso(now_ms()), "expires_at": current["expires_at"], "expires_ms": current["expires_ms"]}
        fingerprint = hashlib.sha256(packed({"kind": kind, "title": title, "filename": filename}).encode() + data).hexdigest()
        admitted = False
        try:
            (directory / "manifest.json").write_text(packed({"session_id": current["id"], "document_id": docid,
                                                            "expires_ms": current["expires_ms"], "created_ms": now_ms()}), encoding="utf-8")
            source.write_bytes(data)
            source.chmod(0o600)
            response, admitted = storage.admit(current["id"], docid, "ingestion", {}, key, fingerprint, document)
            return accepted(response)
        except OSError:
            raise ServiceError("dependency_unavailable", "Private document storage is unavailable.", 503, True) from None
        finally:
            if not admitted:
                # A lost EXEC response is uncertain: retain staged data for reconciliation, not eager deletion.
                record = storage.read(storage.key(current["id"], f"doc:{docid}"))
                if not record:
                    try:
                        source.unlink(missing_ok=True)
                        (directory / "manifest.json").unlink(missing_ok=True)
                        if directory.exists():
                            directory.rmdir()
                    except OSError:
                        pass  # Independent directory reconciliation retries storage cleanup.

    @app.get("/health/live")
    def health():
        return {"status": "ok"}

    @app.get("/api/v1/capabilities", response_model=Capabilities)
    def capabilities():
        return {"api_version": "v1", "application_version": __version__, "processing_available": config.processing_available,
                "features": {"pdf": config.pdf_processing_enabled, "pasted_text": True, "explain": True,
                             "actions": True, "ask": True, "ocr": False, "compare": False, "clause_review": False},
                "output_languages": ["en"], "limits": {
                    "session_lifetime_seconds": config.session_seconds, "max_pdf_bytes": config.max_pdf_bytes,
                    "max_pdf_pages": config.max_pdf_pages, "max_extracted_code_points": config.max_extracted_code_points,
                    "max_pasted_code_points": config.max_pasted_code_points, "max_title_code_points": 200,
                    "max_filename_code_points": 255, "max_question_code_points": 2000,
                    "max_documents_per_session": config.max_documents_per_session,
                    "max_outstanding_operations_per_session": config.max_outstanding_operations,
                    "max_read_requests_per_minute": 60, "max_work_requests_per_minute": 10,
                    "max_session_creations_per_network_window": 5, "session_creation_window_seconds": 600},
                "processing_notice": {"version": config.notice_version, "url": config.notice_url} if config.processing_available else None,
                "processors": [{"name": "OpenAI", "purpose": "Document explanation, retrieval and questions",
                                "policy_url": "https://openai.com/enterprise-privacy/", "retention_summary": config.processor_retention,
                                "region": config.processor_region}] if config.processing_available else []}

    @app.post("/api/v1/sessions", status_code=201, response_model=SessionCreated)
    def create_session(value: SessionRequest, request: Request, storage: Annotated[Store, Depends(store)]):
        available()
        address = request.client.host if request.client else "unknown"
        digest = hmac.new(app.state.network_salt, address.encode(), hashlib.sha256).hexdigest()
        rate(storage, "network:" + digest, 5, 600)
        if value.processing_notice_version != config.notice_version:
            raise ServiceError("notice_changed", "Read the updated processing notice before continuing.", 409)
        return storage.create_session(value.processing_notice_version)

    @app.get("/api/v1/sessions/current", response_model=SessionInfo)
    def current_session(current: Annotated[dict, Depends(session)]):
        return {"session_id": current["id"], "created_at": current["created_at"], "expires_at": current["expires_at"],
                "documents_created": current["documents_created"], "documents_remaining": max(0, config.max_documents_per_session - current["documents_created"]),
                "outstanding_operations": current["outstanding"]}

    @app.delete("/api/v1/sessions/current", status_code=202, response_model=Deleting)
    def end_session(current: Annotated[dict, Depends(session)], storage: Annotated[Store, Depends(store)]):
        storage.revoke_session(current)
        return {"status": "deleting"}

    @app.post("/api/v1/documents/text", status_code=202, response_model=Acknowledgment)
    def paste(value: TextRequest, request: Request, current: Annotated[dict, Depends(session)], storage: Annotated[Store, Depends(store)]):
        available()
        return import_source(storage, current, "text", value.title, None, value.text.encode("utf-8"), idem(request))

    @app.post("/api/v1/documents", status_code=202, response_model=Acknowledgment)
    async def upload(request: Request, current: Annotated[dict, Depends(session)], storage: Annotated[Store, Depends(store)],
                     file: Annotated[UploadFile, File()], title: Annotated[str | None, Form(max_length=200)] = None):
        available()
        key = idem(request)
        if not config.pdf_processing_enabled:
            raise ServiceError("processing_unavailable", "Safe PDF processing is not enabled. Paste readable text instead.", 503)
        filename = file.filename or "document.pdf"
        if len(filename) > 255 or not filename.lower().endswith(".pdf") or file.content_type != "application/pdf":
            raise ServiceError("unsupported_media_type", "Choose a PDF file.", 415)
        data = bytearray()
        try:
            while part := await file.read(65_536):
                data.extend(part)
                if len(data) > config.max_pdf_bytes:
                    raise ServiceError("file_too_large", "PDF files must be 10 MiB or smaller.", 413)
        finally:
            await file.close()
        if not data.startswith(b"%PDF-"):
            raise ServiceError("unsupported_media_type", "The file is not a supported PDF.", 415)
        return import_source(storage, current, "pdf", title or filename, filename, bytes(data), key)

    @app.get("/api/v1/documents/{document_id}", response_model=DocumentInfo)
    def get_document(document_id: str, current: Annotated[dict, Depends(session)], storage: Annotated[Store, Depends(store)]):
        return public_document(storage.document(current["id"], document_id))

    @app.get("/api/v1/documents/{document_id}/pages/{page_number}", response_model=PageInfo)
    def page(document_id: str, page_number: int, current: Annotated[dict, Depends(session)], storage: Annotated[Store, Depends(store)]):
        content = storage.content(current["id"], document_id)
        if not 1 <= page_number <= len(content["pages"]):
            raise ServiceError("not_found", "This page is unavailable.", 404)
        return {"document_id": document_id, **content["pages"][page_number - 1]}

    @app.get("/api/v1/documents/{document_id}/pages", response_model=list[PageInfo])
    def pages(document_id: str, current: Annotated[dict, Depends(session)], storage: Annotated[Store, Depends(store)]):
        content = storage.content(current["id"], document_id)
        return [{"document_id": document_id, **page} for page in content["pages"]]

    @app.get("/api/v1/documents/{document_id}/source")
    def source(document_id: str, current: Annotated[dict, Depends(session)], storage: Annotated[Store, Depends(store)]):
        document = storage.document(current["id"], document_id, ready=True)
        directory = source_directory(config.data_dir, current["id"], document_id)
        path = directory / ("source.pdf" if document["input_type"] == "pdf" else "source.txt")
        def stream():
            with path.open("rb") as value:
                while part := value.read(65_536):
                    try:
                        storage.document(current["id"], document_id, ready=True)
                    except ServiceError:
                        return
                    yield part
        return StreamingResponse(stream(), media_type="application/pdf" if document["input_type"] == "pdf" else "text/plain; charset=utf-8",
                                 headers={"Content-Disposition": 'inline; filename="document.pdf"' if document["input_type"] == "pdf" else 'inline; filename="document.txt"'})

    @app.delete("/api/v1/documents/{document_id}", status_code=202, response_model=DeletingDocument)
    def delete_document(document_id: str, current: Annotated[dict, Depends(session)], storage: Annotated[Store, Depends(store)]):
        storage.revoke_document(current["id"], document_id)
        return {"document_id": document_id, "status": "deleting"}

    def work(document_id, value, request, current, storage, kind):
        available()
        storage.document(current["id"], document_id, ready=True)
        payload = value.model_dump()
        fingerprint = hashlib.sha256(packed(payload).encode()).hexdigest()
        response, _ = storage.admit(current["id"], document_id, kind, payload, idem(request), fingerprint)
        return accepted(response)

    @app.post("/api/v1/documents/{document_id}/analyses", status_code=202, response_model=Acknowledgment)
    def analysis(document_id: str, value: AnalysisRequest, request: Request, current: Annotated[dict, Depends(session)], storage: Annotated[Store, Depends(store)]):
        return work(document_id, value, request, current, storage, "analysis")

    @app.post("/api/v1/documents/{document_id}/questions", status_code=202, response_model=Acknowledgment)
    def question(document_id: str, value: QuestionRequest, request: Request, current: Annotated[dict, Depends(session)], storage: Annotated[Store, Depends(store)]):
        return work(document_id, value, request, current, storage, "question")

    @app.get("/api/v1/operations/{operation_id}", response_model=OperationInfo)
    def operation(operation_id: str, current: Annotated[dict, Depends(session)], storage: Annotated[Store, Depends(store)]):
        value = storage.operation(current["id"], operation_id)
        return {key: value[key] for key in ("id", "document_id", "kind", "state", "stage", "created_at", "updated_at", "expires_at", "result", "error")}

    return app


app = create_app()
