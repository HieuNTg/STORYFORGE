# StoryForge Codebase Summary

**Repository**: https://github.com/HieuNTg/STORYFORGE
**Language**: Python 3.10+, TypeScript, HTML/CSS
**Total Files**: 376 | **Total Tokens**: 560K | **Lines of Code**: 50K+

## Project Overview

StoryForge is an AI-powered story generation engine with multi-agent drama simulation. It takes a one-sentence idea and produces a complete, drama-rich story with character-consistent images and cinematic scene backgrounds.

**2-Layer Pipeline**:
1. Story Generation (characters, world, chapters)
2. Drama Simulation (13 AI agents, conflict analysis)
3. Image Generation (character consistency + scene backgrounds, runs after Layer 2)

## Technology Stack

| Component | Technology |
|-----------|-----------|
| Backend | Python 3.10+, FastAPI, Uvicorn |
| Frontend | Alpine.js 3, TypeScript, Tailwind CSS |
| Database | PostgreSQL (persistent), SQLite (cache) |
| Cache/Session | Redis (rate limiting, session state) |
| Reverse Proxy | Nginx (sticky sessions, TLS termination) |
| Monitoring | Prometheus, Grafana, Loki |
| Containerization | Docker, Docker Compose |
| LLM Support | OpenAI, Gemini, Anthropic, OpenRouter, Ollama, custom APIs |
| Export | PDF (ReportLab), EPUB (ebooklib), HTML, ZIP |

## Top-Level Directory Structure

```
STORYFORGE/
├── api/                          → FastAPI REST endpoints
├── services/                      → Business logic (LLM, scoring, auth)
├── pipeline/                      → 2-layer generation engine + 13 agents
├── middleware/                    → Auth, rate limiting, audit logging
├── models/                        → Pydantic data schemas
├── config.py                      → Configuration manager singleton
├── app.py                         → FastAPI application entry point
├── web/                           → Alpine.js SPA (TypeScript)
├── ui/                            → Gradio UI (optional, settings tab)
├── data/                          → Runtime data (prompts, cache, config)
├── monitoring/                    → Prometheus, Grafana, Loki configs
├── tests/                         → 73 test files, 18K+ LOC
├── docker-compose.yml            → Development stack
├── docker-compose.production.yml  → Production stack (7 services)
├── Dockerfile                     → Container image
├── nginx/                         → Nginx config (sticky sessions, TLS)
├── requirements.txt               → Python dependencies
├── CONTRIBUTING.md                → Contribution guidelines
├── README.md                      → Project documentation
└── LICENSE                        → MIT license
```

## Core Services (Top 5 by Complexity)

### 1. Pipeline Orchestrator (`pipeline/orchestrator.py`)

**Purpose**: 2-layer generation with checkpoint & resume

**Key Features**:
- Layer-by-layer execution (story → drama → image generation)
- Checkpoint save/load for crash recovery
- Real-time SSE streaming of progress
- Quality gate checks before export

**Integrations**: LLMClient, QualityScorer, ExportService

### 2. Drama Simulator (`pipeline/layer2_enhance/`)

**Purpose**: Multi-agent conflict analysis & auto-revision

**Key Components**:
- 13 AI agents (character agents, critic, editor, pacing, style, dialogue)
- Agent debate system (concurrent agent interactions)
- Conflict detection & scoring
- Auto-revision loop when quality < threshold

**Critical File**: `agent_graph.py` (agent orchestration)

### 3. Quality Scorer (`services/quality_scorer.py`)

**Purpose**: 4-dimension story evaluation (coherence, character, drama, style)

**Features**:
- LLM-as-judge scoring
- Dimension-specific prompts
- Threshold-based revision triggering
- Caching of scores for cost optimization

### 4. LLM Client (`services/llm/`)

**Purpose**: Multi-provider LLM abstraction with fallback chain

**Supported Providers**:
- OpenAI
- Google Gemini
- Anthropic
- OpenRouter
- Ollama
- Custom OpenAI-compatible APIs

