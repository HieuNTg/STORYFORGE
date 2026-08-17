# StoryForge - Working agreement

## Codebase navigation (IMPORTANT)
This project has 700+ Python files across 38+ directories. Do NOT blind-read or blind-grep the codebase.

**Prefer Serena MCP tools over Read/Grep for any code task that crosses files:**
- mcp__serena__find_symbol — locate a function/class/method by name
- mcp__serena__find_referencing_symbols — find every callsite/import of a symbol BEFORE refactoring
- mcp__serena__get_symbols_overview — get the shape of a file without reading every line
- mcp__serena__search_for_pattern — symbol-aware search

**Rule:** Before editing any function or class, run find_referencing_symbols to see who depends on it. Do not refactor without that impact list.

For architecture-level questions (layers, pipeline flow, component relationships), refer to ARCHITECTURE.md or the REPO_GRAPH_TREE.md.

---

## Pipeline 2-Layer Flow

### Layer 1: Story Generation (pipeline/layer1_story/) — ~121 files
- Main entry: `StoryGenerator` class in `generator.py`
- Produces: story draft, checkpoints, chapter content
- Sub-components:
  - Theme/premise generation (`theme_premise_generator.py`)
  - Context building (`tiered_context_builder.py`, `context_helpers.py`)
  - Chapter writing (`chapter_writer.py`, `scene_decomposer.py`, `scene_beat_generator.py`)
  - Character development (`character_generator.py`, `story_bible_manager.py`)
  - Dialogue & consistency (`dialogue_strategy.py`, `dialogue_attribution_validator.py`)
  - Plot & structure (`plot_thread_tracker.py`, `l1_causal_graph.py`, `outline_builder.py`)
  - Quality & pacing (`quality_validators.py`, `pacing_controller.py`, `pacing_enforcer.py`)
  - Batch & parallel processing (`batch_generator.py`, `batch_parallel_writer.py`)
  - Specialized (`foreshadowing_manager.py`, `timeline_validator.py`)

### Layer 2: Enhancement (pipeline/layer2_enhance/) — ~121 files
- Main entry: `StoryEnhancer` class in `enhancer.py`
- Refines L1 output: drama simulation, thematic analysis, voice fingerprint, causal/structural analysis, character state tracking, scene/dialogue polishing
- Sub-components:
  - Analyzer (`analyzer.py`) — story analysis
  - Simulator (`simulator.py`) — drama simulation
  - Enhancer (`enhancer.py`) — story refinement
  - Thematic tracker (`thematic_tracker.py`) — thematic analysis
  - Thread watchdog (`thread_watchdog.py`) — thread consistency monitoring
  - Voice fingerprint (`voice_fingerprint.py`) — character voice profiling
  - Causal & structural (`causal_chain.py`, `structural_detector.py`, `conflict_web_builder.py`)
  - Character & state (`character_state_registry.py`, `psychology_engine.py`, `knowledge_system.py`)
  - Scene & dialogue (`scene_enhancer.py`, `sensory_polish.py`, `dialogue_subtext.py`)
  - Gate & contract (`contract_gate.py`, `chapter_contract.py`)

**Flow:** API Route → `PipelineOrchestrator` → L1 `StoryGenerator` → Checkpoint → L2 `StoryEnhancer`/`DramaSimulator` → Final Output

**Key Handoff:** L1 → L2 via `handoff_schemas.py` (`PipelineOutput`, `StoryDraft`, etc.) stored in Redis (24h TTL) or checkpoint files.

---

## Component Relationship Map

