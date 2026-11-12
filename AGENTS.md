# StoryForge - Working agreement for AI coding agents

StoryForge is a local-first AI story generator: FastAPI backend, a two-layer multi-agent LLM pipeline, and a Next.js 16 / React 19 UI. Read `ARCHITECTURE.md` for the layer map, flow and middleware order; read `CONTRIBUTING.md` for setup and the PR checklist. UI work: also read `frontend/AGENTS.md`.

## Navigating the code

The repo has roughly 120 files in `pipeline/layer1_story` + `layer2_enhance`, 120+ in `services/`, and 250+ test files. Do not blind-read it.

- Search first (`rg`, `git grep`, or a symbol-aware tool such as Serena if you have it, which is optional).
- Before changing a function or class, find every caller and import. Do not refactor without that list.
- For layers, flow and component relationships, use `ARCHITECTURE.md`.

## Pipeline in one paragraph

API route -> `PipelineOrchestrator` (`pipeline/orchestrator.py`) -> Layer 1 `StoryGenerator` (`pipeline/layer1_story/generator.py`, 75 files) -> checkpoint -> Layer 2 `StoryEnhancer` / `DramaSimulator` (`pipeline/layer2_enhance/`, 27 files) -> exporters / media. The L1 -> L2 handoff uses the schemas in `models/schemas.py` (`StoryDraft`, `PipelineOutput`) and `models/handoff_schemas.py` (`L1Handoff` envelope), persisted as checkpoint files under `output/` (SQLite for app state). Eight debate agents live in `pipeline/agents/`. Post-write repair lives in `pipeline/layer1_story/repair/` (see `ARCHITECTURE.md`).

Do not change prompts, quality thresholds or the L1/L2 generation flow as a side effect of unrelated work.

## Commands

Python commands assume an activated venv (`source .venv/bin/activate`, or `.venv/Scripts/activate` on Windows Git Bash). Frontend commands run in `frontend/`.

```bash
python scripts/dev.py                 # API :7860 + web :3001, prefixed logs
python app.py                         # backend only
docker compose up                     # packaged stack, UI at http://localhost:3001

ruff check .
python -m pytest -q -m "not calibration and not bench and not perf"
python -m pytest tests/test_x.py -k name --no-cov      # one test

cd frontend && npx tsc --noEmit && npx eslint . && npx vitest run
```

Pytest blocks real network access (mock LLM calls), enforces a 60% coverage floor and a 120 s per-test timeout.

## Conventions and gotchas

- Conventional Commits (`feat:`, `fix:`, `docs:` ...). One focused change per commit.
- Every bug fix starts with a test that fails on the old code. Never delete a behavior test to get green.
- `api/` handlers stay thin; logic goes in `services/` and `pipeline/`.
- Config: `ConfigManager` (`config/config.py`). Inside a pipeline run, `ConfigManager()` returns that run's snapshot, so per-run overrides do not leak between runs. Code that starts threads or tasks during a run must use `services/llm/run_context.py` (`run_in_thread`, `spawn_with_context`, `submit_with_context`) so the run's config and cost wallet follow it.
- Data lives under `data/` (`storyforge.db`, `config.json`, `.secret_key`, caches, `logs/storyforge.log`); generated stories under `output/`. SQLite only; paths come from `services/infra/db_paths.py` (`STORYFORGE_DB_PATH`).
- Defaults: API `127.0.0.1:7860`, UI on host port `3001`. Allowed Host headers: `localhost`, `127.0.0.1`, `[::1]`, `api`, `host.docker.internal`; extend with `STORYFORGE_ALLOWED_HOSTS`.
- Optional access token: `STORYFORGE_ACCESS_TOKEN` plus the `sf_session` cookie (`middleware/access.py`, `api/session_routes.py`). `/docs`, `/redoc`, `/openapi.json` exist only with `STORYFORGE_DEBUG=1`.
- Middleware order is pinned by `tests/test_middleware_order.py`; read `app.py` `create_app` before adding or moving one.
- There are no Redis, Postgres, Alembic, multi-user auth or versioned (`v1`) API layers; do not reintroduce them.
- Never commit secrets, `.env`, runtime files under `data/` (DBs, `config.json`, `.secret_key`, logs, caches; the shipped `data/prompts`, `data/evals`, `data/templates` are tracked) or personal absolute paths.
- Frontend is Next.js 16 and React 19; APIs differ from older versions, so check `frontend/AGENTS.md` and the installed docs before writing UI code.
