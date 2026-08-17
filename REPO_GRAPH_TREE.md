# StoryForge Repository Graph Tree — Accurate Version

## Overview
Comprehensive directory structure and component relationship map for the StoryForge codebase (~700 Python files).

---

## 🌳 Top-Level Structure

```
STORYFORGE/
├── .claude/                    # ClaudeCode configuration
├── .github/                    # GitHub workflows & CI
├── .understand-anything/       # Knowledge graph for architecture
├── .venv/                      # Virtual environment
├── AGENTS.md                   # This graph tree + working agreements
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

---

## 🎯 Core Entry Points

### Backend (`app.py`)
- Launches FastAPI on `http://localhost:7860`
- UI runs separately at `http://localhost:3001` (frontend/)
- Mounts API routes, static files, media, CORS, CSRF, rate limiting, middleware

### Pipeline Orchestrator (`pipeline/orchestrator.py`)
- `PipelineOrchestrator` - single public entry point for all pipeline operations
- Sub-components: StoryGenerator, StoryAnalyzer, DramaSimulator, StoryEnhancer
- Methods: `run_full_pipeline()`, `run_layer1_only()`, `run_layer2_only()`, 
  `continue_story()`, `export_output()`, `export_zip()`, checkpoint/continuation ops

### Versioned API (`api/v1/`)
- `router.py` - Central v1 router, reuses `api/` route modules
- Route groups: `/pipeline`, `/config`, `/export`, `/analytics`, `/auth`,
  `/branch`, `/dashboard`, `/feedback` (placeholder)
- All responses carry `X-API-Version: v1` header

### Unversioned API (`api/`)
- 38 route modules covering: forge, auth, branches, characters, pipelines,
  export, analytics, health, metrics, simulation, quality, share, etc.

---

## 🧩 Pipeline Layer 1: Story Generation (`pipeline/layer1_story/`)

**50+ files including:**

| Category | Key Files |
|----------|-----------|
| **Main Generator** | `generator.py` - `StoryGenerator` class |
| **Theme & Premise** | `theme_premise_generator.py`, `theme_premise_generator.py` |
| **Context Building** | `tiered_context_builder.py`, `context_helpers.py`, `batch_context.py` |
| **Chapter Writing** | `chapter_writer.py`, `chapter_rewrites.py`, `chapter_payoff_rewrite.py`, 
  `chapter_self_critique.py`, `chapter_finalizer.py`, `scene_writer.py`, 
  `scene_decomposer.py`, `scene_beat_generator.py` |
| **Character Development** | `character_generator.py`, `character_memory_bank.py`, 
  `character_secret_tracker.py`, `character_voice_profiler.py`, 
  `story_bible_manager.py` |
| **Dialogue & Consistency** | `dialogue_strategy.py`, `dialogue_attribution_validator.py`, 
  `dialogue_consistency_checker.py`, `dialogue_attribution_parsing.py` |
| **Plot & Structure** | `plot_thread_tracker.py`, `consistency_checker.py`, 
  `consistency_validators.py`, `causal_chain.py`, `l1_causal_graph.py` |
| **Outline & Arc** | `outline_builder.py`, `outline_arc_validator.py`, 
  `outline_critic.py`, `macro_outline_builder.py`, `arc_milestone_manager.py` |
| **Quality & Pacing** | `quality_validators.py`, `pacing_controller.py`, 
  `pacing_enforcer.py`, `coherence_validator.py` |
| **Batch & Parallel** | `batch_generator.py`, `batch_parallel_writer.py`, 
  `batch_parallel_dispatch.py`, `contract_batch_retry.py` |
| **Specialized** | `foreshadowing_manager.py`, `timeline_validator.py`, 
  `enhancement_context_builder.py`, `extraction_guard.py` |

**Key Classes:**
- `StoryGenerator` - Main entry point for L1 story generation
- `StoryBibleManager` - Maintains story consistency across chapters

---

## 🚀 Pipeline Layer 2: Enhancement (`pipeline/layer2_enhance/`)

**30+ files including:**

| Category | Key Files |
|----------|-----------|
| **Main Analyzer** | `analyzer.py` - `StoryAnalyzer` class |
| **Drama Simulation** | `simulator.py` - `DramaSimulator` - simulates conflict/drama |
| **Story Enhancement** | `enhancer.py` - `StoryEnhancer` - refines and polishes story |
| **Thematic Analysis** | `thematic_tracker.py` - Tracks thematic elements across story |
| **Thread Watching** | `thread_watchdog.py` - Monitors thread consistency |
| **Voice Fingerprint** | `voice_fingerprint.py` - Character voice profiling |
| **Causal & Structural** | `causal_chain.py`, `structural_detector.py`, 
  `coherence_validator.py`, `conflict_web_builder.py` |
| **Character & State** | `character_state_registry.py`, `enhancement_diff_tracker.py`, 
  `knowledge_system.py`, `psychology_engine.py` |
| **Scene & Dialogue** | `scene_enhancer.py`, `sensory_polish.py`, 
  `dialogue_subtext.py`, `setting_continuity.py` |
