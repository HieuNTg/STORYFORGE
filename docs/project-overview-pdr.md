# StoryForge: Project Overview & Product Development Requirements

## Project Vision

**AI-powered story generation with multi-agent drama simulation.**

Transform a one-sentence idea into a complete, drama-rich story with character-consistent images and cinematic scene backgrounds. Self-hosted, privacy-first, works with any OpenAI-compatible LLM.

## Core Features

### 1. 2-Layer Generation Pipeline

**Layer 1: Story Generation** → Characters, world-building, full chapters
**Layer 2: Drama Simulation** → 13 AI agents, conflict analysis, auto-revision
**Image Generation** → Character consistency (IP-Adapter) + scene backgrounds (runs after Layer 2)

**Key**: Checkpoint & resume, real-time SSE streaming, quality gates.

### 2. Multi-Agent Drama System

**13 Specialized Agents**:
- 10 character agents (autonomous interactions)
- Drama critic (conflict scoring)
- Editor-in-chief (story coherence)
- Pacing analyzer, style checker, dialogue expert

**Conflict Detection**: Agents debate, form alliances, discover unexpected conflicts not in original outline.

### 3. Quality Scoring & Auto-Revision

**4-Dimension Evaluation**:
- Coherence (logical consistency)
- Character (personality consistency)
- Drama (emotional impact & conflict)
- Writing style (prose quality)

**Auto-Revision Loop**: If any dimension scores below threshold, agent recommends rewrites.

### 4. Multi-Provider LLM Support

**Supported**:
- OpenAI (GPT-4, GPT-4o)
- Google Gemini
- Anthropic Claude
- OpenRouter (290+ models)
- Ollama (local)
- Any OpenAI-compatible endpoint

**Smart Routing**: Assign cheap models to analysis, premium to writing (45% cost savings).

### 5. Rich Export

- PDF (via ReportLab)
- EPUB (via ebooklib)
- HTML web reader
- ZIP with full story content (chapters, image prompts, character sheets)

### 6. Interactive Branch Reader

Choose-your-own-adventure mode: LLM generates branching narrative paths.

## Technical Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.10+, FastAPI, Uvicorn |
| Frontend | Alpine.js 3, TypeScript, Tailwind CSS |
| Streaming | Server-Sent Events (SSE) |
| AI/LLM | Any OpenAI-compatible API |
| Image Generation | IP-Adapter (character consistency), diffusion models (scene backgrounds) |
| Storage | PostgreSQL (persistent), SQLite (cache), JSON (prompts) |
| Export | ReportLab (PDF), ebooklib (EPUB), custom HTML |
| Auth | JWT (signed with SECRET_KEY) |
| Monitoring | Prometheus, Grafana, Loki |
| Containerization | Docker, Docker Compose |

## Project Structure

```
├── api/                 → REST endpoints (FastAPI routes)
├── services/            → Business logic (LLM, quality scoring, auth)
├── pipeline/            → 2-layer generation + 13 agents
├── middleware/          → JWT auth, rate limiting, audit logging
├── models/              → Pydantic schemas
├── web/                 → Alpine.js SPA (TypeScript)
├── ui/                  → Gradio UI (legacy compatibility)
├── data/prompts/        → Customizable agent prompts (YAML)
├── monitoring/          → Prometheus, Grafana, Loki configs
├── tests/               → 73 test files, 18K+ LOC
├── Dockerfile           → Container image
└── docker-compose.production.yml → Full stack with monitoring
```

## Phase A: L2 Signal Integration Deliverables

### 1. Arc Waypoint Gates (`pipeline/layer2_enhance/_agent.py`)
- CharacterAgent now stores `waypoint_floor` (min arc progress) and `waypoint_stage` (max arc progress)
- `set_waypoint()` method enforces character arc gates during dialogue generation
- Prevents L2 agents from contradicting L1 arc trajectories

### 2. Pacing Directive Routing (`pipeline/layer2_enhance/enhancer.py` + `adaptive_intensity.py`)
- `_extract_pacing_directive()` parses L1 draft for pacing cues (slow_down, escalate, neutral)
- AdaptiveController maps directives to DRAMA_TARGET: slow_down=0.55, escalate=0.75
- Scene enhancement threshold adjusts dynamically based on pacing

### 3. Plot Thread Validation (`pipeline/layer2_enhance/simulator.py`)
- `_is_event_thread_valid()` gates resolution events against PlotThread.status
- Prevents L2 agents from resolving threads L1 marked as unresolved
- Validates event logic against structured narrative from L1

### 4. Signal-Aware Scene Enhancement (`pipeline/layer2_enhance/scene_enhancer.py`)
- SCORE_SCENE_DRAMA and ENHANCE_SCENE prompts gain `preserve_facts`, `thread_status`, `arc_context` fields
- `_scenes_from_summary()` skip-extraction gate prevents fact loss during dramatization
- Ensures L2 rewrites respect L1 narrative anchors

### 5. Chapter Contract Attachment (`pipeline/layer1_story/batch_generator.py`)
- L1 now attaches ChapterContract to each Chapter object
- Contract specifies arc_waypoints, thread_dependencies, and validation gates
- Applied in both serial and parallel generation paths

