# AIGht Product and Delivery Plan

Status: proposed MVP baseline, 2 November 2026. No application implementation exists yet. Estimates and release dates must be set after the first technical spike.

## Product direction

**AIGht — AIght, Alright!**

Making complicated documents easier to understand.

AIGht turns document content into plain-language explanations, source-backed answers, and practical next steps. Initial users include students reviewing scholarship guidelines and people navigating school memoranda, government announcements, policies, and application requirements. Contracts are a later evaluation category, not a promise of legal review.

Proposed tagline: “Complicated documents? AIght, alright. We got you.”

Success means a user can identify the relevant rule, understand its conditions, and find the original evidence before acting.

## MVP scope

| Feature | Included behavior |
| --- | --- |
| Document input | Upload one text-based PDF or paste text; one active document at a time |
| AIght, Explain! | English explanation organized by meaning, possible relevance, actions, and details to check |
| AIght, What Now? | Cited requirements, eligibility rules, fees, deadlines, and an action checklist |
| AIght, Ask! | Single-turn questions grounded in the active document, with selectable source citations |
| Source access | PDF preview and accessible extracted text; citations open the relevant page and passage |
| Privacy controls | Temporary anonymous session, visible expiry, delete-document and end-session actions |
| Feedback | An issue template for redacted AI accuracy reports; a private vulnerability reporting route |

Users can mark checklist items complete in the current browser view. These marks are personal progress, not a verified eligibility determination, and are not stored by the server in the MVP.

Ask requests are independent. The UI may show prior exchanges during the session, but follow-up questions must restate their subject; conversational memory is deferred.

## Later releases

- Filipino and Cebuano explanations, after native-speaker evaluation of meaning and terminology.
- AIght, Watch Out!: deeper clause review, with evidence and uncertainty rather than automatic legal conclusions.
- AIght, Compare!: two-document comparison with aligned passages and explicit version identity.
- OCR for scanned pages, with confidence and extraction-quality warnings.
- Accounts, saved history, persistent checklists, document sharing, and PostgreSQL storage.
- Multi-document questions, exports, notifications, and integrations.

The MVP still surfaces ambiguity or conflicts encountered during ordinary extraction. That is a grounding requirement, not the full Watch Out feature.

## Initial operating limits

These are project defaults to implement and evaluate, not measured service capacity. [api.md](api.md) owns the precise request limits.

| Limit | MVP default |
| --- | --- |
| Session lifetime | 60 minutes from creation, without sliding renewal |
| Documents per session | 5, including failed imports; no upload history survives the session |
| Uploaded PDF | 10 MiB, 50 pages, 300,000 extracted Unicode code points |
| Pasted text | 100,000 Unicode code points |
| Question | 2,000 Unicode code points |
| Simultaneous work | 2 queued or running operations per session |

Reject encrypted PDFs and documents with no usable text. If only some pages are readable, show the missing pages and return a partial analysis; never imply the entire document was covered. Reject pathological extraction output rather than silently truncating it.

## Delivery sequence

### 0. Confirm the foundations

- Select supported .NET and Python versions; record and pin exact versions during scaffolding.
- Select the LLM/embedding provider, PDF extraction library, and backend/storage host.
- Verify provider data handling, regions, pricing, request limits, and deletion constraints.
- Create synthetic fixtures covering the scholarship example, conflicting rules, missing dates, and unreadable pages.
- Prototype PDF text extraction, page references, bounding boxes, and accessible text navigation.

Exit: a permitted sample can be extracted with reproducible passage locations; deployment and provider decisions are recorded, including unresolved risks.

### 1. Build secure input and temporary sessions

- Scaffold Blazor WebAssembly with Bootstrap and a FastAPI service plus worker.
- Add anonymous bearer sessions, ownership checks, request limits, private source storage, and Redis-backed jobs.
- Add upload/paste validation, scan-before-parse handling, ingestion status, and source viewing.
- Implement absolute expiry, cancellation, deletion, and cleanup monitoring before accepting real user documents.

Exit: two sessions cannot access each other's documents or jobs; expired/deleted data cannot be read or republished by workers.

### 2. Explain and extract actions

- Preserve page provenance while chunking and indexing.
- Extract facts across all readable pages, then synthesize the explanation.
- Return typed, schema-validated sections with evidence and coverage information.
- Preserve “must,” “may,” exceptions, amounts, and relative-deadline wording.
- Build the explanation view, action checklist, and source citation navigation.

