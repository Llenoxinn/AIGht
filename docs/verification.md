# Initial v1.0.0 verification — 3 November 2026

This is a record of local checks, not a beta approval or production security assessment.

| Check | Observed result |
| --- | --- |
| Blazor/.NET build | Succeeded; zero warnings/errors |
| Python/API tests | 22 passed, 2 skipped; one upstream Starlette warning about its future HTTP client migration |
| JavaScript module syntax | `node --check` passed |
| OpenAPI | Exported from implemented typed models |
| Git whitespace | `git diff --check` passed |
| Compose configuration | `docker compose --env-file .env.example config --quiet` passed; no containers started |
| Browser: example | Loaded the real synthetic five-page PDF and prepared explanation |
| Browser: citations | Citation selected the matching page and highlighted the exact canonical source text |
| Browser: original PDF | PDF.js rendered the original source page |
| Browser: checklist / Q&A | Checkbox state survived tool changes; prepared question returned a clearly labeled answer |
| Browser: navigation | Flat selection and Read used the same page; actual 3D raycast picking changed the Blazor page number; spread/stack controls responded |
| Browser: mobile | 390×844 view used the automatic flat fallback; layout was visually inspected |

Lifecycle tests exercise owned/foreign access, fixed expiry and stale attempts, delete-before/after completion, admission replay and concurrency, pre-commit failure, lost acknowledgement recovery, quotas/budgets, complete text ingestion→analysis→question, and cleanup of source/content/jobs plus late candidates and interrupted staging. Parser tests use actual synthetic PDFs, including a searchable heading over an image body. Provider behavior in these tests is deterministic fixture data, not a live model.

The two locally skipped checks require Linux Landlock/libseccomp and a dedicated real Redis. CI is configured to run them on Linux with Redis; CI has not been run remotely in this session. Docker Desktop could not start because Windows reported insufficient paging-file capacity. Browser automation also encountered transient resource failures; the successful checks above were observed after recovery. This is not a physical-device performance benchmark.

Not checked: a live OpenAI model/account, actual provider retention settings, adversarial/entailment evaluation, container builds and end-to-end PDF ingestion through ClamAV, representative-device frame times/memory, assistive technologies, production TLS/storage/network controls, load/restart tests, and a deployed environment. These remain release gates. Real processing is disabled by default until actual provider and privacy configuration is supplied.
