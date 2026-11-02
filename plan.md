# AIGht Product and Delivery Plan

Status: initial v1.0.0 local implementation, 3 November 2026. The API/worker pipeline, evidence validation, temporary lifecycle, Blazor interface, and interactive Three.js workspace now exist. This version number does not establish beta readiness; the gates below still apply. See [README.md](README.md) for runnable commands and [system-flow.md](docs/diagrams/system-flow.md) for complete inputs/outputs and flow.

## Implementation checkpoint

| Area | Implemented | Remaining release evidence |
| --- | --- | --- |
| API and lifecycle | Typed OpenAPI, owned sessions, atomic Redis/RQ admission, guarded publication, cleanup reconciliation | CI/real Redis, restart and load checks |
| Document processing | Pasted text, ClamAV-scanned PDF, Linux Landlock/seccomp subprocess, coverage and canonical spans | Linux runtime check, broad hostile/complex PDF corpus |
| AI | OpenAI structured output and embeddings, scoped hybrid retrieval, literal evidence/fact validation, abstention | Live account/model compatibility, reviewed entailment/injection evaluations, cost measurements |
| Workspace | Explain, checklist, Ask, exact source highlight, PDF preview, interactive 3D and flat navigation | Physical-device performance, assistive-technology and wider responsive checks |
| Operations | Locked application dependencies, local run scripts, Compose, CI configuration | Run container/CI checks, production host/TLS/storage/network controls and actual processing notice |

Local deterministic tests and builds are implementation checks; they do not prove live AI quality or production safety. Do not open beta uploads until the original acceptance/security gates below are evidenced.

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
| Interactive 3D | A real-time Three.js page stack within Blazor, synchronized with source/citation selection and an equivalent flat navigator |
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

Reject encrypted PDFs and documents with no usable text. Classify pages as readable, partial, or unreadable. A searchable heading above a scanned body remains partial even though some text was extracted. Carry partial/missing-page warnings into analyses, answers, and the 3D/flat viewers; never imply the entire document was covered or assert that an unseen requirement is absent. Reject pathological extraction output rather than silently truncating it.

## Delivery sequence

### 0. Confirm the foundations

- Select supported .NET and Python versions; record and pin exact versions during scaffolding.
- Select the LLM/embedding provider, PDF extraction library, and backend/storage host.
- Verify provider data handling, regions, pricing, request limits, and deletion constraints.
- Create synthetic fixtures covering the scholarship example, conflicting rules, missing dates, unreadable pages, searchable headings above image-only bodies, and unreliable table/column extraction.
- Prototype PDF text extraction, page references, bounding boxes, and accessible text navigation.
- Prove one thin local path with a synthetic PDF: upload → bounded AI explanation/question → validated source citation → the same selected page in a minimal interactive 3D stack. This is a feasibility spike, not the full feature implementation or permission to process real private documents.
- Verify Blazor/Three.js module loading and discrete page-selection interop, a flat fallback, and renderer disposal. Record the chosen viewer/renderer build approach and representative desktop/phone test devices.
- Verify that the selected Redis/RQ versions support caller-owned transactional enqueueing, watched-key expiry, and guarded publication. Bound provider spend from the first spike call.

Exit: one synthetic document completes that source-backed path, including actual 3D page selection and flat access. Partial-page fixtures are classified honestly, the queue/transaction approach is demonstrated, and deployment/provider decisions and unresolved risks are recorded.

### 1. Build secure input and temporary sessions

- Scaffold Blazor WebAssembly with Bootstrap and a FastAPI service plus worker.
- Add anonymous bearer sessions, ownership checks, request limits, private source storage, and Redis-backed jobs using the atomic admission/finalization protocol in [architecture.md](architecture.md).
- Add upload/paste validation, scan-before-parse handling, ingestion status, and source viewing.
- Implement absolute expiry, cancellation, deletion, and cleanup monitoring before accepting real user documents.
- Add injected-failure checks before/after queue commit, duplicate concurrent submissions, deleted/expired parent records, stale worker attempts, and storage writes arriving after cleanup. Enforce budgets before dispatching any AI work.

Exit: two sessions cannot access each other's documents/jobs. One accepted request produces one logical operation and queue admission; replay after a lost HTTP response recovers it. Deletion and worker finalization are safe in either order, and interrupted admission/retries resolve without stuck keys, duplicate capacity charges, or orphaned private data.

### 2. Explain and extract actions

- Preserve page provenance while chunking and indexing.
- Extract facts across all readable pages, then synthesize the explanation.
- Return typed, schema-validated sections with evidence and readable/partial/unreadable coverage information. Partial results leave `not_stated` empty and explain uncertainty about missing facts.
- Preserve “must,” “may,” exceptions, amounts, and relative-deadline wording.
- Build the explanation view, action checklist, and source citation navigation.

Exit: the evaluation fixtures produce complete or explicitly partial results; the searchable-heading/scanned-body case never reports complete coverage or a definitive missing deadline. Unsupported claims and fabricated citations are blocked.