**Features**:
- Provider detection & routing
- Fallback chain (auto-retry on failure)
- Token counting (for cost estimation)
- Caching (SQLite TTL)

### 5. Health Check System (`api/health_routes.py`)

**Purpose**: Deep system diagnostics with scaling readiness

**Endpoints**:
- `/api/health` (shallow, fast)
- `/api/health/deep` (full subsystem probe + scale_ready flag)

**Checks**:
- Database (SELECT 1 via cached SQLAlchemy engine)
- Redis (PING with auth)
- Disk (free space %)
- Memory (psutil or /proc/meminfo)
- LLM (reachability test)

**P3 Update**: Includes `scale_ready` field for multi-instance deployments

## Frontend Architecture (`web/`)

**SPA Framework**: Alpine.js 3 with TypeScript

**Pages**:
- Create Story (prompt input, genre/style selection)
- Story Reader (Markdown rendering, annotations, branch navigation)
- Settings (API config, language, compact mode)

**Components**:
- Dialog (modal windows)
- Story card (reusable story display)
- Theme toggle (dark/light mode)

**Styling**: Tailwind CSS utility-first approach

## Data Models (`models/schemas.py`)

Key Pydantic schemas:
- `StoryRequest`: User input (prompt, genre, style)
- `Story`: Complete story with metadata
- `Character`: AI character definition
- `Chapter`: Story chapter with content
- `QualityScore`: 4-dimension scoring result
- `HealthCheckResponse`: System health status

## Configuration System (`config.py`)

**ConfigManager**: Singleton pattern, lazy initialization

**Config Sources** (priority):
1. Environment variables
2. `.env` file (development)
3. `data/config.json` (persistent user settings)
4. Defaults

**Key Settings**:
- LLM provider, model, API key
- Temperature, max tokens, batch size
- Pipeline flags (quality gate, smart revision, agent debate)
- Language (Vietnamese/English)

## Database Schema

**PostgreSQL**:
- Stories (id, title, prompt, status, created_at, updated_at)
- Chapters (story_id, chapter_num, content, quality_score)
- UserSettings (config_json, language)
- AuditLog (timestamp, user, endpoint, status, response_time)

**SQLite** (per-instance cache):
- LLMCache (prompt_hash, response, timestamp, ttl)

## API Endpoints

### Story Generation

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/generate` | POST | Start story generation (SSE streaming) |
| `/api/pipeline/{id}` | GET | Resume checkpointed pipeline |
| `/api/stories` | GET | List all stories |
| `/api/stories/{id}` | GET | Fetch story details |

### Settings & Config

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/config` | GET/PUT | Get/update configuration |
| `/api/config/test` | POST | Test LLM connection |
| `/api/providers` | GET | List available LLM providers |

### Health & Monitoring

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/health` | GET | Shallow health check (fast) |
| `/api/health/deep` | GET | Deep system diagnostics |

### Export

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/export/{id}/pdf` | GET | Export as PDF |
| `/api/export/{id}/epub` | GET | Export as EPUB |
| `/api/export/{id}/html` | GET | Export as HTML |
| `/api/export/{id}/storyboard` | GET | Export as ZIP (shots + scripts) |

## Deployment Architecture

### Development

```bash
python app.py
# Single container, SQLite cache, no external dependencies
```

### Production (Single Instance)

```bash
docker compose -f docker-compose.production.yml up -d
# 7 services: app, postgres, redis, nginx, loki, prometheus, grafana
```

### Production (Multi-Instance)

```bash
docker compose -f docker-compose.production.yml up -d --scale app=3
# Nginx sticky sessions (ip_hash) route SSE to same instance
```

## P3 Sprint Changes

### 1. Redis Authentication
- Added `--requirepass ${REDIS_PASSWORD}` to redis-server
- Health check uses `-a` flag for auth
- `.env.production` requires `REDIS_PASSWORD`

### 2. Nginx Sticky Sessions
- Upstream uses `ip_hash` for client IP affinity
- Ensures SSE streams route to same app instance
- Enables horizontal scaling