| **Gate & Contract** | `contract_gate.py`, `contract_gate.py`, `chapter_contract.py` |
| **Agents** | `agent.py`, `agent_state.py`, `_agent.py`, `_envelope_access.py` |

**Key Classes:**
- `StoryAnalyzer` - Analyzes story structure, identifies issues
- `DramaSimulator` - Simulates dramatic events and character interactions
- `StoryEnhancer` - Applies refinements, fixes, and improvements

---

## 🌐 API Routes (`api/` - 38 modules)

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
| `metrics_routes.py` | System metrics | Performance data |
| `flowkit.py` | FlowKit integration | Media/flow processing |

**Note:** `api/v1/router.py` reuses all these modules under `/api/v1/` prefix.

---

## 🗄️ Models & Schemas (`models/`)

| File | Purpose | Key Models |
|------|---------|-----------|
| `schemas.py` | Main Pydantic schemas (52KB) | `EnhancedStory`, `PipelineOutput`, `StoryDraft`, `ForgeRequest/Response` |
| `db_models.py` | Database model definitions | SQLAlchemy models, database tables |
| `handoff_schemas.py` | Layer handoff schemas | Transition between L1/L2 |
| `narrative_schemas.py` | Narrative structure schemas | Chapter, scene, arc definitions |
| `semantic_schemas.py` | Semantic processing | Meaning extraction, entity recognition |
| `voice_schemas.py` | Voice/character voice models | Voice profiles, speech patterns |

---

## 🤖 Services (`services/` - 20+ modules)

| Directory | Key Files | Purpose |
|-----------|-----------|---------|
| `llm/` | `client.py` (73KB), `generation.py`, `provider_status.py`, `streaming.py` | LLM client singleton, multi-provider support, streaming, token tracking |
| `auth/` | `user_manager.py`, `user_store.py` | User management, authentication state |
| `pipeline/` | `branch_narrative.py`, `quality_gate.py`, `smart_revision.py` | Pipeline services, quality gates, smart revisions |
| `media/` | `flow_service.py`, `output_paths.py` | Media processing, flowKit, output path management |
| `assets/` | - | Asset handling and storage |
| `export/` | - | Exporters (Wattpad, other formats) |
| `prompts/` | - | Prompt templates for LLM calls |
| `security/` | `url_validator.py` | URL validation, security sanitization |
| `token_cost_tracker.py` | Token cost tracking across operations |
| `trace_context.py` | Trace context management | Request-wide context propagation |
| `embedding_service.py` | Embedding generation & caching |
| `embedding_cache.py` | Embedding cache for similarity |
| `structured_logger.py` | Structured logging | JSON/logger correlation |
| `gzipped_static_files.py` | Gzipped static file serving |
| `output_paths.py` | OUTPUT_ROOT - single source truth for output directory |

**LLM Client (`services/llm/client.py`)** - Main singleton:
- Supports multiple LLM providers
- Token counting and cost tracking
- Streaming and non-streaming modes
- Model selection (cheap/expensive)
- Caching and retry logic

---

## 🌍 Frontend (`frontend/` - Next.js 16 + React 19)

| Directory | Purpose |
|-----------|---------|
| `app/` | Next.js 16 app router pages & routes |
| `components/` | React components organized by feature: |
| | `account/`, `analytics/`, `branching/`, `characters/`, `common/`, |
| | `continue/`, `export/`, `gallery/`, `guide/`, `library/`, `motion/`, |
| | `pipeline/`, `providers/`, `reader/`, `settings/`, `shell/`, `simulation/`, |
| | `ui/`, `usage/` |
| `hooks/` | Custom React hooks (useQuery, useMutation, etc.) |
| `lib/` | Utility libraries (API client, constants, helpers) |
| `messages/` | Localization messages (Vietnamese, Chinese) |
| `stores/` | Zustand state management stores |
| `types/` | TypeScript type definitions |
| `package.json` | Dependencies: Next.js 16, React 19, Tailwind CSS v4 |
| `vitest.config.ts` | Vitest testing configuration |
| `next.config.ts` | Next.js configuration |

**Key Frontend Flow:**
- UI at `http://localhost:3001`
- API calls to backend at `http://localhost:7860`
- Type-safe API calls with generated types
- Zustand stores for global state (story state, pipeline state, auth)
- Localization with Vietnamese/Chinese support

---

## 📊 Tests (`tests/` - 100+ files)

| Directory | Purpose |
|-----------|---------|
| `fixtures/` | Test data fixtures & reference data |
| `golden/` | Golden test outputs (expected results for regression) |
| `benchmarks/` | Performance benchmarks |
| `load/` | Load testing scripts |
| `perf/` | Performance tests |
| `security/` | Security testing |

**Key Test Files:**
- `test_l1_*.py` - Layer 1 pipeline tests (story generation)
- `test_l2_*.py` - Layer 2 pipeline tests (enhancement)
- `test_pipeline_*.py` - Pipeline integration tests
- `test_orchestrator_*.py` - Orchestrator functionality tests
- `test_api_*.py` - API route tests (coverage, async, routes)
- `test_agent_*.py` - Agent tests (debate, graph, individual)
- `test_forge_routes.py` - Forge endpoint tests
- `test_config_*.py` - Configuration tests
- `test_batch_*.py` - Batch processing tests

