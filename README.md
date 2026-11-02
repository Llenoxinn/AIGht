# AIGht 1.0.0

Make complicated documents easier to understand: plain-English explanations, an action checklist, and questions backed by source passages. The Blazor workspace includes a real Three.js page stack, a flat navigator, and accessible source text.

This is the initial local implementation, not a published or beta-approved release. Real processing stays disabled until a provider, model, and actual processing notice are configured. The clearly labeled synthetic scholarship example works without an AI key.

## Run the workspace

The browser example needs only .NET SDK **10.0.403**. Python **3.13** and **uv 0.13.6** are needed for the backend. Node 24 is needed only to regenerate the committed frontend assets. Install tools from [Microsoft](https://dotnet.microsoft.com/download/dotnet/10.0) and [Astral](https://docs.astral.sh/uv/getting-started/installation/) when they are not already available.

In this development session the implementation and local tools are in `C:\Users\Dexter\.codex\worktrees\aight-v1\AIght`, separate from the original project folder. To run its browser example in PowerShell:

```powershell
Set-Location "C:\Users\Dexter\.codex\worktrees\aight-v1\AIght"
./scripts/dev.ps1 web
```

Open [localhost:5080](http://localhost:5080). Choose **Try a synthetic example**, then try Explain, What now?, Ask, source citations, page selection, spread/stack, Read, and flat view. Example answers are prepared demonstration content, never represented as a live AI response.

If the preview is already running, open that URL directly. Stop its existing terminal with Ctrl+C before starting another copy on port 5080.

For a fresh checkout, run `./scripts/dev.ps1 web` from its repository root after installing the .NET SDK. The ignored `.tools` directory is local to this development workspace and is not included in Git.

In a second terminal, set up and start the optional local API. This development workspace already has its Python environment; its local `uv.exe` works without adding `uv` to PATH:

```powershell
Set-Location "C:\Users\Dexter\.codex\worktrees\aight-v1\AIght"
& ./.tools/uv/uv.exe sync --frozen
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
./scripts/dev.ps1 api
```

On a fresh checkout with uv installed globally, use `uv sync --frozen` instead of the local executable command. The API advertises that real processing is unavailable with the blank `.env.example`. The launcher recognizes project-local `.tools/dotnet` and `.venv` installations.

## Run real document processing locally

Use Docker Desktop's Linux engine. Fill the blank provider/model/processing-notice fields in your untracked `.env` with actual deployment details. Never put a key in Blazor configuration. The configured chat model must support strict JSON schema output.

```powershell
docker compose up --build
```

This starts the static frontend, API, Redis, worker, independent cleanup process, and ClamAV. ClamAV's initial signature download can take several minutes. Source files use a private named volume; Redis is ephemeral and configured without persistence or eviction. Only localhost ports 5080 and 8000 are published. Stop the separately running preview first to free those ports.

PDF parsing requires Linux with **Landlock ABI 3+** and libseccomp. It fails closed if those restrictions cannot be installed. Native Windows development supports pasted text with a separately configured Redis and worker; PDF ingestion is disabled by default outside Compose. Do not enable PDF processing on a host until its sandbox check passes.

The Compose setup is for local development. Production still requires HTTPS, operator-owned privacy and security contacts, access-controlled/encrypted storage, outbound network controls, image digest pinning, capacity measurements, and the release checks in [plan.md](plan.md). No production deployment is configured.

## Check the implementation

```powershell
./scripts/dev.ps1 test
./scripts/dev.ps1 build
uv run python scripts/export_openapi.py
node --check src/AIGht.Web/wwwroot/js/document-space.js
```

Regenerate the synthetic PDF/JSON fixture with `uv run python scripts/create_demo.py`. Regenerate vendored assets with `npm ci --omit=optional` followed by `npm run assets` inside `src/AIGht.Web`. Asset versions/licenses are in [vendor/manifest.json](src/AIGht.Web/wwwroot/vendor/manifest.json).

Tests use synthetic data and a deterministic provider double. Most lifecycle checks use fakeredis with Lua support. CI also configures a dedicated real Redis and runs Linux sandbox denial checks; those checks skip locally when their required platform/service is absent. No test sends private documents or calls a live paid provider.

## Read the system design

- [Complete architecture and inputs/outputs](docs/diagrams/system-flow.md)
- [Architecture decisions and lifecycle invariants](architecture.md)
- [API narrative contract](api.md) and [generated OpenAPI](docs/openapi.json)
- [Design and interactive 3D direction](design.md)
- [Delivery and beta gates](plan.md), [security](security.md), and [AI declaration](ai-declaration.md)

Code boundaries: `src/AIGht.Web` owns the browser; `src/aight_api/main.py` owns HTTP; `store.py` owns admission/publication/authorization; `jobs.py`, `parser.py`, `processing.py`, and `provider.py` own the worker pipeline; `maintenance.py` owns expiry, cleanup, and abandoned-operation reconciliation.

Version 1 intentionally omits OCR, other output languages, comparison, accounts/history, advanced clause review, and overall eligibility decisions. Exact source matching establishes citation integrity; human-reviewed entailment and adversarial AI evaluations remain required before beta.