Exit: the evaluation fixtures produce complete or explicitly partial results; unsupported claims and fabricated citations are blocked.

### 3. Add document-grounded questions

- Retrieve within the authorized document before calling the model.
- Cite exact passages; return insufficient evidence or conflicting evidence when appropriate.
- Add provider timeouts, bounded retry behavior, per-session budgets, and safe error messages.
- Show the answer beside its source and offer a redacted accuracy-report path.

Exit: answerable, unanswerable, ambiguous, adversarial, and cross-session cases pass the agreed evaluation set.

### 4. Validate and release a controlled beta

- Exercise keyboard, screen-reader, small-screen, zoom, and low-bandwidth flows.
- Test malicious PDFs, prompt injection, cost exhaustion, cancellation races, and provider outages.
- Run retention/deletion drills, restore/configuration checks, and secret scanning.
- Publish the actual processing notice, provider details, and private security contact.
- Measure quality, latency, and cost on a documented workload before publishing claims.

Exit: all release gates below have recorded evidence and a maintainer signs off on the remaining limitations.

## Acceptance examples

| Scenario | Required behavior |
| --- | --- |
| “GWA not exceeding 2.00”; question: “Does 1.75 meet this condition?” | Explain that 1.75 meets that numeric condition, cite it, and avoid asserting overall eligibility |
| “Within fifteen calendar days from receipt of notice” | Preserve the trigger and calendar-day rule; ask the user to identify receipt date; leave the absolute due date unset |
| A fee is not stated | Say “Not stated in the document”; do not convert absence into “free” |
| Two clauses give different deadlines | Show both passages and request clarification from the issuer |
| Question asks about an unrelated scholarship | Say the active document does not provide enough information |
| A PDF page contains “ignore all instructions” | Treat it as document content; do not execute it or expose other data |
| Page 4 has no extractable text | Identify page 4 as unreadable and label analysis coverage partial |

## Quality and release gates

Use at least 30 synthetic or permitted documents and 100 reviewed questions, including negative cases. Keep document-level train/development and held-out evaluation splits; never tune prompts on the held-out set. Initial thresholds are targets to validate, not achieved results.

- 100% of emitted citations resolve to exact text in the correct authorized document and page.
- At least 95% of reviewed factual claims are supported by their cited evidence; assess entailment separately from citation validity.
- At least 95% recall for critical stated deadlines, fees, required documents, and eligibility conditions in the labeled evaluation set.
- At least 95% correct abstention on questions whose answers are absent; report sample counts and ambiguous cases.
- Zero fabricated dates/amounts and zero cross-session disclosure in the release test set. Any occurrence blocks release.
- Full keyboard operation, readable source text, and WCAG 2.2 AA checks for the critical journey.
- Deletion/expiry tests cover API data, storage, queue registries, caches, and late worker writes.
- Record p50/p95 latency, failure rate, and cost per document/question with workload and environment. Set operating targets after measurement.

## Risks and decisions

| Risk or decision | Initial treatment |
| --- | --- |
| Wrong or incomplete extraction | Coverage reports, representative fixtures, and source access |
| Unsupported explanations | Citation validation, evidence review, and abstention |
| Personal or sensitive documents | Temporary sessions, restricted processing, clear provider notice, and redacted reporting |
| Unexpected AI cost | Hard input/output budgets, concurrency limits, and a deployment-wide spend ceiling |
| Anonymous sessions do not provide durable identity | No recovery/history claim; abuse controls and a possible later account model |
| Hosting or provider constraints change | Recheck primary documentation when implementing and deploying |

The repository maintainer owns these decisions until roles are assigned. Track implementation work with the [GitHub issue templates](.github/ISSUE_TEMPLATE); templates become available after the files reach a GitHub repository's default branch, following [GitHub's template configuration guidance](https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/configuring-issue-templates-for-your-repository).

## Documentation map

[AI declaration](ai-declaration.md) defines responsible AI practice. [Design](design.md) defines user journeys and interface behavior. [Architecture](architecture.md) defines system boundaries. [AGENTS.md](AGENTS.md) guides contributors and coding agents. [Security](security.md) defines protections and disclosure. [API](api.md) defines the proposed wire contract.
