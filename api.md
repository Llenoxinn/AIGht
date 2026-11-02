# AIGht API Contract

Status: proposed REST contract v0.1, 2 November 2026. These endpoints are not implemented. Examples use synthetic IDs and data, not live credentials or documents.

## Conventions

- Base path: `/api/v1`; production hostname remains a deployment decision.
- Use HTTPS. JSON requests/responses use UTF-8; file upload uses multipart form data.
- Timestamps are RFC 3339 UTC strings. Explicit normalized dates use `YYYY-MM-DD`; preserve the original date wording separately.
- IDs are opaque server-generated strings. Never derive authorization from their format.
- Strings are bounded and measured in Unicode code points after NFC normalization, except uploaded file byte limits. Reject unknown request fields and unsupported enum values with `422`.
- All private responses, including errors, use `Cache-Control: no-store`. Secrets never appear in URLs.
- Return `X-Request-ID` on responses. Generate/validate a safe correlation ID; do not put content into it.
- Public health is `GET /health/live`, outside the versioned product API, returning only `{"status":"ok"}`. Restrict detailed readiness information.

## Authentication, agreement, and expiry

All endpoints except capabilities, session creation, and liveness require:

```http
Authorization: Bearer <session_token>
```

Before session creation, the client displays the current processing notice and asks for agreement. The deployment must supply actual processor identities and policies before enabling processing; a draft notice is insufficient.

Generate at least 256 random token bits and store only a digest. Sessions expire 60 minutes after creation, with no renewal endpoint. Documents, operations, results, caches, and idempotency records inherit the same expiry. The browser keeps the token only in memory, so a refresh loses access.

Missing, invalid, revoked, and expired tokens return `401 invalid_session`. With a valid session, missing, foreign, deleted, or expired document/operation resources return the same `404 not_found` response. Check ownership on every endpoint, including original source and page reads.

## Endpoint summary

| Method | Path | Success | Purpose |
| --- | --- | --- | --- |
| GET | `/capabilities` | 200 | Public features, limits, notice, and processor information |
| POST | `/sessions` | 201 | Create a temporary session after notice agreement |
| GET | `/sessions/current` | 200 | Read expiry and remaining session quotas |
| DELETE | `/sessions/current` | 202 | Revoke session and schedule cleanup |
| POST | `/documents` | 202 | Upload a PDF and queue ingestion |
| POST | `/documents/text` | 202 | Import pasted text and queue ingestion |
| GET | `/documents/{document_id}` | 200 | Read owned document metadata and coverage |
| GET | `/documents/{document_id}/source` | 200 | Read the original PDF or pasted source |
| GET | `/documents/{document_id}/pages/{page_number}` | 200 | Read canonical extracted text and layout metadata |
| DELETE | `/documents/{document_id}` | 202 | Revoke document and cancel its work |
| POST | `/documents/{document_id}/analyses` | 202 | Queue explanation and action extraction |
| POST | `/documents/{document_id}/questions` | 202 | Queue an independent grounded question |
| GET | `/operations/{operation_id}` | 200 | Poll work state and obtain its typed result |

There are no MVP translation, comparison, account, sharing, OCR, or cross-document endpoints. Checklist marks and question history display are browser-memory UI state.

## Limits and idempotency

| Resource | Initial hard limit |
| --- | --- |
| PDF | 10 MiB = 10,485,760 file bytes; 50 pages; 300,000 extracted code points |
| Pasted text | 1–100,000 code points, with non-whitespace content |
| Title / filename display | 200 / 255 code points; never used as storage paths |
| Question | 1–2,000 code points, with non-whitespace content |
| Language | `en` only |
| Document creations | 5 accepted imports per session, including imports that later fail |
| Outstanding operations | 2 queued/running operations per session, including ingestion |
| Read calls | 60 requests per minute per session |
| Work-creation calls | 10 requests per minute per session, plus outstanding-work/document quotas |
| Session creation | 5 per 10 minutes per network identifier, with deployment-wide abuse controls |

Publish deployed limits through capabilities and keep the client consistent. Gateways may apply additional body-size/rate limits, but must preserve the documented file allowance including multipart overhead. Set global capacity and spend ceilings before beta; anonymous session resets must not bypass them.

Require `Idempotency-Key` for PDF/text import, analysis, and question creation. Accept 16–128 ASCII letters, digits, hyphens, or underscores. Scope a key to the session, HTTP method, and concrete path, and retain it only until session expiry.