**Fixtures & Golden:** `tests/fixtures/` contains input data, `tests/golden/` contains expected outputs for regression testing.

---

## ⚙️ Configuration (`config/`)

| File | Purpose |
|------|---------|
| `validation.py` | Configuration validation logic |
| `.env*` | Environment variables |

**Key Config Options:**
- `pipeline.enable_sentence_forge` - Feature flag for forge endpoint
- `pipeline.flowkit_enabled` - FlowKit/media integration
- `llm.cheap_model` / `llm.expensive_model` - Model configuration
- `llm.api_key` - LLM authentication key
- `REDIS_URL` - Redis connection for session state (24h TTL)
- `STORYFORGE_REDIS_REQUIRED` - Make Redis failure fatal
- `STORYFORGE_ALLOWED_ORIGINS` - CORS allowed origins
- `STORYFORGE_SECRET_KEY` - Encryption key

---

## 📁 Output (`output/`)

**Structure:** `output/<story-slug>/`
- `checkpoint_*.json` - Pipeline checkpoints at various layers
- `chapters/` - Generated chapter content
- `images/` - Generated story illustrations
- `avatars/` - Character avatars
- `exports/` - Exported files (PDF, EPUB, Markdown)
- `metadata.json` - Pipeline execution metadata

**Checkpoint contains:**
- Story state at specific layer (L1 draft, L2 enhanced)
- Character information and profiles
- Progress tracking across chapters
- Agent interaction history
- Redis session key reference

---

## 🔌 Plugins (`plugins/`)

**Extension point system for:**
- Custom LLM providers
- Additional export formats (PDF, EPUB, Markdown, Wattpad)
- Genre-specific extensions (Vietnamese, Chinese, Western)
- Media generation plugins (images, video segments)
- Custom agent behaviors

---

## 🛠️ Scripts (`scripts/`)

**Utility & automation scripts for:**
- Database initialization & migrations
- Batch story generation
- Checkpoint backup/restore
- Development workflow automation
- Deployment utilities

---

## 🔗 Component Relationships (Data Flow)

```
User Input
    │
    ├──► API Route (api/ or api/v1/)
    │         │
    │         ├──► PipelineOrchestrator (pipeline/orchestrator.py)
    │         │   │
    │         │   ├──► StoryGenerator (pipeline/layer1_story/generator.py)
    │         │   │   │
    │         │   │   ├──► ConfigManager (config/) → Models (models/schemas.py)
    │         │   │   │
    │         │   │   └──► LLM Client (services/llm/client.py)
    │         │   │
    │         │   ├──► DramaSimulator (pipeline/layer2_enhance/simulator.py)
    │         │   │   └──► LLM Client (services/llm/client.py)
    │         │   │
    │         │   ├──► StoryEnhancer (pipeline/layer2_enhance/enhancer.py)
    │         │   │   └──► LLM Client (services/llm/client.py)
    │         │   │
    │         │   ├──► CheckpointManager → Redis (24h TTL) or memory
    │         │   │
    │         │   ├──► MediaProducer → services/media/ → images
    │         │   │
    │         │   └──► PipelineExporter → output/ exports
    │         │
    │         └──► Response → Frontend or Client
    │
    ├──► Services (LLM, DB, Redis, Media)
    │
    └──► Response → Frontend or Client
```

**Middleware Stack (app.py, innermost → outermost):**
1. BodySizeLimitMiddleware (10MB limit)
2. GZipMiddleware
3. CORS middleware (explicit origins only)
4. CSRF middleware
5. TraceIDMiddleware
6. SecurityHeadersMiddleware
7. SanitizationMiddleware (prompt injection detection)
8. RateLimitMiddleware (Redis or in-memory per-IP)
9. AuditMiddleware
10. MetricsMiddleware

---

## 📝 Quick Navigation Commands

**Find a component:**
- `rg "<function_name>" --type py` - Grep in Python files (ripgrep)
- `mcp__serena__find_symbol <function_name>` - Symbol-aware search (Serena MCP)
- `find . -name "*.py" | grep -i <name>` - File search

**Run tests:**
```bash
cd C:\Users\Admin\OneDrive\Desktop\STORYFORGE
pytest tests/ -x -v              # Full test suite
pytest tests/test_l1_*.py -x -v  # Layer 1 pipeline tests
pytest tests/test_l2_*.py -x -v  # Layer 2 pipeline tests
pytest tests/test_forge_routes.py -x -v  # Forge endpoint tests
```

**Run lint/typecheck:**
```bash
cd C:\Users\Admin\OneDrive\Desktop\STORYFORGE
ruff check .              # Ruff Python linting
ruff check . --fix       # Auto-fix linting issues
```

**Type check (if configured):**
```bash
pyproject.toml defines type checking setup
```

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

*Generated from comprehensive codebase exploration on 2026-08-17. This graph tree covers ~700 Python files across 38+ directories and helps agents quickly navigate the StoryForge repository.*