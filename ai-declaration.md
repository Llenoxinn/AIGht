# AIGht AI Declaration

Status: initial project declaration, 2 November 2026. This describes intended practice; it is not evidence of an implemented or audited system.

## Purpose

AIGht — “AIght, Alright!” — helps people understand complicated documents and decide what to check or do next. AI supports explanation and extraction; the original document remains the authority.

The product should answer four questions:

1. What does this document mean?
2. How might it affect me?
3. What do I need to do?
4. What should I pay attention to?

## AI use in development

This initial documentation set was drafted with OpenAI Codex from the project owner's brief. It contains proposed product, design, architecture, security, and API decisions. Application code, model integrations, deployment, and production verification are not part of this documentation delivery.

Maintainers remain responsible for reviewing AI-assisted work before merging or releasing it. Contributions should disclose material AI assistance in their pull request, including affected areas, verification performed, and unresolved limitations. Never claim a human review, test result, security assessment, or model capability that did not occur.

Do not submit private documents, credentials, personal information, or proprietary source material to a development AI service without appropriate authorization. Use synthetic or explicitly permitted fixtures.

## AI use in the product

| Capability | Intended AI role | Required safeguard |
| --- | --- | --- |
| AIght, Explain! | Explain document content in plain language | Preserve qualifications, exceptions, quantities, and source citations |
| AIght, What Now? | Extract requirements, deadlines, fees, eligibility, and actions | Separate stated requirements from suggested next steps |
| AIght, Ask! | Answer a question using retrieved document passages | Cite supporting passages; abstain when evidence is insufficient |
| AIght, Watch Out! | Later: flag clauses or uncertainties worth checking | Explain the reason; avoid unsupported legal judgments |
| AIght, Compare! | Later: explain changes between document versions | Show the original and revised passages |

English explanations are the MVP output. Filipino and Cebuano support require their own evaluations before release. OCR, comparison, and advanced clause analysis are also outside the MVP.

## Grounding and uncertainty

- Retrieve evidence only from the active document owned by the current session.
- Keep source text distinct from system instructions. Instructions embedded inside uploaded documents are untrusted content.
- Validate citation locations and exact quotations on the server. A valid quote alone does not prove that the explanation follows from it; evaluate that separately.
- Explain missing information and conflicting clauses. Never invent a missing date, fee, grading convention, eligibility rule, or legal conclusion.
- Preserve relative deadlines as relative rules. Do not calculate a calendar date without the necessary trigger date and counting rules.
- Distinguish “this grade meets the stated condition” from “you qualify for the scholarship.”
- Show a clear failure or partial-result state when extraction or evidence checks fail.

RAG reduces reliance on unsupported model recall. It does not guarantee accuracy or eliminate prompt injection.

## User-facing disclosure

Before upload, disclose that document content will be processed by AI, identify the selected providers and their retention terms, and explain the session lifetime and deletion controls. Record agreement to the current processing notice without treating that agreement as blanket permission for unrelated use.

Suggested result disclosure:

> AI-generated explanation. Check the cited passages before acting. AIGht can miss details and does not replace advice from a qualified professional.

This notice supplements accurate behavior and source access; it does not excuse unsupported answers. AIGht must never present an AI response as an official decision by a school, government agency, employer, or other document issuer.

## Data use and accountability

- Do not use uploaded documents, questions, embeddings, or answers to train models by default.
- Select provider settings and terms that support the published data-use policy; do not promise zero provider retention without verification.
- Apply the retention and deletion rules in [security.md](security.md) to all application-controlled copies.
- Keep provider and model identifiers, prompt version, retrieval version, and evaluation results available to maintainers without logging document contents.
- Provide a way to report an incorrect explanation using a redacted example. Route vulnerabilities through private reporting.
- Re-evaluate material model, prompt, parser, or retrieval changes before release.

The repository maintainer is accountable for approvals until named product, engineering, and security owners are assigned. No compliance certification, accuracy percentage, or independent audit is claimed.

## Related documents

[Plan](plan.md) · [Design](design.md) · [Architecture](architecture.md) · [Agent instructions](AGENTS.md) · [Security](security.md) · [API](api.md)
