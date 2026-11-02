import unicodedata
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SessionRequest(StrictModel):
    processing_notice_version: str = Field(min_length=1, max_length=100)
    accept_processing: Literal[True]


class TextRequest(StrictModel):
    title: str = Field(default="Pasted text", max_length=200)
    text: str = Field(min_length=1, max_length=100_000)

    @field_validator("title", "text", mode="before")
    @classmethod
    def normalized(cls, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("A string is required")
        value = unicodedata.normalize("NFC", value)
        if not value.strip():
            raise ValueError("Text must not be blank")
        return value


class AnalysisRequest(StrictModel):
    language: Literal["en"] = "en"


class QuestionRequest(AnalysisRequest):
    question: str = Field(min_length=1, max_length=2_000)

    @field_validator("question", mode="before")
    @classmethod
    def normalized(cls, value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("A question is required")
        return unicodedata.normalize("NFC", value).strip()


class Warning(StrictModel):
    code: str
    message: str
    page_numbers: list[int] = Field(default_factory=list)


class Coverage(StrictModel):
    status: Literal["complete", "partial"]
    readable_pages: list[int]
    partial_pages: list[int]
    unreadable_pages: list[int]
    analyzed_pages: list[int]
    reasons: list[str]


class Statement(StrictModel):
    text: str = Field(max_length=5_000)
    citation_ids: list[str] = Field(default_factory=list)


class Fact(Statement):
    id: str


class Fee(Fact):
    amount: str | None = None
    currency: str | None = None


class Deadline(Fact):
    kind: Literal["absolute", "relative", "ambiguous"]
    date: str | None = None
    trigger: str | None = None
    counting_rule: str | None = None


class Action(Fact):
    kind: Literal["document_requirement", "suggested_step"]
    related_fact_ids: list[str] = Field(default_factory=list)


class AnalysisDraft(StrictModel):
    meaning: list[Statement]
    possible_effects: list[Statement]
    requirements: list[Fact]
    eligibility: list[Fact]
    fees: list[Fee]
    deadlines: list[Deadline]
    actions: list[Action]
    details_to_check: list[Statement]
    not_stated: list[Literal["requirements", "eligibility", "fees", "deadlines"]]


class AnswerDraft(StrictModel):
    status: Literal["answered", "insufficient_evidence", "conflicting_evidence"]
    statements: list[Statement]


class ErrorInfo(StrictModel):
    code: str
    message: str
    request_id: str
    retryable: bool
    details: list[dict[str, str]]


class ErrorEnvelope(StrictModel):
    error: ErrorInfo


class SessionCreated(StrictModel):
    session_id: str
    session_token: str
    created_at: str
    expires_at: str
    processing_notice_version: str


class SessionInfo(StrictModel):
    session_id: str
    created_at: str
    expires_at: str
    documents_created: int
    documents_remaining: int
    outstanding_operations: int


class Acknowledgment(StrictModel):
    document_id: str
    operation_id: str
    status: Literal["queued"]
    expires_at: str


class DocumentInfo(StrictModel):
    id: str
    input_type: Literal["text", "pdf"]
    title: str
    filename: str | None
    status: Literal["queued", "processing", "ready", "failed"]
    ingestion_operation_id: str
    page_count: int | None
    coverage: Coverage | None
    warnings: list[Warning]
    error: ErrorInfo | None
    created_at: str
    expires_at: str


class Paragraph(StrictModel):
    number: int
    start: int
    end: int


class LayoutSpan(StrictModel):
    start: int
    end: int
    boxes: list[list[float]]


class PageInfo(StrictModel):
    document_id: str
    page_number: int
    printed_page_label: str | None
    status: Literal["readable", "partial", "unreadable"]
    text: str
    paragraphs: list[Paragraph]
    layout_spans: list[LayoutSpan]
    warnings: list[Warning]


class Citation(StrictModel):
    id: str
    document_id: str
    page_number: int
    start: int
    end: int
    quote: str
    boxes: list[list[float]]


class Generation(StrictModel):
    model_id: str
    prompt_version: str
    retrieval_version: str
    extraction_version: str
    schema_version: str


class IngestionResult(StrictModel):
    type: Literal["ingestion"]
    document_id: str
    coverage: Coverage
    warnings: list[Warning]


class AnalysisResult(AnalysisDraft):
    type: Literal["analysis"]
    language: Literal["en"]
    coverage: Coverage
    citations: list[Citation]
    warnings: list[Warning]
    generation: Generation


class AnswerResult(AnswerDraft):
    type: Literal["answer"]
    language: Literal["en"]
    coverage: Coverage
    citations: list[Citation]
    warnings: list[Warning]
    generation: Generation


class OperationInfo(StrictModel):
    id: str
    document_id: str
    kind: Literal["ingestion", "analysis", "question"]
    state: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    stage: str
    created_at: str
    updated_at: str
    expires_at: str
    result: IngestionResult | AnalysisResult | AnswerResult | None
    error: ErrorInfo | None


class Notice(StrictModel):
    version: str
    url: str


class Processor(StrictModel):
    name: str
    purpose: str
    policy_url: str
    retention_summary: str
    region: str


class Capabilities(StrictModel):
    api_version: Literal["v1"]
    application_version: str
    processing_available: bool
    features: dict[str, bool]
    output_languages: list[str]
    limits: dict[str, int]
    processing_notice: Notice | None
    processors: list[Processor]


class Deleting(StrictModel):
    status: Literal["deleting"]


class DeletingDocument(Deleting):
    document_id: str


class ServiceError(Exception):
    def __init__(self, code: str, message: str, status: int = 422, retryable: bool = False):
        self.code, self.message, self.status, self.retryable = code, message, status, retryable
        super().__init__(code)

    def safe(self, request_id: str = "") -> dict:
        return {"code": self.code, "message": self.message, "request_id": request_id,
                "retryable": self.retryable, "details": []}
