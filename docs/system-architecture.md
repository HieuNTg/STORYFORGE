# System Architecture

## Overview

StoryForge is a 2-layer AI story generation pipeline with a FastAPI backend, Alpine.js frontend, and production-ready monitoring stack.

```
User Input
    ↓
┌─────────────────────────────────────┐
│   Layer 1: Story Generation         │
│   (Characters, World, Chapters)     │
└────────────┬────────────────────────┘
             ↓
┌─────────────────────────────────────┐
│   Layer 2: Drama Simulation         │
│   (13 AI Agents, Conflict Analysis) │
└────────────┬────────────────────────┘
             ↓
┌─────────────────────────────────────┐
│   Image Generation                  │
│   (Character Consistency + Scenes)  │
└────────────┬────────────────────────┘
             ↓
        Export (PDF/EPUB/HTML/ZIP)
```

## Layer 1 Pipeline: Story Generation

Layer 1 generates story structure in stages:

```
1. Setup (characters, world, outline)
   ↓
2. Batch Generation (parallel chapter writing)
   ├─ Outline critique + revision loop
   ├─ Scene decomposition
   ├─ Character voice profiling
   └─ Theme premise anchoring
   ↓
3. Chapter Writing (per-chapter)
   ├─ Format context (story bible or rolling summaries)
   ├─ Call LLM with adaptive prompt
   ├─ Optional self-review & revision
   ├─ Extract: summary, character states, plot events
   ├─ Consistency validation (zero-cost heuristics)
   ├─ Story bible update (timeline, locations, threads)
   └─ Show-don't-tell enforcement
   ↓
4. Continuation (resume from checkpoint)
   ├─ Fetch last written chapter
   ├─ Rebuild context window
   └─ Resume at next chapter
```

**Key Components** (`pipeline/layer1_story/`):
- `generator.py` — Main orchestrator, calls batch_generator or story_continuation
- `batch_generator.py` — Parallel chapter generation with quality gates
- `chapter_writer.py` — Chapter text generation with context formatting
- `consistency_validators.py` — Non-fatal post-write validation (timeline, names, arc drift)
- `story_bible_manager.py` — Long-term memory for 100+ chapter stories
- `post_processing.py` — Summary, state, event extraction + context updates
- `story_continuation.py` — Resume generation from checkpoint

**Quality Enhancements** (Phase 1):
- Theme premise anchoring (semantic consistency)
- Character voice profiling (dialogue distinctiveness)
- Outline critique & revision loop (structural coherence)
- Scene decomposition (pacing control)
- Show-don't-tell enforcement (narrative quality)
- Chapter self-critique (consistency review)

## Core Services Architecture

### Backend Stack

**Python 3.10+ / FastAPI / Uvicorn**

```
api/                    → REST endpoints (thin layer)
  ├── pipeline_routes.py    → SSE streaming, resumable checkpoints
  ├── health_routes.py      → Health checks with scale_ready flag
  ├── config_routes.py      → Settings CRUD
  └── export_routes.py      → PDF/EPUB/ZIP generation

services/               → Business logic
  ├── llm/                  → LLM client with fallback chain
  ├── quality_scorer.py     → 4-dimension evaluation (coherence, character, drama, style)
  ├── branch_narrative.py   → Choose-your-own-adventure reader
  ├── browser_auth/         → DEPRECATED in v3.x, removed in v4.0
  └── deepseek_web_client.py → DEPRECATED in v3.x, removed in v4.0

pipeline/               → 2-layer generation engine
  ├── orchestrator.py       → Checkpoint & resume logic
  ├── layer1_story/         → Story generation agents
  ├── layer2_enhance/       → Drama simulation (13 agents)
  └── agents/               → Stateless AI agent implementations

middleware/             → Cross-cutting concerns
  ├── auth.py               → JWT token validation
  ├── rate_limiting.py      → Per-IP rate limiting (Redis-backed)
  └── audit_logging.py      → Request/response audit trail

models/schemas.py       → Pydantic data models

config.py               → Singleton config manager
```

### Frontend Stack

**Alpine.js 3 + TypeScript + Tailwind CSS**

