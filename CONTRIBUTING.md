# Contributing to StoryForge

Thanks for helping out. StoryForge is a local-first, open-source story generator: a FastAPI backend, a multi-agent LLM pipeline, and a Next.js UI. Bug fixes, features and docs are all welcome.

## Prerequisites

- Python 3.11+ (Docker and CI use 3.12)
- Node.js 24 (for `frontend/`)
- Git
- Docker (optional, only to run the packaged stack)

## Setup

```bash
git clone https://github.com/<your-username>/STORYFORGE.git
cd STORYFORGE

# Python: create a venv, then install runtime + test dependencies
python -m venv .venv
source .venv/bin/activate          # Windows Git Bash: source .venv/Scripts/activate
pip install -r requirements.txt -r requirements-test.txt
# Linux: append --extra-index-url https://download.pytorch.org/whl/cpu to get the
# CPU-only torch wheel instead of the multi-GB CUDA build.
# or with uv: uv venv && uv pip install -r requirements.txt -r requirements-test.txt

# Frontend
cd frontend && npm ci && cd ..

cp .env.example .env               # then add your LLM API key (or set it in the UI)
```

CI and the Docker image install from the pinned `requirements.lock.txt`. It is compiled for Linux x86_64 and Python 3.12 (it does not install on Windows or macOS); on Linux you can use it to reproduce CI exactly (it needs `--extra-index-url https://download.pytorch.org/whl/cpu`). CI checks that it stays in sync with `requirements.txt`; after changing `requirements.txt`, regenerate it with the `uv pip compile` command in its header.

## Running it

- **Both services, one command:** `python scripts/dev.py` starts the API (`app.py`, default `:7860`, debug on) and `npm run dev` (default `:3001`) with `[api]` / `[web]` prefixed logs. Flags: `--api-port`, `--web-port`.
- **Backend only:** `python app.py`.
- **Docker:** `docker compose up` builds both images from this checkout and serves the UI at http://localhost:3001.

Runtime state lives under `data/` (SQLite DB, `config.json`, caches, `data/logs/storyforge.log`) and `output/`.

## Checks CI runs

Run these before opening a PR (Python commands from the repo root with the venv active):

```bash
ruff check .
python -m pytest -q -m "not calibration and not bench and not perf"

cd frontend
npx tsc --noEmit
npx eslint .
npx vitest run
```

CI also runs `pip-audit`, `npm audit --omit=dev --audit-level=high` and `docker compose build`. Pytest enforces a coverage floor (`--cov-fail-under=75` in `pyproject.toml`) and blocks real network access in tests, so mock LLM calls. Run a single test with `python -m pytest tests/test_foo.py -k name --no-cov`.

## Code style

- Linter: ruff (`ruff check .`); configuration is in `pyproject.toml`.
- Type hints on public function signatures; docstrings on public classes and functions.
- Keep files focused. There is no hard line limit, but split modules that grow several responsibilities.
- Keep `api/` handlers thin; put logic in `services/` or `pipeline/`.
- Follow the naming already used in each directory (snake_case modules).
- Every bug fix starts with a test that fails on the old code. Do not delete a behavior test to get green.

See `docs/code-standards.md` for more detail.

## Commits and pull requests

Use [Conventional Commits](https://www.conventionalcommits.org/): `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`, `ci:`.

```
fix: handle empty chapter text in quality scorer
```

PR checklist:

- [ ] One focused change; branch named `feat/...` or `fix/...`
- [ ] Tests added or updated
- [ ] `ruff check .`, the pytest command and the frontend checks above pass
- [ ] Docs updated if behavior, config or architecture changed (see `ARCHITECTURE.md`)
- [ ] No secrets, personal paths or generated output committed
- [ ] PR description links the issue (`Closes #123`)

## Directory map

| Directory | Responsibility |
|:----------|:---------------|
| `api/` | FastAPI routers (thin handlers), session endpoints, SSE/WebSocket |
| `pipeline/` | Generation engine: `orchestrator.py`, `layer1_story/`, `layer2_enhance/`, `agents/`, `semantic/` |
| `services/` | LLM client and providers (`llm/`), exporters, media, quality scoring, SQLite/infra (`infra/`) |
| `middleware/` | Hosts allow-list, access token, CSRF, body limit, rate limit, sanitization, audit, metrics |
| `config/` | `ConfigManager`, defaults, presets |
| `models/` | Pydantic schemas shared across layers |
| `errors/` | Exception types and handlers |
| `frontend/` | Next.js 16 / React 19 UI (see `frontend/AGENTS.md`) |
| `docker/`, `compose*.yaml` | Container images and compose files |
| `scripts/` | Dev launcher and maintenance scripts |
| `tests/` | pytest suite; `frontend/tests/` and `*.test.ts` for the UI |
| `docs/` | Architecture, standards, ADRs |

Dependencies between layers are by convention, not enforced: `api/` calls into `services/` and `pipeline/`; `pipeline/` uses `services/` (LLM client, config); avoid `services/` and `pipeline/` importing `api/`.

## Getting help

Open a [GitHub Discussion](https://github.com/HieuNTg/STORYFORGE/discussions) for questions or ideas, and look for the `good first issue` label. Be respectful; we follow the [Contributor Covenant](https://www.contributor-covenant.org/).