The first accepted request atomically claims the key and records a payload fingerprint. Same key and same payload returns the original `202` response and operation, even if that operation has completed or failed; it creates no extra work or quota charge. Same key with different payload returns `409 idempotency_conflict`. Missing/malformed keys return `422 validation_error`.

For JSON, fingerprint validated canonical fields including applied defaults. For multipart, fingerprint validated fields and file bytes, excluding boundary encoding. Concurrent identical requests must resolve to one operation; return `409 request_in_progress` with `Retry-After` if the original response is not available yet. If the referenced document was deleted, a replay returns `404`, never revives it. Rejected validation does not consume a document slot.

## Public capabilities and session endpoints

### GET /capabilities

Return these fields without authentication:

| Field | Type / meaning |
| --- | --- |
| `api_version` | String, `v1` |
| `processing_available` | Boolean; false until required configuration and notice are complete |
| `features` | Object with booleans for `pdf`, `pasted_text`, `explain`, `actions`, `ask`, `ocr`, `compare`, `clause_review` |
| `output_languages` | String array, initially `["en"]` |
| `limits` | Object containing the numeric fields listed below |
| `processing_notice` | Null while unconfigured, otherwise `{version, url}` pointing to the actual published notice |
| `processors` | Array of actual `{name, purpose, policy_url, retention_summary}` records; empty while unconfigured |

The `limits` object contains `session_lifetime_seconds` (3600), `max_pdf_bytes` (10485760), `max_pdf_pages` (50), `max_extracted_code_points` (300000), `max_pasted_code_points` (100000), `max_title_code_points` (200), `max_filename_code_points` (255), `max_question_code_points` (2000), `max_documents_per_session` (5), `max_outstanding_operations_per_session` (2), `max_read_requests_per_minute` (60), `max_work_requests_per_minute` (10), `max_session_creations_per_network_window` (5), and `session_creation_window_seconds` (600). All are positive integers. Publish changed deployment limits before the client accepts work under them.

The notice describes application retention, provider retention, training use, regions, deletion limitations, and user controls. Do not return fabricated provider names or generic promises as deployment facts.

### POST /sessions

Request:

```json
{
  "processing_notice_version": "notice_v1",
  "accept_processing": true
}
```

`accept_processing` must be true and the version must match the active notice. A changed notice returns `409 notice_changed`; unavailable processing returns `503 processing_unavailable`. No uploaded document or personal profile is required to create the session.

Response, `201 Created`:

```json
{
  "session_id": "ses_example",
  "session_token": "<returned-once-random-bearer-token>",
  "created_at": "2026-11-02T01:00:00Z",
  "expires_at": "2026-11-02T02:00:00Z",
  "processing_notice_version": "notice_v1"
}
```

The session ID is metadata, not a credential. Do not log this response or redisplay the bearer token. There is no token recovery or refresh in the MVP.

### GET /sessions/current

Return `{session_id, created_at, expires_at, documents_created, documents_remaining, outstanding_operations}`. Do not return the bearer token.

### DELETE /sessions/current

Return `202` with `{"status":"deleting"}` only after access is revoked and cleanup is scheduled. Cancel all associated work. The response acknowledges asynchronous physical cleanup, not verified removal from provider systems. A repeated call with the revoked token returns `401`. There is no authenticated cleanup polling endpoint after revocation.

## Document ingestion and reads

### POST /documents

Multipart fields: required `file` containing a `.pdf` with declared media type `application/pdf`; optional `title`. Validate actual content independently of declaration. No URL import or password field is supported.

Return `202`, with `Location: /api/v1/operations/{operation_id}` and `Retry-After: 2`:

```json
{
  "document_id": "doc_example",
  "operation_id": "op_ingest_example",
  "status": "queued",
  "expires_at": "2026-11-02T02:00:00Z"
}
```

Perform cheap validation before acceptance. Malware scanning, full parsing, page limits, and extracted-text limits may fail asynchronously. Such failures appear on the operation and document, without a misleading ready state. Keep unsafe sources unavailable for preview/download.

### POST /documents/text

Request:

```json
{
  "title": "Scholarship example",
  "text": "GWA must not exceed 2.00."
}
```

