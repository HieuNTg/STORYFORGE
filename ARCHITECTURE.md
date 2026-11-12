# StoryForge Architecture

StoryForge runs on one machine: a FastAPI backend (`app.py`, default `127.0.0.1:7860`) and a Next.js 16 / React 19 UI (`frontend/`, default `:3001`). The UI proxies `/api/*` to the backend (`API_ORIGIN` in `frontend/next.config.ts`; `http://api:7860` in Docker). State is SQLite plus files; there is no Redis, Postgres or multi-user auth.

## Top-level layout

```
api/            FastAPI routers, session endpoints, SSE/WebSocket helpers
app.py          create_app(): routers, middleware, error handlers, entry point
config/         ConfigManager (snapshot + run scope), defaults, presets, persistence
data/           Runtime files (gitignored): storyforge.db, config.json,
                .secret_key, llm_cache.db, embedding_cache.db, logs/storyforge.log.
                Shipped prompts/, evals/, templates/ are tracked.
docker/         api.Dockerfile, web.Dockerfile (compose.yaml, compose.release.yaml at root)
docs/           Code standards, frontend security/accessibility notes, ADRs
errors/         StoryForgeError types and handlers
frontend/       Next.js UI (own AGENTS.md)
middleware/     Hosts, trace id, body limit, security headers, CSRF, access, rate limit,
                sanitization, audit, metrics
models/         Pydantic schemas (schemas.py, handoff_schemas.py, narrative/voice/semantic)
output/         Generated stories, per-story checkpoints and exports
pipeline/       orchestrator*.py, layer1_story/, layer2_enhance/, agents/, semantic/
plugins/        Plugin extension points
scripts/        dev.py (dev launcher) and maintenance scripts
services/       llm/, infra/, pipeline/ (scoring, revision), media/, export/, prompts/ ...
tests/          pytest suite
mcp_server.py   Optional MCP (stdin/stdout) server exposing pipeline tools
```

Measured file counts (`git ls-files <dir> | wc -l`): `pipeline/layer1_story` 75, `pipeline/layer2_enhance` 27, `pipeline/agents` 15, `services` 122, `api` 28, `middleware` 12.

## Two-layer pipeline

`PipelineOrchestrator` (`pipeline/orchestrator.py`, split across `orchestrator_layers.py`, `orchestrator_checkpoint.py`, `orchestrator_continuation.py`, `orchestrator_export.py`, `orchestrator_media.py`) is the single entry point. Public methods include `run_full_pipeline()`, `run_layer1_only()`, `run_layer2_only()`, `continue_story()`, `export_output()` / `export_zip()`, `save_checkpoint()` / `resume_from_checkpoint()`.

### Layer 1: story generation (`pipeline/layer1_story/`)

`StoryGenerator` (`generator.py`) turns a title/genre/idea into a draft: theme and premise, characters and story bible, outline, scene decomposition and beats, chapter writing (batched, optionally parallel), plus validators for pacing, dialogue, timeline, plot threads and foreshadowing. Post-write repair (`repair/`) is one bounded loop instead of several independent full-chapter rewrites: a collector gathers findings (payoff, name, location, length, plus pacing, arc and critique as constraints), a planner builds one plan, and a single rewrite carries every constraint at once. The verifier is always a deterministic detector (word count, consistency validators, embedding-based payoff check), never an LLM grading its own prose. The candidate is kept only if it scores better than the original, otherwise it is reverted; when the budget is spent with findings left, the legacy passes run as a fallback. Config: `enable_agentic_repair` (on by default), `repair_max_rounds`, `repair_budget_calls`; kill switch `STORYFORGE_AGENTIC_REPAIR=0`.

A Layer 3 sensory polish pass (`pipeline/layer2_enhance/sensory_polish.py`, flag `enable_sensory_polish`, on by default) adds sensory detail to prose after L2 without changing plot or drama.

### Layer 2: enhancement (`pipeline/layer2_enhance/`)

`StoryEnhancer` (`enhancer.py`) refines the L1 output using `analyzer.py`, `simulator.py` (`DramaSimulator`), `thematic_tracker.py`, `voice_fingerprint.py`, `thread_watchdog.py`, causal/structural analysis, scene and dialogue polish, and `contract_gate.py`. `pipeline/agents/` holds eight debate agents (drama critic, editor in chief, continuity checker, character specialist, dialogue expert, dialogue balance, pacing analyzer, style consistency) coordinated by `debate_orchestrator.py` and `agent_graph.py`.

### Handoff and persistence

L1 to L2 data moves as `StoryDraft` / `PipelineOutput` (`models/schemas.py`) plus the typed envelope in `models/handoff_schemas.py` (`L1Handoff`, `NegotiatedChapterContract`, `ConflictWeb`, ...), validated by `pipeline/handoff_gate.py`. Checkpoints are files under `output/<story>/checkpoints/`.