### 6. Config Flags (`config/defaults.py`)
- `l2_use_l1_signals` (default: enabled) — Master signal integration toggle
- `l2_causal_audit` — Log signal flow for debugging
- `l2_thread_pressure` — Enforce stricter thread validation
- `l2_contract_gate` — Enforce contract boundaries

### 7. Test Coverage (`tests/test_l2_signal_integration.py`)
- 16 new tests validating arc waypoint gates, pacing directive mapping, thread validation, and scene fact preservation
- Tests cover both enabled and disabled signal integration scenarios

## P3 Sprint Deliverables

### 1. Production Redis Security
- Added `--requirepass ${REDIS_PASSWORD}` to redis-server command
- Updated health checks to use `-a` flag for authentication
- `.env.production` requires strong random `REDIS_PASSWORD`

### 2. Horizontal Scaling Support
- Nginx upstream now uses `ip_hash` for sticky sessions
- SSE streams route to same app instance
- Enables: `docker compose --scale app=3`

### 3. Enhanced Health Checks
- `/api/health/deep` includes `scale_ready` field
- Confirms Redis + PostgreSQL healthy before scaling
- Fixed duplicate `critical_failed` logic

### 4. Database Connection Pooling
- SQLAlchemy engine cached globally in health checks
- Faster repeated health probes (reuses connection pool)
- Reduced connection overhead

### 5. Deprecation Warnings
- `BrowserAuth.__init__()` emits DeprecationWarning
- `DeepSeekWebClient.__init__()` emits DeprecationWarning
- Settings tab centralizes deprecation logging via `_get_browser_auth()` helper
- DRY refactor: eliminates code duplication

## Requirements

### Functional Requirements

| ID | Requirement | Status |
|----|-------------|--------|
| F1 | 2-layer pipeline with real-time streaming | Complete |
| F2 | 13 AI agents with autonomous interactions | Complete |
| F3 | Quality scoring with auto-revision | Complete |
| F4 | Multi-provider LLM support | Complete |
| F5 | Rich export (PDF, EPUB, HTML, ZIP) | Complete |
| F6 | Interactive branch reader | Complete |
| F7 | Dark/Light theme toggle | Complete |
| F8 | Checkpoint & resume on interrupted pipelines | Complete |
| F9 | API key authentication (recommended) | Complete |
| F10 | Browser auth (deprecated in v3.x) | Deprecated, removal in v4.0 |

### Non-Functional Requirements

| ID | Requirement | Status |
|----|-------------|--------|
| NF1 | Support horizontal scaling to 3+ instances | P3 Sprint |
| NF2 | Redis password authentication in production | P3 Sprint |
| NF3 | Sticky session routing for SSE streams | P3 Sprint |
| NF4 | Health check API with scale_ready flag | P3 Sprint |
| NF5 | Database connection pooling | P3 Sprint |
| NF6 | L1 signal integration for L2 (Phase A) | Phase A |
| NF7 | Sub-2s response time for shallow health checks | Target |
| NF8 | Support single & multi-instance deployments | Complete |
| NF9 | Prometheus + Grafana monitoring | Complete |
| NF10 | Audit logging (PostgreSQL-backed) | Complete |
| NF11 | JWT auth with token revocation | Complete |

## Acceptance Criteria (P3 Sprint)

### Scaling Support
- [x] Multi-instance deployment: `docker compose --scale app=3` works end-to-end
- [x] Nginx sticky sessions route SSE to same instance
- [x] Redis shared state across instances
- [x] Health checks confirm scaling readiness

### Security
- [x] Redis requires password authentication in production
- [x] Health check logs use redis-cli `-a` flag
- [x] `.env.production.example` documents `REDIS_PASSWORD`

### Performance
- [x] Connection pooling reduces health check latency
- [x] Cached SQLAlchemy engine reuses connections
- [x] `/api/health/deep` completes in <2s

### Code Quality
- [x] Deprecation warnings added to browser auth
- [x] Settings tab DRY refactored via `_get_browser_auth()`
- [x] No duplicate code in health check logic
- [x] All tests passing (ruff lint, pytest coverage)

## Deprecation Timeline

| Version | Browser Auth Status |
|---------|-------------------|
| v3.0-3.x | Available + DeprecationWarning |
| v4.0 | REMOVED |

See [deprecations-v4-migration.md](./deprecations-v4-migration.md) for migration guide.

## Success Metrics

- **Deployment time**: Single instance: < 5 min, Multi-instance: < 10 min
- **Uptime**: 99.5% SLA (target)
- **API latency**: p95 < 500ms (streaming excluded)
- **Health check latency**: < 2s
- **Test coverage**: > 80% (services, api, pipeline)

## Next Steps (Post-P3)

1. **Database Replication**: Master-replica setup for HA
2. **Redis Sentinel/Cluster**: High availability for Redis
3. **Load Balancer**: External LB (CloudFlare, AWS ALB, etc.)
4. **Cost Optimization**: Smart model routing refinement
5. **Agent Improvements**: Deeper conflict analysis, better pacing

## Contact & Contribution

- **GitHub**: https://github.com/HieuNTg/STORYFORGE
- **Issues**: File bugs or feature requests via GitHub Issues
- **Discussions**: Community Q&A at GitHub Discussions
- **Contributing**: See [CONTRIBUTING.md](../CONTRIBUTING.md)
