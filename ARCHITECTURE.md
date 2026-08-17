# StoryForge Architecture Documentation

## Top-Level Directory Structure

The repository is organized into the following top-level directories:

```
STORYFORGE/
├── .claude/                    # ClaudeCode configuration
├── .github/                    # GitHub workflows & CI
├── .understand-anything/       # Knowledge graph for architecture
├── .venv/                      # Virtual environment
├── AGENTS.md                   # This document + working agreements
├── CHANGELOG.md                # Change history
├── COMMUNITY.md                # Community contribution guide
├── config/                     # Configuration & validation
├── data/                       # Project data & prompts
├── docs/                       # Documentation
├── errors/                     # Error definitions & handlers
├── flowkit_extension/          # FlowKit extension
├── frontend/                   # Next.js 16 React 19 UI
├── locales/                    # i18n (Vietnamese/Chinese)
├── middleware/                 # Express/Next.js middleware stack
├── models/                     # Database & Pydantic schemas
├── output/                     # Generated story outputs/checkpoints
├── plugins/                    # Plugin system extensions
├── scripts/                    # Utility & automation scripts
├── services/                   # Backend service modules
├── tests/                      # Comprehensive test suite (~100+ files)
├── .gitignore
├── .env*                       # Environment configurations
├── pyproject.toml              # Project config & dependencies
├── requirements*.txt           # Python dependency locks
├── Dockerfile                  # Container definition
├── docker-compose*.yml         # Multi-service orchestration
├── README.md / README.vi.md    # Project documentation
├── storyforge.log              # Application log
├── uv.lock                     # UV lock file
└── test-results/               # Test execution results
```

## Pipeline 2-Layer Flow

### Layer 1: Story Generation

The first layer generates the initial story draft from user input (title, genre, idea).

**Key Components:**
- `pipeline/layer1_story/generator.py` — `StoryGenerator` main entry point
- `pipeline/layer1_story/theme_premise_generator.py` — Generates themes and premises
- `pipeline/layer1_story/tiered_context_builder.py` — Builds contextual layers
- `pipeline/layer1_story/chapter_writer.py` — Writes chapter content
- `pipeline/layer1_story/character_generator.py` — Generates characters
- `pipeline/layer1_story/plot_thread_tracker.py` — Tracks plot threads
- `pipeline/layer1_story/quality_validators.py` — Validates quality
- `pipeline/layer1_story/outline_builder.py` — Builds story outlines

**Data Flow:**
```
User Input (title, genre, idea)
    │
    ├──► API Route (api/forge or api/pipeline)
    │
    └──► PipelineOrchestrator
          │
          ├──► StoryGenerator → StoryDraft
          │
          └──► CheckpointManager → Redis (24h TTL) or memory
```

### Layer 2: Enhancement

The second layer enhances the L1 draft with drama simulation, thematic analysis, voice fingerprinting, and refinement.

**Key Components:**
- `pipeline/layer2_enhance/enhancer.py` — `StoryEnhancer` main entry point
- `pipeline/layer2_enhance/simulator.py` — `DramaSimulator` — simulates conflict/drama
- `pipeline/layer2_enhance/analyzer.py` — `StoryAnalyzer` — analyzes story structure
- `pipeline/layer2_enhance/thematic_tracker.py` — Tracks thematic elements
- `pipeline/layer2_enhance/voice_fingerprint.py` — Character voice profiling
- `pipeline/layer2_enhance/thread_watchdog.py` — Monitors thread consistency

**Data Flow:**
```
StoryDraft (from L1)
    │
    ├──► StoryEnhancer → EnhancedStory
    │
    ├──► DramaSimulator → conflict events & drama scores
    │
    ├──► ThematicTracker → theme alignment scores
    │
    ├──► VoiceFingerprint → character voice consistency
    │
    └──► CheckpointManager → Redis/in-memory persistence
```

### Layer Handoff (L1 → L2)

The handoff between layers uses `models/handoff_schemas.py` which defines:

- `PipelineOutput` — Full pipeline output with metadata
- `StoryDraft` — Initial story draft from L1
- `EnhancedStory` — Story after L2 enhancement
- `StoryContinuation` — Continuation/edit operations

**Persistence:** Stored in Redis (24h TTL) or local checkpoint files in `output/`

---

## Component Relationship Map

### Data Flow