`title` is optional; use a safe display default if omitted. Store the original pasted text, create canonical page text, and return the same `202` envelope as PDF ingestion. Pasted text is represented as one logical source page for offsets, labeled as pasted text in the UI.

### GET /documents/{document_id}

Return a document record:

```json
{
  "id": "doc_example",
  "title": "Scholarship example",
  "input_type": "text",
  "filename": null,
  "status": "ready",
  "ingestion_operation_id": "op_ingest_example",
  "page_count": 1,
  "coverage": {
    "status": "complete",
    "readable_pages": [1],
    "unreadable_pages": []
  },
  "warnings": [],
  "error": null,
  "created_at": "2026-11-02T01:01:00Z",
  "expires_at": "2026-11-02T02:00:00Z"
}
```

Document status is `queued | processing | ready | failed`. Before ingestion completes, `page_count` and `coverage` may be null. A failed document has a safe error object. A PDF with some unreadable pages may be ready with partial coverage; a source with no usable text fails ingestion.

### GET /documents/{document_id}/source

Available only after safe ingestion reaches ready. Return the original source as `application/pdf` for PDFs or `text/plain; charset=utf-8` for pasted input. Use a fixed safe media type, escaped disposition filename, `nosniff`, and `no-store`. A valid owned document that is not ready returns `409 document_not_ready`.

Use an authenticated fetch for the viewer. A short-lived browser Blob URL may display the response; revoke it on deletion, expiry, or view teardown. Never put the bearer token in a viewer URL. Do not issue publicly readable object-storage links. The initial viewer may download the bounded complete file; range/streaming behavior is outside this initial contract.

### GET /documents/{document_id}/pages/{page_number}

Page numbers are one-based PDF positions; printed labels, if present, are metadata. Return `409 document_not_ready` before readiness and `404 not_found` for a page outside the document's page range.

```json
{
  "document_id": "doc_example",
  "page_number": 1,
  "printed_page_label": null,
  "status": "readable",
  "text": "GWA must not exceed 2.00.",
  "paragraphs": [
    {"number": 1, "start": 0, "end": 25}
  ],
  "layout_spans": []
}
```

Canonical page text is NFC-normalized with LF line endings. Every `start` is inclusive and every `end` exclusive, counted in Unicode code points. JavaScript/.NET clients must translate to their native UTF-16 indexing when selecting text. Do not compare byte or UTF-16 indexes directly with these offsets.

`layout_spans` contain `{start, end, boxes}` when extraction supports layout. A box is `[x, y, width, height]` normalized to 0–1 in the visible rotated page, with origin at the top-left. Missing geometry is an empty array, not an invented location. An unreadable page returns `status: "unreadable"`, empty text, and empty span/paragraph arrays; it cannot support a citation.

### DELETE /documents/{document_id}

Return `202` with `{"document_id":"doc_example","status":"deleting"}` after revocation. Cancel related operations, invalidate caches, and schedule source/derived-data cleanup. Subsequent document/page/source/operation access returns `404`; repeated deletion also returns `404`. A worker must not republish deleted content. Application-controlled storage cleanup targets 15 minutes; provider copies follow the published notice.

## Analysis and question creation

### POST /documents/{document_id}/analyses

Request:

```json
{
  "language": "en"
}
```

`language` defaults to `en`; other values return `422 unsupported_language`. Require a ready document and return `202` with `{document_id, operation_id, status, expires_at}`, Location, and Retry-After as for ingestion.

Analyze all readable pages in bounded batches. If coverage or result limits prevent completion, return an explicitly partial analysis identifying the affected pages/reasons; never silently treat top-k retrieved chunks as the full document. A requested analysis is not started automatically by the import API; the client starts it after ingestion succeeds.

### POST /documents/{document_id}/questions

Request:

```json
{
  "question": "Does a GWA of 1.75 meet this condition?",
  "language": "en"
}
```

Return the same `202` envelope and headers. The question is single-turn and scoped to the path's document. Do not accept `session_id`, arbitrary document lists, client-supplied evidence, provider prompts, or conversation history as additional request fields.

No answer found is a successful operation with `status: "insufficient_evidence"` in its result, not a transport failure. A timeout or invalid provider output is an operation failure, not an invented answer.

## Operations and result schemas

### GET /operations/{operation_id}

Operation state is `queued | running | succeeded | failed | cancelled`. Return `200` for all readable states; HTTP success means the operation record was fetched, not that processing succeeded.

