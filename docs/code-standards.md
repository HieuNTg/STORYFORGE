# Code Standards

Conventions for StoryForge contributors. Setup, checks and the PR checklist are in `CONTRIBUTING.md`; the system layout is in `ARCHITECTURE.md`.

## Tooling

- Python 3.11+ (`requires-python` in `pyproject.toml`), linted with `ruff check .` (rules and line length 120 are in `pyproject.toml`).
- Frontend: TypeScript, `npx tsc --noEmit`, `npx eslint .`, `npx vitest run` in `frontend/`.
- There are no pre-commit hooks. CI (`.github/workflows/ci.yml`) is the gate, so run the checks locally before pushing.

## Python

| Element | Style | Example |
|---------|-------|---------|
| Modules, functions, variables | snake_case | `llm_cache.py`, `score_chapter` |
| Classes | PascalCase | `StoryGenerator` |
| Constants | UPPER_SNAKE_CASE | `OUTPUT_ROOT` |
| Private | leading underscore | `_instance` |

- Type hints on public function signatures; docstrings on public classes and functions.
- Imports: standard library, third-party, then local, separated by blank lines.
- No fixed file-length limit. Split a module when it takes on more than one responsibility.
- No magic numbers; name the constant.
- Use specific exceptions from `errors/` and chain with `raise ... from e`. Never log secrets.

## Design rules

1. **Thin API layer.** Route handlers validate input (Pydantic) and call `services/` or `pipeline/`; they hold no business logic.
2. **Layers.** `api/` calls `services/` and `pipeline/`; `pipeline/` uses `services/` (LLM client, config). Do not import `api/` from `services/` or `pipeline/`. This is convention, not enforced by tooling, so check in review.
3. **Stateless agents.** Agents in `pipeline/agents/` receive their context as arguments.
4. **Config.** Read settings through `ConfigManager`. Inside a run it returns the run's snapshot; do not cache config values across runs. Threads and tasks started during a run must go through `services/llm/run_context.py` (`run_in_thread`, `spawn_with_context`, `submit_with_context`).
5. **LLM calls** go through `services/llm/client.py` so retry, fallback, caching and cost accounting apply.
6. **Persistence** is SQLite (`services/infra/db_paths.py`) and files under `data/` and `output/`. No external database or cache services.
7. **Config flags** default to off for new features and are removed when dead.
8. **Prompts and quality thresholds** are not changed as a side effect of other work.

## Tests

- Python tests live in `tests/` as `test_<module>.py`; frontend tests sit next to the code as `*.test.ts(x)` or under `frontend/tests/`.
- Mock all LLM and network calls. Pytest blocks real network access (`--disable-socket`, localhost allowed) and fails any test over 120 s.
- Coverage floor is 60% (`--cov-fail-under=60`), set in `pyproject.toml`.
- Every bug fix starts with a test that fails on the old code. Do not delete a behavior test to get green.
- Slow suites use markers (`calibration`, `bench`, `perf`) and are excluded from the default run: `python -m pytest -q -m "not calibration and not bench and not perf"`.

## Security

1. Validate inputs with Pydantic schemas.
2. Keep secrets in `.env` or `data/` (never committed); the UI only ever receives masked keys (see `docs/frontend-security.md`).
3. CORS uses an explicit allow list (`STORYFORGE_ALLOWED_ORIGINS`); unknown Host headers are rejected (`STORYFORGE_ALLOWED_HOSTS`).
4. State-changing requests need the CSRF double-submit token; `/docs`, `/redoc` and `/openapi.json` exist only with `STORYFORGE_DEBUG=1`.
5. Do not reorder middleware without updating `tests/test_middleware_order.py`.

## Deprecation

Emit a `DeprecationWarning` with a migration path, note it in `CHANGELOG.md`, and remove it in the next major version.

## Documentation

Update `ARCHITECTURE.md` when layout, flow, middleware or config change. Record significant design decisions as ADRs in `docs/adr/`.