```
User Input
    │
    ├──► API Route (api/ or api/v1/)
    │       │
    │       ├──► PipelineOrchestrator
    │       │   │
    │       │   ├──► StoryGenerator (L1)
    │       │   │   │
    │       │   │   └──► ConfigManager → Models (schemas.py)
    │       │   │
    │       │   ├──► DramaSimulator (L2)
    │       │   │   └──► LLM Client (services/llm/client.py)
    │       │   │
    │       │   ├──► StoryEnhancer (L2)
    │       │   │   └──► LLM Client (services/llm/client.py)
    │       │   │
    │       │   ├──► CheckpointManager → Redis/in-memory
    │       │   │
    │       │   ├──► MediaProducer → images
    │       │   │
    │       │   └──► PipelineExporter → output formats
    │       │
    │       └──► Response → Frontend or Client
    │
    └──► Services (LLM, DB, Redis, Media)
            │
            └──► Response → Frontend or Client
```

### Key Models

| Model | File | Purpose |
|-------|------|---------|
| `StoryDraft` | `models/schemas.py` | Initial story draft from L1 |
| `EnhancedStory` | `models/schemas.py` | Story after L2 enhancement |
| `PipelineOutput` | `models/schemas.py` | Full pipeline output with metadata |
| `ForgeRequest/Response` | `models/schemas.py` | Sentence-forge payloads |
| `ThemeProfile` | `pipeline/layer2_enhance/thematic_tracker.py` | Theme extraction result |
| `ChapterThematicScore` | `pipeline/layer2_enhance/thematic_tracker.py` | Chapter theme alignment score |
| `VoiceProfile` | `models/voice_schemas.py` | Character voice profile |
| `Character` | `models/schemas.py` | Character definition |

### Key Schemas

| Schema | File | Purpose |
|--------|------|---------|
| `handoff_schemas.py` | `models/handoff_schemas.py` | Layer handoff between L1/L2 |
| `narrative_schemas.py` | `models/narrative_schemas.py` | Chapter, scene, arc definitions |
| `voice_schemas.py` | `models/voice_schemas.py` | Voice/profile schemas |
| `schemas.py` | `models/schemas.py` | Main Pydantic schemas (52KB) |

---

## Middleware Stack (app.py, order matters)

The FastAPI application uses the following middleware stack (from outermost to innermost):

1. **BodySizeLimitMiddleware** — 10MB body size limit (runs first)
2. **GZipMiddleware** — Compresses responses ≥1KB (shrink ~5-7×)
3. **CORS middleware** — Explicit origins only, no wildcard `*`
4. **CSRF middleware** — Double-submit cookie protection
5. **TraceIDMiddleware** — Must be outermost so all downstream layers see it
6. **SecurityHeadersMiddleware** — CSP, X-Frame-Options, etc.
7. **SanitizationMiddleware** — Prompt injection detection
8. **RateLimitMiddleware** — Redis or in-memory per-IP rate limiting
9. **AuditMiddleware** — Audit logging
10. **MetricsMiddleware** — Request metrics collection

**Note:** BodySizeLimitMiddleware runs outermost to block oversized requests early.

---

## API Routes Structure

The API has 38 route modules under `api/`, plus a versioned `api/v1/` router:

### Unversioned API (`api/`)

| Route | Prefix | Key Endpoints |
|-------|--------|---------------|
| `forge_routes.py` | `/forge` | `POST /sentence`, `POST /sentence/stream` |
| `pipeline_routes.py` | `/pipeline` | Full pipeline orchestration |
| `auth_routes.py` | `/auth` | Register, login, me |
| `character_routes.py` | `/characters` | CRUD operations |
| `branch_routes.py` | `/branch` | Alternate paths |
| `continuation_routes.py` | `/pipeline` | Continue/edit stories. `POST /continue` is checkpoint-addressed; `POST /continue/library` takes a whole localStorage story in the body (hydrated by `services/library_continuation.py`) and is what the "Viết tiếp truyện" screen calls, with `POST /continue/library/outlines` planning the next chapters for review/editing first |
| `export_routes.py` | `/export` | PDF, EPUB, Markdown |
| `quality_routes.py` | `/quality` | Quality scoring |
| `simulation_routes.py` | `/simulation` | Drama scenarios |
| `dashboard_routes.py` | `/dashboard` | Summary stats |
| `analytics_routes.py` | `/analytics` | Usage tracking |
| `health_routes.py` | `/health` | DB/Redis checks |
| `metrics_routes.py` | `/metrics` | Performance data |
| `share_routes.py` | `/share` | Shareable links |
| `account_routes.py` | `/account` | User profile |
| `prompt_routes.py` | `/prompts` | Prompt templates |
| `image_routes.py` | `/images` | Avatar generation |
| `eval_routes.py` | `/eval` | Human evaluation |
| `feedback_routes.py` | `/feedback` | User feedback |
| `diagnostics_routes.py` | `/diagnostics` | Debug endpoints |
| `ab_routes.py` | `/ab` | A/B testing |
| `config_routes.py` | `/config` | Settings management |
| `flowkit.py` | — | FlowKit media integration |

