# AIGht Security and Privacy Plan

Status: v1.0.0 implementation requirements, 3 November 2026. Ownership, fixed expiry, guarded publication, bounded admission, cleanup, schema/evidence validation, and a fail-closed Linux parser sandbox are implemented. Local tests cover selected invariants; container/runtime, live-provider, adversarial, load, and deployment checks remain beta gates. This is not a security audit, a deployed privacy notice, or a claim of legal compliance. No public production release or support schedule exists yet.

The parser subprocess receives a scrubbed environment, resource limits, a Landlock allowlist for one source file plus installed runtime files, and seccomp denial of network/process creation. Its stdout is a bounded file rather than an unbounded captured pipe. The local Compose stack adds an unprivileged user, dropped capabilities, read-only runtime filesystems, and private document storage. These controls require Linux runtime verification before enabling PDFs. Application cleanup scans files and Redis independently every 15 seconds, including orphaned candidates written after an earlier file sweep. The 15-minute cleanup target must still be measured with failures and restarts.

## Reporting a vulnerability

Do not include vulnerabilities, credentials, private document contents, or personal information in public issues.

Once a GitHub repository is configured, use its **Security → Report a vulnerability** route if private vulnerability reporting is enabled; see [GitHub's private reporting instructions](https://docs.github.com/en/code-security/how-tos/report-and-fix-vulnerabilities/report-privately). The repository owner must enable that feature or publish a monitored private security contact before the beta accepts real documents. No address or repository URL is invented here.

If neither route is available, request a private reporting channel without sharing technical details or sensitive evidence. Maintainers should acknowledge reports within three business days as an initial operating target, provide a next update date, and coordinate disclosure after a fix. This is a proposed response target, not an existing support guarantee.

Provide the affected version/environment, reproducible steps with synthetic data, impact, and a safe proof of concept privately. Avoid downloading other users' documents or causing unnecessary disruption while demonstrating a problem.

Only the latest deployed beta is planned for fixes. Publish concrete supported versions when releases exist. [.github/SECURITY.md](.github/SECURITY.md) exposes this policy through GitHub's standard location.

## Assets and trust boundaries

Protect original documents, extracted text, metadata, filenames, embeddings, questions, answers, action lists, access tokens, and provider credentials. Derived AI data can be as sensitive as the source.

Trust boundaries include browser-to-API, upload-to-parser, API-to-Redis/storage, queue-to-worker, worker-to-model-provider, and maintainer-to-production systems. Anonymous sessions provide temporary authorization, not verified identity or durable account recovery.

| Threat | Required protection | Verification |
| --- | --- | --- |
| Another session requests a document/job/source | Ownership check on every access; opaque IDs alone are insufficient | Two-session negative tests across all endpoints |
| Malicious or resource-heavy PDF | Layered type validation, scanning, isolated parser, bounded resources | Corrupt, encrypted, embedded-content, and resource-exhaustion fixtures |
| Instructions hidden in source material | Treat source as data; scoped retrieval; no model tools or execution | Direct/indirect injection evaluations |
| Stored/reflected script content | Default text escaping, restricted Markdown, safe viewer and CSP | HTML/script payloads in filename, text, and model output |
| Stolen or logged bearer token | HTTPS, in-memory token, no token URLs/logging, short fixed lifetime | Log inspection, browser storage inspection, expiry tests |
| AI cost or queue exhaustion | Session/IP/global quotas, concurrency, token and spend ceilings | Budget and repeated-session abuse tests |
| Deleted data returns through a worker/cache | Atomic revocation and guarded generation/attempt publication; independent cleanup | Delete-first, complete-first, stale-attempt, and restart tests |
| A crash separates accepted work from queue admission | Commit operation, idempotency response, reservations, and RQ admission together | Crash before commit, lose the response after commit, replay the key |
| Secrets/dependencies compromised | Least privilege, pinned dependencies, secret scanning, patch process | CI checks and deployment review |

## Session authorization and browser controls

- Generate bearer tokens from at least 32 cryptographically random bytes. Store only a digest and compare safely.
- A session expires exactly 60 minutes after creation; activity never extends it. Every resource inherits that expiry.
- Keep tokens only in page memory. No access tokens in local/session storage, cookies, query strings, analytics, or error reports. A page refresh loses access; the server still expires and deletes the data.
- Authorize by server-side ownership before lookup, retrieval, download, status, cancellation, or result publication. Return `404` for resources that are absent, belong to another session, or have been deleted.
- Missing, invalid, revoked, or expired session credentials return the same `401` category. Never expose another session's existence through error details.
- Allow only configured frontend origins. CORS is not authorization. Do not use wildcard credentialed CORS.
- The MVP uses explicit Authorization headers rather than ambient cookies. If cookie authentication is introduced later, add a CSRF design before shipping it.
- Use HTTPS, appropriate HSTS, `nosniff`, a restrictive referrer policy, and a tested CSP compatible with the pinned Blazor/PDF viewer runtime. Do not weaken policy with broad wildcards to fix integration errors.
- Disable CDN/service-worker/browser caching of private API data with `Cache-Control: no-store`. Avoid third-party analytics/session replay on document screens.

## Upload and processing safeguards

Accept PDF files through the file endpoint and pasted text through the text endpoint. Do not accept URLs, archives, office files, or arbitrary remote fetch instructions in the MVP.

Enforce 10 MiB per PDF, 50 pages, 300,000 extracted Unicode code points, 100,000 pasted code points, five document creations per session, and two outstanding operations per session. Account for multipart envelope overhead separately from the file limit. Reject excessive decompressed/parser output even if the compressed input is small.

Use extension, MIME, signature, and actual parser checks together. Do not trust the submitted Content-Type or filename. Use generated storage keys, reject path traversal, scan before parsing, reject encrypted PDFs, and run parsing without network access or executable document actions. A clean scan does not replace isolation or resource limits. These are layered controls consistent with [OWASP's file upload guidance](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html).

Keep source storage private. Serve authorized originals with a fixed media type and safe content disposition; preview through a maintained viewer, without executing PDF JavaScript or opening embedded attachments. Downloads require the same authorization and expiry checks as metadata. Never embed a user's upload into the trusted application origin as executable HTML.

Queue payloads contain registered task names and IDs only. Configure RQ producers/workers for JSON, restrict Redis to trusted services, sanitize failure handling, and override long default failure/result retention. Do not leak source text or provider payloads through job tracebacks.

## AI-specific protections

RAG does not eliminate prompt injection; [OWASP describes the remaining risk](https://genai.owasp.org/llmrisk/llm01-prompt-injection/). Treat hidden text, quoted commands, and retrieved passages as untrusted input.

- Send only the current document's bounded evidence or necessary extraction batches to the selected provider.
- Provide no model access to shell commands, browsing, file paths, service credentials, external actions, or other users' resources.
- Separate system instructions, user questions, and source passages structurally. Never put secrets into a model prompt.
- Validate structured output, exact source spans, and reference ownership before displaying it. Render generated content as escaped text or a tightly restricted Markdown subset.
- Evaluate whether a cited passage actually supports the claim. Return insufficient/conflicting evidence when appropriate.
- Put hard input/output-token ceilings, timeouts, retries, and total-spend controls outside the model's discretion. Reserve budget before dispatch to avoid concurrent overrun.
- Do not let a document authorize API calls, change retention, select a different session, or override these rules.

## Data lifecycle

| Data | Application retention | Deletion handling |
| --- | --- | --- |
| Original PDF/pasted source | Until session expiry or explicit deletion, whichever comes first | Revoke immediately; remove private storage and temporary parser files |
| Extracted text, chunks, embeddings | Same deadline as source | Delete indexes, metadata, caches, and worker scratch data |
| Analyses, questions, answers | Same deadline as source/session | Delete operation results and scoped caches |
| Queue arguments, results, failure records | Bounded by session lifetime; IDs only in arguments | Cancel work and clean job/retry/registry entries |
| Token digest and session metadata | Until expiry/revocation, with minimal cleanup tombstones if necessary | Never retain source content in tombstones |
| Content-free operational logs | Initial maximum: 14 days | Automatic rotation; access limited to maintainers |
| Rate-limit counters | No longer than 24 hours | Expire counters; minimize/hash network identifiers where feasible |
| Provider-side content | Depends on selected provider and contract | Publish actual retention/deletion capabilities before processing is enabled |

Authorization blocks access immediately on deletion/expiry. The cleanup target for application-controlled live copies is 15 minutes; monitor failures and sweep independently of Redis. Object lifecycle rules are a backstop, not the only deletion mechanism. Use deterministic storage prefixes and creation/expiry metadata to find orphans after a crash.

Late workers must check ownership, generation, cancellation, current attempt, and absolute expiry inside the same atomic operation that publishes output. A check followed by an independent write is insufficient. Apply the [admission and finalization protocols](architecture.md#atomic-admission): accepted work and its queue admission commit together; deletion revokes the generation/session atomically. If deletion wins, no result/index/callback may recreate missing parents; if completion wins, deletion removes its published content. Retry/failure callbacks use the same guards and release reserved capacity at most once.

Private candidate artifacts outside Redis carry session/document/attempt/expiry metadata, remain inaccessible until a guarded reference is published, and are swept after rejected publication, crashes, or late writes. RQ stores content-free completion values; application-controlled results follow the guarded lifecycle. Test recovery for uncertain transaction outcomes rather than treating an orphaned operation or idempotency key as accepted work. Provider calls may execute again after a crash, so retry/spend policies must cover that possibility.

Disable content-bearing backups and object versioning for ephemeral storage where possible. If a provider/host necessarily retains copies, publish the actual retention boundary and review suitability before accepting real documents. Do not promise immediate physical removal from infrastructure outside application control.

Closing a tab is not reliable server-side deletion. Offer explicit “Delete document” and “End session” controls and explain the remaining fixed expiry. Do not use uploads, questions, answers, or embeddings for model training or unrelated analytics by default.

## Secrets and operations

- Keep provider/storage credentials in a secret manager or server environment; use a redacted `.env.example` only after configuration exists.
- Never commit `.env`, keys, real user documents, Redis dumps, request captures, or unredacted production logs.
- Use separate development/production credentials, least-privilege storage roles, private Redis networking, TLS where supported, and protected maintainer access.
- Remove user content from access logs, model SDK tracing, crash reports, and queue exceptions. Verify vendor SDK defaults explicitly.
- Pin dependencies and images, review licenses, scan for secrets/vulnerabilities, and apply security updates through meaningful regression checks.
- Treat Redis loss as session invalidation, not an invitation to restore old private sessions. Sweep orphaned files.
- Reject new work when safe storage, authorization, scanning, quotas, or provider configuration is unavailable. Preserve source access only where its authorization remains verifiable.

## Before beta

Release requires evidence of ownership isolation, malformed-file handling, prompt-injection resistance, citation validation, XSS protection, rate/cost limits, fixed expiry, atomic admission/finalization, crash/replay and deletion ordering, stale-attempt rejection, late-artifact cleanup, log redaction, and dependency review. Verify that partial source pages never produce complete coverage or unsupported absence claims. Exercise document revocation while the 3D viewer is animating or loading textures; late callbacks must discard the private content. These are release requirements, not implemented or audited protections yet.

Select actual processors and hosting regions, publish a plain-language processing notice, and review privacy obligations for the intended users and jurisdictions. If minors or sensitive document categories are in scope, resolve the appropriate handling before inviting uploads. Agreement to a notice alone is not a claim that every legal obligation is satisfied.

If an incident is suspected, stop affected processing, contain access, rotate exposed credentials, preserve minimal necessary evidence under restricted access, assess affected records, remediate, and communicate through the approved incident process. Document any justified evidence-retention exception rather than silently abandoning the normal deletion policy.