### 3. Add document-grounded questions

- Retrieve within the authorized document before calling the model.
- Cite exact passages; return insufficient evidence or conflicting evidence when appropriate.
- Add provider timeouts, bounded retry behavior, per-session budgets, and safe error messages.
- Show the answer beside its source and offer a redacted accuracy-report path.

Exit: answerable, unanswerable, ambiguous, adversarial, and cross-session cases pass the agreed evaluation set.

### 4. Deliver the interactive 3D workspace

- Build the bounded page stack, page picking, spread/stack and reset controls, Explore/Read transition, and existing evidence/action views described in [design.md](design.md).
- Share one selected page/evidence state between Blazor controls, the DOM/PDF viewer, and Three.js. Keep question input, reading text, and checkboxes usable without waiting for animation.
- Generate private thumbnails in memory, virtualize neighboring pages, and preserve partial-page labels in both 3D and flat views.
- Add keyboard and tap alternatives for dragging, reduced motion, mobile activation, WebGL/context-loss fallback, and adaptive scene quality.
- Exercise deletion/expiry during animation and texture loading, renderer disposal, hidden-tab suspension, and repeated view changes on the recorded representative devices.

Exit: real page picking and citation selection resolve to the same source span in Explore, Read, and the flat navigator. Desktop/mobile interaction meets the measured budgets agreed from the spike; all tasks work with keyboard/tap alternatives and reduced motion, and deleted content cannot reappear through a late scene callback.

### 5. Validate and release a controlled beta

- Exercise keyboard, screen-reader, small-screen, zoom, and low-bandwidth flows.
- Test malicious PDFs, prompt injection, cost exhaustion, cancellation races, and provider outages.
- Run the crash/replay/deletion ordering matrix and partial-page extraction fixtures against the deployed stack; verify scene fallback and resource cleanup on actual devices.
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
| A selectable heading sits above an image-only deadline | Mark that page partial; do not report the deadline as absent or coverage as complete |
| The API process stops before admission commits | No accepted operation, queue entry, quota charge, or permanent idempotency claim; unused staged input is cleaned up |
| The API process stops after commit but before returning `202` | Replaying the key returns the original operation without another admission |
| Deletion races with worker completion | Delete-first rejects publication; complete-first is removed by deletion; old attempts cannot recreate data |
| A citation is selected in the 3D workspace | Explore, Read, and the flat navigator identify the same document/page/span |
| WebGL fails or a document expires during texture loading | Flat access remains usable when authorized; expired content and late textures are discarded |

## Quality and release gates

Use at least 30 synthetic or permitted documents and 100 reviewed questions, including negative cases. Keep document-level train/development and held-out evaluation splits; never tune prompts on the held-out set. Initial thresholds are targets to validate, not achieved results.

- 100% of emitted citations resolve to exact text in the correct authorized document and page.
- At least 95% of reviewed factual claims are supported by their cited evidence; assess entailment separately from citation validity.
- At least 95% recall for critical stated deadlines, fees, required documents, and eligibility conditions in the labeled evaluation set.
- At least 95% correct abstention on questions whose answers are absent; report sample counts and ambiguous cases.
- Zero fabricated dates/amounts and zero cross-session disclosure in the release test set. Any occurrence blocks release.
- Full keyboard operation, readable source text, and WCAG 2.2 AA checks for the critical journey.
- Deletion/expiry tests cover API data, storage, queue registries, caches, and late worker writes.
- Injected admission/finalization failures prove replay safety, bounded recovery, current-attempt enforcement, and exactly-once capacity release; external provider execution/billing is not assumed exactly once.
- No known partial/unreadable page is labeled complete, and incomplete coverage never generates a definitive `not_stated` claim. Include the mixed-content single-page fixture in the release set.
- Interactive 3D is delivered, including source-state synchronization, keyboard/tap alternatives, reduced motion, context-loss/low-performance fallback, and resource cleanup. A concept image or hover tilt does not satisfy this gate.
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
| Work is accepted or published inconsistently after a crash/delete | Transactional admission, guarded finalization, fixed logical operation IDs, and injected-failure checks |
| A page has both readable and unreadable content | Per-page partial status, conservative extraction checks, persistent coverage warnings, and no absence claims |
| 3D integration or phone performance blocks delivery | Phase 0 proof, an explicit Phase 4 milestone, on-device budgets, and equivalent flat controls |

The repository maintainer owns these decisions until roles are assigned. Track implementation work with the [GitHub issue templates](.github/ISSUE_TEMPLATE); templates become available after the files reach a GitHub repository's default branch, following [GitHub's template configuration guidance](https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/configuring-issue-templates-for-your-repository).

## Documentation map

[AI declaration](ai-declaration.md) defines responsible AI practice. [Design](design.md) defines user journeys and interface behavior. [Architecture](architecture.md) defines system boundaries. [AGENTS.md](AGENTS.md) guides contributors and coding agents. [Security](security.md) defines protections and disclosure. [API](api.md) and the generated OpenAPI define the wire contract.