```json
{
  "id": "op_question_example",
  "document_id": "doc_example",
  "kind": "question",
  "state": "succeeded",
  "stage": "complete",
  "created_at": "2026-11-02T01:02:00Z",
  "updated_at": "2026-11-02T01:02:05Z",
  "expires_at": "2026-11-02T02:00:00Z",
  "result": {
    "type": "answer",
    "status": "answered",
    "language": "en",
    "statements": [
      {
        "text": "A GWA of 1.75 meets this condition because it does not exceed 2.00. Other requirements may still apply.",
        "citation_ids": ["cit_example"]
      }
    ],
    "coverage": {
      "status": "complete",
      "readable_pages": [1],
      "unreadable_pages": [],
      "analyzed_pages": [1],
      "reasons": []
    },
    "citations": [
      {
        "id": "cit_example",
        "document_id": "doc_example",
        "page_number": 1,
        "start": 0,
        "end": 25,
        "quote": "GWA must not exceed 2.00.",
        "boxes": []
      }
    ],
    "warnings": [],
    "generation": {
      "model_id": "configured-model-version",
      "prompt_version": "ask_v1",
      "retrieval_version": "retrieval_v1",
      "extraction_version": "extract_v1",
      "schema_version": "1"
    }
  },
  "error": null
}
```

`kind` is `ingestion | analysis | question`. `stage` is `queued | scanning | extracting | indexing | analyzing | retrieving | answering | complete | failed | cancelled`; text imports skip scanning. Stages are descriptive, not percentages. Pending/running records have null `result` and `error`. Failed records have null `result` and a safe error. Succeeded records have a typed result and null error. Cancelled records have both null.

Poll after two seconds initially and back off up to ten seconds with jitter, respecting `Retry-After` where present. Stop on terminal state, session expiry, or view teardown. The MVP has no SSE/WebSocket stream and no separate operation-cancellation endpoint; deleting its document or ending the session cancels work and makes the record unavailable.

### Common evidence types

| Type | Fields and invariants |
| --- | --- |
| `Statement` | `{text, citation_ids}`; document claims require at least one valid citation; absence/uncertainty messages may have none |
| `Citation` | `{id, document_id, page_number, start, end, quote, boxes}`; quote exactly equals the canonical page slice |
| `Warning` | `{code, message, page_numbers}`; safe human-readable message, page list may be empty |
| `Coverage` | `{status, readable_pages, unreadable_pages, analyzed_pages, reasons}`; status `complete | partial`; reason codes explain missing/budget-limited coverage |
| `Generation` | `{model_id, prompt_version, retrieval_version, extraction_version, schema_version}`; version identifiers, no credentials |

Citation IDs are assigned/resolved by the server and unique within a result. All referenced IDs must exist in that result and belong to the active document. A multi-page claim uses separate page citations. Never create offsets on unreadable pages. Exact quotation validation and semantic support evaluation are separate obligations.

For analysis, `analyzed_pages` identifies pages actually processed for extraction. For questions, it identifies evidence pages supplied to answer generation; `complete` means readable ingestion/retrieval completed within its budget, not that every page was sent to the model or the answer is infallible. Unreadable pages always make coverage partial. Include a reason for any budget-limited or unprocessed scope.

### Ingestion result

`{type: "ingestion", document_id, coverage, warnings}`. Its coverage contains status/readable/unreadable pages; it does not include `analyzed_pages` or `reasons` until downstream analysis. A successful ingest means safe text is ready for processing, not that an explanation has been generated.

### Analysis result

| Field | Type / meaning |
| --- | --- |
| `type` | `analysis` |
| `language` | `en` |
| `meaning` | Array of `Statement` |
| `possible_effects` | Array of conditional `Statement`; no definitive personal eligibility judgment |
| `requirements` | Array of `{id, text, citation_ids}` for stated obligations |
| `eligibility` | Array of `{id, text, citation_ids}` for stated conditions |
| `fees` | Array of `{id, text, amount, currency, citation_ids}`; amount is decimal string or null; currency is explicit code or null |
| `deadlines` | Array of deadline objects described below |
| `actions` | Array of `{id, kind, text, citation_ids, related_fact_ids}`; kind `document_requirement | suggested_step` |
| `details_to_check` | Array of `Statement` for conditions/ambiguity/conflicts encountered |
| `not_stated` | Array drawn from `requirements | eligibility | fees | deadlines` when absent from readable analyzed content |
| `coverage` | `Coverage` |
| `citations` | Array of `Citation` |
| `warnings` | Array of `Warning` |
| `generation` | `Generation` |