### 3. Health Check Enhancements
- `/api/health/deep` now includes `scale_ready` field
- Cached SQLAlchemy engine reduces probe latency
- Fixed duplicate `critical_failed` logic

### 4. Deprecation Warnings
- `BrowserAuth.__init__()` emits DeprecationWarning
- `DeepSeekWebClient.__init__()` emits DeprecationWarning
- Settings tab centralizes via `_get_browser_auth()` helper (DRY)

## Testing Coverage

**Test Files**: 73 (mirrors source structure)

**Coverage**:
- Unit tests for services (80%+)
- Integration tests for pipeline
- API endpoint tests
- Mock LLM responses for deterministic testing

**Key Test Directories**:
- `tests/test_layer1_story.py` → Story generation
- `tests/test_layer2_enhance.py` → Drama simulation
- `tests/test_quality_scorer.py` → Quality evaluation
- `tests/integration/` → End-to-end pipeline tests

## Performance Optimizations

1. **Connection Pooling**: PostgreSQL (pool_pre_ping), Redis (built-in)
2. **LLM Cache**: SQLite TTL cache (7-day default)
3. **Gzip Compression**: HTTP responses
4. **HTTP/2**: Nginx support
5. **Async I/O**: FastAPI + uvicorn
6. **Cached Health Engine**: Reuses SQLAlchemy connection for repeated probes

## Security Features

- **JWT Authentication**: Token-based API auth
- **Rate Limiting**: Redis-backed per-IP throttling
- **CORS**: Whitelist via `ALLOWED_ORIGINS`
- **TLS/SSL**: Nginx HTTPS with Let's Encrypt
- **Audit Logging**: All API requests logged to PostgreSQL
- **Secret Management**: Environment variables for sensitive data

## Monitoring & Observability

**Prometheus Metrics**:
- API request latency (p95, p99)
- Pipeline generation time
- LLM API response times
- Cache hit/miss ratio
- Error rates per endpoint

**Grafana Dashboards**:
- Real-time request rates & latencies
- Story generation success rates
- Agent execution times
- Resource utilization (CPU, memory, disk)

**Loki Logs**:
- Structured logging from all services
- Query-able by timestamp, service, log level

## Code Quality Standards

- **Linting**: ruff check (PEP 8, security rules)
- **Formatting**: ruff format (Black-compatible)
- **Type Hints**: Required for all public functions
- **File Length**: < 200 lines (split large modules)
- **Docstrings**: Required for public functions/classes
- **Circular Imports**: Not permitted (api ← services ← pipeline)

## Deprecations

**Browser-Based Auth** (v3.x):
- `BrowserAuth` class
- `DeepSeekWebClient` class
- Browser Chrome automation for credential capture

**Removal Date**: v4.0

**Migration**: Use API key auth (STORYFORGE_API_KEY env var)

## Key Files to Know

| File | LOC | Purpose |
|------|-----|---------|
| `app.py` | 50 | FastAPI app setup, middleware registration |
| `config.py` | 200 | ConfigManager singleton |
| `api/health_routes.py` | 194 | Health checks (P3: scale_ready, cached engine) |
| `services/quality_scorer.py` | 150 | 4-dimension evaluation |
| `pipeline/orchestrator.py` | 250 | Pipeline execution + checkpoint |
| `pipeline/layer2_enhance/agent_graph.py` | 300 | Multi-agent orchestration |
| `services/llm/__init__.py` | 200 | Multi-provider LLM abstraction |
| `web/js/app.ts` | 180 | Alpine.js main instance |
| `nginx/nginx.conf` | 177 | Proxy config (P3: ip_hash) |
| `docker-compose.production.yml` | 290 | Production stack (P3: Redis auth) |

## Community & Contribution

- **GitHub**: https://github.com/HieuNTg/STORYFORGE
- **Issues**: Bug reports, feature requests
- **Discussions**: Q&A, architecture discussions
- **Contributing**: See CONTRIBUTING.md for setup & PR guidelines

## License

MIT License — Free for personal and commercial use