```
web/
  ├── index.html            → SPA root
  ├── js/                   → TypeScript source (compiled to JS)
  │   ├── app.ts            → Main Alpine app instance
  │   ├── components/       → Reusable Alpine components
  │   └── pages/            → Page-specific logic (create, reader, branching)
  └── css/main.css          → Tailwind utilities + custom styles
```

**Dark/Light Mode**: Full theme synchronization via CSS variables and localStorage.

### Data Persistence

| Storage | Purpose | Multi-Instance |
|---------|---------|-----------------|
| PostgreSQL | Persistent story data, user config, audit logs | Shared (required) |
| SQLite | LLM response cache (local), embeddings | Per-instance (optional) |
| Redis | Rate limiting, token revocation, session state | Shared (required for scale) |
| JSON files | Agent prompts, presets, exports | Mounted volume |

## Phase 1 Consistency Architecture

### Consistency Validation Pipeline

Post-write validation runs in `pipeline/layer1_story/post_processing.py`:

```
Chapter Written
    ↓
[Non-fatal Validators - Parallel / Sequential]
    ├─ Timeline & Location Extraction (1 cheap LLM call)
    ├─ Character Name Validation (Regex, zero cost)
    └─ Arc Drift Detection (Heuristic, zero cost)
    ↓
Story Context Updated
    ├─ timeline_positions dict
    ├─ character_locations dict
    ├─ arc_drift_warnings list
    └─ name_warnings list
    ↓
Story Bible Updated (if enabled)
    ├─ timeline_positions capped at 30
    ├─ character_locations capped at 30
    ├─ milestone_events tracked
    └─ active_threads managed (20-entry cap)
    ↓
Chapter Write Prompt Enhanced
    └─ _append_consistency_context() injects:
       ├─ Timeline markers (mốc thời gian)
       ├─ Character locations (vị trí)
       ├─ Arc drift warnings ([CẢNH BÁO])
       └─ Name issues ([TÊN NHÂN VẬT])
```

**Key Design Principles**:
1. **Non-fatal**: Validation failures don't crash pipeline; logged as warnings
2. **Cheap**: Name validation (regex) and arc drift (heuristic) have zero LLM cost
3. **Contextual**: Warnings fed back into next chapter's LLM prompt
4. **Capped**: Timeline/location storage bounded at 30 entries (prevent memory bloat)

**Vietnamese Localization**:
- Arc stages: setup (giới thiệu), rising (phát triển), testing (thử thách), crisis (khủng hoảng), climax (cao trào), resolution (giải quyết)
- Warnings and prompts fully in Vietnamese

### Always-On Story Bible

Story Bible is now mandatory (no opt-out):
- Initialized with `StoryBibleManager.initialize()`
- Updated after each chapter with new events, threads, and timeline data
- Provides long-term memory context for chapters 100+
- Replaces rolling window approach for large stories

## P3 Sprint Architecture Changes

### 1. Redis Authentication & Security

**Change**: Production Redis now requires password authentication.

```yaml
# docker-compose.production.yml
redis:
  command: redis-server --appendonly yes --appendfsync everysec --requirepass ${REDIS_PASSWORD}
  healthcheck:
    test: ["CMD", "redis-cli", "-a", "${REDIS_PASSWORD}", "ping"]
```

**Impact**:
- `REDIS_URL` now includes password: `redis://:${REDIS_PASSWORD}@redis:6379/0`
- Health check script uses `-a "${REDIS_PASSWORD}"` flag
- Environment: `.env.production` requires `REDIS_PASSWORD` (min 32 chars)

### 2. Nginx Sticky Sessions for Horizontal Scaling

**Change**: `ip_hash` directive added to nginx upstream block for SSE stream affinity.

```nginx
upstream storyforge_app {
    ip_hash;  # Route same client IP to same app instance
    server app:7860;
    keepalive 32;
}
```

**Why**: Server-Sent Events (SSE) streams for pipeline progress must route to the same app instance.

**Impact**:
- Enables horizontal scaling: `docker compose --scale app=3`
- Client IP → consistent app instance routing
- Required for multi-instance deployments with SSE

### 3. Health Check API Enhancement

**Change**: Deep health check now includes `scale_ready` field.