### Versioned API (`api/v1/`)

- `api/v1/router.py` — Central v1 router
- Reuses 9 route modules from `api/` with local imports
- All responses carry `X-API-Version: v1` header
- **Frozen**: Further changes should go through v2 or `/api/` routes

### API Versioning Strategy

- StoryForge uses URL-path versioning (`/api/v1/`, `/api/v2/`, …)
- `api/v1/` mirrors the unversioned `/api/` routes
- **TODO**: When v2 is introduced, freeze v1 by copying modules to `api/v1/` and stopping further changes
- This guarantees backward compatibility for existing clients

---

## Entry Points

### Backend (`app.py`)

- Launches FastAPI on `http://localhost:7860`
- UI runs separately at `http://localhost:3001` (frontend/)
- Mounts API routes, static files, media, CORS, CSRF, rate limiting, middleware
- Key environment variables:
  - `REDIS_URL` — Redis connection for session state
  - `STORYFORGE_REDIS_REQUIRED` — Make Redis failure fatal
  - `STORYFORGE_ENABLE_DOCS` — Enable `/docs` and `/redoc`
  - `STORYFORGE_ALLOWED_ORIGINS` — CORS allowed origins

### Pipeline Orchestrator (`pipeline/orchestrator.py`)

- `PipelineOrchestrator` — single public entry point for all pipeline operations
- **Public methods:**
  - `run_full_pipeline()` — Execute L1 + L2 pipeline
  - `run_layer1_only()` — Generate story draft (L1 only)
  - `run_layer2_only()` — Enhance existing draft (L2 only)
  - `continue_story()` — Continue from checkpoint
  - `export_output()` / `export_zip()` — Export story formats
  - `save_checkpoint()` / `resume_from_checkpoint()` — Persistence
  - `update_character()` / `enhance_chapters()` — Interactive editing

### Frontend (`frontend/`)

- Next.js 16 + React 19 application
- UI at `http://localhost:3001`
- Communicates with backend API at `http://localhost:7860`
- State management via Zustand stores
- TypeScript types in `frontend/types/`
- `package.json` — Dependencies: Next.js 16, React 19, Tailwind CSS v4

---

## Test Organization

### Test Directories

| Directory | Purpose |
|-----------|---------|
| `fixtures/` | Test data fixtures & reference data |
| `golden/` | Golden test outputs (expected results for regression) |
| `benchmarks/` | Performance benchmarks |
| `load/` | Load testing scripts |
| `perf/` | Performance tests |
| `security/` | Security testing |

### Key Test Files

| File | Purpose |
|------|---------|
| `test_l1_*.py` | Layer 1 pipeline tests (story generation) |
| `test_l2_*.py` | Layer 2 pipeline tests (enhancement) *[new]* |
| `test_pipeline_*.py` | Pipeline integration tests |
| `test_orchestrator_*.py` | Orchestrator functionality tests |
| `test_forge_routes.py` | Forge endpoint tests |
| `test_agent_*.py` | Agent tests (debate, graph, individual) |
| `test_config_*.py` | Configuration tests |

**Test Fixtures & Golden:**
- `tests/fixtures/` — Input data for tests
- `tests/golden/` — Expected outputs for regression testing

**Running Tests:**
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

**Type check:**
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

For detailed architecture diagrams, component relationships, and pipeline flow diagrams, see:
- `AGENTS.md` — Working guide for agents and developers
- `REPO_GRAPH_TREE.md` — Comprehensive directory structure and relationships
- `ARCHITECTURE.md` — This file

These documents cover:
- Top-level directory structure (30+ directories)
- Pipeline L1 → L2 data flow with all sub-components
- Middleware stack order and purpose
- API routes structure with endpoint descriptions
- Entry points and their responsibilities
- Test organization and navigation commands
- Quick reference commands (rg, Serena MCP, pytest, ruff)