```
User input -> API route -> PipelineOrchestrator
                             |-> StoryGenerator (L1) -> checkpoint
                             |-> DramaSimulator / StoryEnhancer (L2)
                             |-> MediaProducer (optional images)
                             '-> exporters (PDF, EPUB, Markdown, ZIP)
All LLM calls go through services/llm/client.py (providers, retry, fallback, cache).
```

## Per-run isolation

- `ConfigManager.snapshot()` plus a run scope in `config/config.py`: inside a run, `ConfigManager()` returns that run's snapshot, so concurrent runs do not share overrides.
- `services/llm/run_context.py` carries the run's config and cost wallet into worker threads and tasks (`run_in_thread`, `spawn_with_context`, `submit_with_context`, `run_wallet_scope`). Start threads inside a run only through these helpers.

## Middleware stack

Outermost first (built in `app.py` `create_app`; pinned by `tests/test_middleware_order.py`):

1. `TrustedHostsMiddleware` (`middleware/hosts.py`): rejects unknown Host headers (DNS rebinding). Defaults: `localhost`, `127.0.0.1`, `[::1]`, `api`, `host.docker.internal`; add more with `STORYFORGE_ALLOWED_HOSTS`.
2. `TraceIDMiddleware`: `X-Request-ID` on every response past the Host check.
3. CORS: explicit origins only (`STORYFORGE_ALLOWED_ORIGINS`), no wildcard.
4. `BodySizeLimitMiddleware` (`middleware/body_limit.py`): 10 MB, chunked bodies included.
5. `SecurityHeadersMiddleware`: CSP, X-Frame-Options, etc.
6. `CSRFMiddleware`: double-submit cookie; `/docs`, `/redoc`, `/openapi.json` are exempt only when `STORYFORGE_DEBUG=1`.
7. `AccessMiddleware` (`middleware/access.py`): optional `STORYFORGE_ACCESS_TOKEN` with the `sf_session` cookie (`api/session_routes.py`); covers `/media` and WebSocket upgrades. Routers use the `require_access` dependency.
8. `RateLimitMiddleware`: in-memory, per IP.
9. `SanitizationMiddleware`: prompt-injection detection on JSON bodies.
10. `AuditMiddleware`
11. `MetricsMiddleware`
12. `GZipMiddleware` (responses of 1 KB or more)

Token-exempt routes: `GET /api/health`, `GET /api/session`, `POST /api/session`, `GET /api/share/gallery`, `GET /api/share/{share_id}`.

## API surface (`api/`)

Route modules (see each file for endpoints): `forge_routes` (sentence forge, sync and SSE), `pipeline_routes` (runs, SSE stream, resume), `continuation_routes` (continue stories; `/continue/library` takes a whole library story), `branch_routes` + `branch_websocket`, `character_routes`, `export_routes`, `quality_routes`, `simulation_routes`, `config_routes`, `provider_status_routes`, `prompt_routes`, `image_routes`, `share_routes`, `session_routes`, `dashboard_routes`, `analytics_routes`, `usage_routes`, `health_routes`, `metrics_routes`, `diagnostics_routes`, `eval_routes`, `feedback_routes`, `ab_routes`. All are mounted under `/api`.

## Frontend (`frontend/`)

Next.js 16 App Router, React 19, Tailwind v4, Zustand stores (`stores/`), React Query, SSE helpers in `lib/sse/`. Pages live in `app/(shell)/`: forge, library, reader, branching, characters, account, analytics, continue, simulation, export, gallery, settings, providers, usage, guide. The production image proxies `/api/*` to the API service; SSE responses must not be gzipped or buffered (see comments in `next.config.ts`).

## Entry points and environment

- `python scripts/dev.py`: API + web with prefixed logs. `python app.py`: backend only. `docker compose up`: packaged stack.
- Common variables (full list in `.env.example`): `STORYFORGE_HOST`, `STORYFORGE_PORT`, `STORYFORGE_DB_PATH`, `STORYFORGE_ACCESS_TOKEN`, `STORYFORGE_ALLOWED_HOSTS`, `STORYFORGE_ALLOWED_ORIGINS`, `STORYFORGE_DEBUG`, `STORYFORGE_API_KEY`, `STORYFORGE_BASE_URL`, `STORYFORGE_MODEL`.
- The secret key is generated on first start at `data/.secret_key` unless `STORYFORGE_SECRET_KEY` is set. Logs: `data/logs/storyforge.log`.

## Tests

`tests/` holds the pytest suite (unit, route, golden, security, perf/benchmark); the `calibration`, `bench` and `perf` markers are excluded from the default run. Frontend tests are vitest (`frontend/**/*.test.ts(x)`) plus Playwright e2e (`npm run test:e2e`). Commands are in `CONTRIBUTING.md`.

More detail: `docs/code-standards.md`, `docs/frontend-security.md`, `docs/frontend-accessibility.md`, `docs/adr/`.