```
User Input
    │
    ├──► API Route (api/ or api/v1/)
    │       │
    │       ├──► PipelineOrchestrator (pipeline/orchestrator.py)
    │       │   │
    │       │   ├──► StoryGenerator (pipeline/layer1_story/generator.py)
    │       │   │   │
    │       │   │   ├──► ConfigManager (config/) → Models (models/schemas.py)
    │       │   │   │
    │       │   │   └──► LLM Client (services/llm/client.py)
    │       │   │
    │       │   ├──► DramaSimulator (pipeline/layer2_enhance/simulator.py)
    │       │   │   └──► LLM Client (services/llm/client.py)
    │       │   │
    │       │   ├──► StoryEnhancer (pipeline/layer2_enhance/enhancer.py)
    │       │   │   └──► LLM Client (services/llm/client.py)
    │       │   │
    │       │   ├──► CheckpointManager → Redis (24h TTL) or memory
    │       │   │
    │       │   ├──► MediaProducer → services/media/ → images
    │       │   │
    │       │   └──► PipelineExporter → output/ exports
    │       │
    │       └──► Response → Frontend or Client
    │
    ├──► Services (LLM, DB, Redis, Media)
    │
    └──► Response → Frontend or Client
```

---

## Middleware Stack (app.py, order matters)
1. BodySizeLimitMiddleware (10MB limit)
2. GZipMiddleware
3. CORS middleware (explicit origins only, no wildcard)
4. CSRF middleware (double-submit cookie)
5. TraceIDMiddleware (must be outermost)
6. SecurityHeadersMiddleware (CSP, X-Frame-Options, etc.)
7. SanitizationMiddleware (prompt injection detection)
8. RateLimitMiddleware (Redis or in-memory per-IP)
9. AuditMiddleware
10. MetricsMiddleware

---

## API Routes Structure (api/ — 38 modules)

| Route File | Primary Endpoints | Purpose |
|------------|------------------|---------|
| `forge_routes.py` | `POST /forge/sentence`, `POST /forge/sentence/stream` | Synchronous forge from sentence idea |
| `pipeline_routes.py` | Pipeline orchestration endpoints | Session management, layer execution |
| `auth_routes.py` | Auth endpoints | User authentication |
| `character_routes.py` | Character management | CRUD operations on characters |
| `branch_routes.py` | Story branching | Alternate paths & branching |
| `continuation_routes.py` | Story continuation | Continue/edit existing stories |
| `export_routes.py` | Export formats | PDF, EPUB, Markdown export |
| `quality_routes.py` | Quality scoring | Story quality assessment |
| `simulation_routes.py` | Drama simulation | Interactive drama scenarios |
| `dashboard_routes.py` | Dashboard data | Summary statistics |
| `analytics_routes.py` | Usage analytics | Usage tracking & reports |
| `health_routes.py` | Health checks | DB/Redis status |
| `metrics_routes.py` | System metrics | Performance metrics |
| `share_routes.py` | Story sharing | Shareable links |
| `account_routes.py` | Account management | User profile |
| `prompt_routes.py` | Prompt management | Prompt templates |
| `image_routes.py` | Image generation | Visual asset creation |
| `eval_routes.py` | Evaluation | Story evaluation |
| `feedback_routes.py` | User feedback | Feedback submission |
| `diagnostics_routes.py` | Diagnostics | Debug/ diagnostics |
| `ab_routes.py` | A/B testing | Experiment variants |
| `config_routes.py` | Configuration | Settings management |
| `flowkit.py` | FlowKit integration | Media/flow processing |

**Note:** `api/v1/router.py` reuses all the above modules under `/api/v1/` prefix with `X-API-Version: v1` header. See `ARCHITECTURE.md` for freeze details.

---

## Entry Points

### Backend (`app.py`)
- Launches FastAPI on `http://localhost:7860`
- UI runs separately at `http://localhost:3001` (frontend/)
- Mounts API routes, static files, media, CORS, CSRF, rate limiting, middleware

### Pipeline Orchestrator (`pipeline/orchestrator.py`)
- `PipelineOrchestrator` — single public entry point for all pipeline operations
- Methods: `run_full_pipeline()`, `run_layer1_only()`, `run_layer2_only()`, 
  `continue_story()`, `export_output()`, `export_zip()`, checkpoint/continuation ops

### Versioned API (`api/v1/`)
- `api/v1/router.py` — Central v1 router (frozen copy of api/ modules)
- `api/v1/__init__.py` — Package-level router with local imports
- `api/v1/router.py` — Built via `build_v1_router()` factory function