```python
# api/health_routes.py
scale_ready = redis_ok and db_ok

return JSONResponse(
    content={
        "status": overall,
        "scale_ready": scale_ready,
        "components": checks,
    }
)
```

**Fields**:
- `scale_ready` (bool): `True` if Redis + PostgreSQL are both healthy
- `components`: Per-component status (database, redis, disk, memory, llm)
- `status`: overall ("ok" if no critical failures, "degraded" otherwise)

**Use case**: Orchestrators check `scale_ready` before scaling to N instances.

### 4. Cached SQLAlchemy Engine

**Change**: Database connection pooling now uses a cached engine instance.

```python
# api/health_routes.py
_health_engine = None

def _check_database():
    global _health_engine
    if _health_engine is None:
        _health_engine = create_engine(db_url, pool_pre_ping=True, ...)
    with _health_engine.connect() as conn:
        conn.execute(text("SELECT 1"))
```

**Benefits**:
- Faster health checks (reuses connection pool)
- Reduced connection overhead on repeated probes
- Single engine per health check process

### 5. Deprecation Warnings for Browser Auth

**Changes**:
- `services.browser_auth.BrowserAuth` → emits `DeprecationWarning` on init
- `services.deepseek_web_client.DeepSeekWebClient` → emits `DeprecationWarning` on init
- UI helper `_get_browser_auth()` → centralizes deprecation logging in settings tab

**Code**:
```python
# services/browser_auth/__init__.py
def __init__(self):
    warnings.warn(
        "BrowserAuth is deprecated and will be removed in v4.0. "
        "Use API key authentication instead.",
        DeprecationWarning,
        stacklevel=2,
    )
```

```python
# ui/tabs/settings_tab.py
_DEPRECATION_MSG = (
    "BrowserAuth (browser-based credential capture) is deprecated and will be "
    "removed in v4.0. Use API key authentication (STORYFORGE_API_KEY) instead."
)

def _get_browser_auth():
    """Import BrowserAuth with deprecation warning. Raises on failure."""
    _log.warning(_DEPRECATION_MSG)
    from services.browser_auth import BrowserAuth
    return BrowserAuth()
```

**DRY Refactor**: Settings tab now centralizes all browser auth calls through `_get_browser_auth()`, eliminating code duplication.

## Deployment Architecture

### Development

```bash
python app.py  # Single container, SQLite cache, no Redis required
```

### Production (Single Instance)

```bash
docker compose -f docker-compose.production.yml up -d
# Requires: PostgreSQL, Redis, Nginx, monitoring stack
```

### Production (Multi-Instance Scaling)

```bash
docker compose -f docker-compose.production.yml up -d --scale app=3
# Sticky sessions (nginx ip_hash) + Redis shared state + PostgreSQL replication
```

## High-Availability Considerations

For production HA deployments:

1. **Database**: PostgreSQL replication (host or managed service)
2. **Redis**: Sentinel or Cluster mode for high availability
3. **Load Balancer**: Keep nginx or deploy external LB with sticky sessions
4. **Monitoring**: Prometheus + Grafana for alerting

See [deployment-production.md](./deployment-production.md) for detailed setup.

## Performance & Caching

**LLM Cache**:
- SQLite (local, per-instance)
- TTL-based expiration
- Reduces API calls by caching similar prompts

**Connection Pooling**:
- PostgreSQL: `pool_pre_ping=True` for safe connection reuse
- Redis: Built-in connection pooling via redis-py
- HTTP: Nginx keepalive connections to app

**Rate Limiting**:
- Redis-backed (shared across instances)
- Per-IP throttling
- Token bucket algorithm

## Security Architecture

**JWT Authentication**:
- Tokens signed with `SECRET_KEY`
- Stored in browser cookies (HttpOnly, Secure flags)
- Validated on every API request

**CORS**:
- Whitelist configured via `ALLOWED_ORIGINS`
- Prevents cross-site request forgery

**TLS/SSL**:
- Nginx terminates HTTPS
- Let's Encrypt certificates (auto-renewed via certbot)
- HSTS enforced (max-age=63072000)

**Audit Logging**:
- All API requests logged with timestamp, user, endpoint, status
- Stored in PostgreSQL for forensics