Arrays may be empty. `not_stated` is not a claim about unreadable/unprocessed pages; display partial coverage beside any absence statement. Do not infer a currency solely from user location, or infer a zero fee from missing text. Preserve amount ranges or ambiguity in `text` and leave `amount` null when it is not a single explicit amount. Recommendations are distinguished from document obligations.

A deadline contains `{id, text, kind, date, trigger, counting_rule, citation_ids}`. `kind` is `absolute | relative | ambiguous`. `date` is nullable and set only for an unambiguous explicit date; `trigger` and `counting_rule` are nullable source-derived strings.

Example deadline object:

```json
{
  "id": "deadline_example",
  "text": "Submit within fifteen calendar days from receipt of notice.",
  "kind": "relative",
  "date": null,
  "trigger": "receipt of notice",
  "counting_rule": "fifteen calendar days",
  "citation_ids": ["cit_deadline_example"]
}
```

This standalone schema example assumes its enclosing result supplies the cited passage. The MVP does not accept a receipt date or calculate a derived deadline. A month/day without a determinable year, conflicting dates, or an unknown counting rule remains ambiguous with original wording preserved.

### Answer result

`{type: "answer", status, language, statements, coverage, citations, warnings, generation}`. Status is `answered | insufficient_evidence | conflicting_evidence`. Conflict responses cite both sides; insufficient-evidence responses do not fabricate a source for an absent fact. The operation example above shows the full envelope.

## Errors

Use one safe error shape for HTTP failures and failed-operation `error` fields:

```json
{
  "error": {
    "code": "document_not_ready",
    "message": "This document is still being processed.",
    "request_id": "req_example",
    "retryable": true,
    "details": []
  }
}
```

An operation stores the inner error object only. `details` may contain `{field, code}` entries, without submitted values, source passages, filenames, stack traces, or provider responses. `retryable` means retry may be useful after the condition changes; a caller should not blindly repeat failed work. Reuse the original key to discover prior acceptance, and use a new key only for an explicit new processing attempt.

| HTTP status | Example codes | Meaning |
| --- | --- | --- |
| 400 | `malformed_request` | Invalid JSON or multipart encoding |
| 401 | `invalid_session` | Missing/invalid/revoked/expired bearer |
| 404 | `not_found` | Unknown, foreign, deleted, expired, or inaccessible resource |
| 409 | `document_not_ready`, `idempotency_conflict`, `request_in_progress`, `notice_changed` | State or request conflict |
| 413 | `file_too_large`, `text_too_large` | Size limit rejected before acceptance |
| 415 | `unsupported_media_type` | Unsupported request or file type |
| 422 | `validation_error`, `unsupported_language` | Valid syntax with invalid fields |
| 429 | `rate_limited`, `session_limit_reached`, `capacity_limited` | Quota, concurrency, spend, or capacity gate |
| 500 | `internal_error` | Unexpected safe server failure |
| 503 | `processing_unavailable`, `dependency_unavailable` | Required infrastructure/provider configuration unavailable |

Accepted work reports later errors through its operation, such as `encrypted_pdf`, `malformed_pdf`, `unsafe_file`, `page_limit_exceeded`, `extracted_text_limit_exceeded`, `no_extractable_text`, `processing_timeout`, `provider_unavailable`, `invalid_model_output`, `evidence_validation_failed`, or `budget_exceeded`. These do not change the HTTP status of a successful operation-status read.

Rate/capacity responses include `Retry-After` when retry timing is known. For session-lifetime quotas, explain the expiry instead of advertising a short retry. Never expose whether a foreign resource exists or echo sensitive input in errors.

## Versioning and implementation verification

Generate the eventual `/openapi.json` from FastAPI schemas and keep this contract aligned with it. Restrict interactive API documentation in public production as appropriate. A public OpenAPI document must contain no real tokens or private examples.

Before beta, verify all endpoint schemas, synthetic examples, Unicode citation offsets, ownership, malformed input, idempotency concurrency, result readiness, coverage, session expiry, deletion races, bounded worker retries, and safe error serialization. A breaking deployed contract change requires a new API version or coordinated migration; additive fields must remain backward compatible.