### Frontend (`frontend/`)
- Next.js 16 + React 19 application
- UI at `http://localhost:3001`
- Communicates with backend API at `http://localhost:7860`
- State management via Zustand stores
- TypeScript types in `frontend/types/`

---

## Test Organization (tests/ — 100+ files)

| Directory | Purpose |
|-----------|---------|
| `fixtures/` | Test data fixtures |
| `golden/` | Golden test outputs (expected results) |
| `benchmarks/` | Performance benchmarks |
| `load/` | Load testing |
| `perf/` | Performance tests |
| `security/` | Security testing |

**Key Test Files:**
- `test_l1_*.py` — Layer 1 pipeline tests (story generation)
- `test_l2_*.py` — Layer 2 pipeline tests (enhancement) *[new]*
- `test_pipeline_*.py` — Pipeline integration tests
- `test_orchestrator_*.py` — Orchestrator functionality tests
- `test_forge_routes.py` — Forge endpoint tests
- `test_agent_*.py` — Agent tests (debate, graph, individual)
- `test_config_*.py` — Configuration tests

**Run tests:**
```bash
cd C:\Users\Admin\OneDrive\Desktop\STORYFORGE
pytest tests/ -x -v              # Full test suite
pytest tests/test_l1_*.py -x -v  # Layer 1 pipeline tests
pytest tests/test_l2_*.py -x -v  # Layer 2 pipeline tests
pytest tests/test_forge_routes.py -x -v  # Forge endpoint tests
```

---

## Quick Navigation Commands

**Find a component:**
- `rg "<function_name>" --type py` — Grep in Python files (ripgrep)
- `mcp__serena__find_symbol <function_name>` — Symbol-aware search (Serena MCP)
- `find . -name "*.py" | grep -i <name>` — File search

**Run tests:**
```bash
pytest tests/ -x -v              # Full test suite
pytest tests/test_l1_*.py -x -v  # Layer 1 pipeline tests
pytest tests/test_l2_*.py -x -v  # Layer 2 pipeline tests
```

**Run lint/typecheck:**
```bash
cd C:\Users\Admin\OneDrive\Desktop\STORYFORGE
ruff check .              # Ruff Python linting
ruff check . --fix       # Auto-fix linting issues
```

**Type check (if configured):**
- `pyproject.toml` defines type checking setup

**Docker:**
```bash
cd C:\Users\Admin\OneDrive\Desktop\STORYFORGE
docker-compose up -d      # Start all services (database, Redis, etc.)
```

**Environment:**
```bash
cp .env.example .env      # Copy env template
# Edit .env with your settings
# Required: REDIS_URL, STORYFORGE_SECRET_KEY, LLM API keys
```

---

## Recent Changes (as of 2026-08-17)

1. **API v1 freeze** — Copied 9 route modules from `api/` to `api/v1/` with local imports. `api/v1/` is now immutable — further changes should go through v2 or the unversioned `/api/` routes.

2. **Layer 2 test coverage** — Added `tests/test_l2_thematic_tracker.py` (10 tests) and `tests/test_l2_voice_fingerprint.py` (2 tests) covering ThemeProfile, ChapterThematicScore, ThematicTracker methods, and VoiceProfile model.

3. **Import optimization** — Created `api/v1/__init__.py` with relative imports, updated `api/v1/router.py` to use `from .X import` instead of `from api.X import`.

4. **Repository graph tree** — Created `REPO_GRAPH_TREE.md` with comprehensive directory structure and component relationships (563 Python files, 38+ directories).

5. **Documentation** — Updated `AGENTS.md` with comprehensive navigation guide, component relationships, middleware stack, and API routes structure.

---

## Architecture Reference

For detailed architecture diagrams, component relationships, and pipeline flow diagrams, see `ARCHITECTURE.md` at the repo root. This file contains:
- Top-level directory structure (30+ directories)
- Pipeline L1 → L2 data flow with all sub-components
- Middleware stack order and purpose
- API routes structure with endpoint descriptions
- Entry points and their responsibilities
- Test organization and navigation commands
- Quick reference commands (rg, Serena MCP, pytest, ruff)