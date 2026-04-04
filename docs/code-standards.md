# Code Standards & Codebase Structure

## Overview

StoryForge follows Python best practices (PEP 20, PEP 8) with ruff for linting and formatting. Frontend uses TypeScript with strict null checks.

## Directory Structure

### Backend (`/`)

```
api/                        → REST endpoints (FastAPI)
  health_routes.py            ✓ Health checks + deep probes
  pipeline_routes.py          ✓ SSE streaming, checkpoint resume
  config_routes.py            ✓ Settings CRUD
  export_routes.py            ✓ PDF/EPUB/ZIP generation
  [other route modules]

services/                   → Business logic (no circular deps to api/)
  llm/                        ✓ LLM client, fallback chain, provider adapters
  quality_scorer.py           ✓ 4-dimension evaluation
  branch_narrative.py         ✓ Interactive story branching
  browser_auth/               DEPRECATED in v3.x
    __init__.py               ✓ BrowserAuth singleton + deprecation warning
    browser_manager.py
    token_extractor.py
    auth_flow.py
  deepseek_web_client.py      DEPRECATED in v3.x, emits DeprecationWarning
  i18n.py                     ✓ Translation singleton
  llm_cache.py                ✓ SQLite TTL cache
  [other service modules]

pipeline/                   → 2-layer generation engine
  orchestrator.py             ✓ Checkpoint & resume
  layer1_story/               ✓ Story generation layer
  layer2_enhance/             ✓ Drama simulation (13 agents)
  agents/                     ✓ Stateless agent implementations

middleware/                 → Cross-cutting concerns
  auth.py                     ✓ JWT validation
  rate_limiting.py            ✓ Redis-backed per-IP throttling
  audit_logging.py            ✓ Request/response audit trail

models/                     → Pydantic schemas
  schemas.py                  ✓ Shared data models (no business logic)

config.py                   → ConfigManager singleton (lazy init)
app.py                      → FastAPI app entry point
requirements.txt            → Python dependencies
```

### Frontend (`web/`)

```
web/
  index.html                  ✓ SPA root, Tailwind CSS
  js/
    app.ts                    ✓ Main Alpine app instance
    components/               ✓ Alpine components (inputs, dialogs, loaders)
    pages/
      create.ts               ✓ Story creation page
      reader.ts               ✓ Story reading + styling
      branching.ts            ✓ Interactive branch navigation
    utils/                    ✓ API client, theme toggler, etc.
  css/
    main.css                  ✓ Tailwind + custom styles

ui/                         → Gradio UI (optional, for settings)
  gradio_app.py               ✓ Main Gradio blocks
  tabs/
    settings_tab.py           ✓ Config UI + deprecation warnings via _get_browser_auth()
    [other tabs]
```

### Testing (`tests/`)

```
tests/
  test_layer1_story.py        ✓ Story generation tests
  test_layer2_enhance.py      ✓ Drama simulation tests
  test_quality_scorer.py      ✓ Scoring tests
  test_llm_client.py          ✓ LLM provider tests
  test_health_routes.py       ✓ Health endpoint tests
  integration/                ✓ End-to-end pipeline tests
  fixtures/                   ✓ Mock data, sample stories
```

### Configuration & Deployment

```
.env.example                → Development defaults
.env.production.example      → Production secrets template
docker-compose.yml           → Development stack
docker-compose.production.yml → Production stack (7 services)
Dockerfile                   → Container image
nginx/
  nginx.conf                  ✓ Reverse proxy + ip_hash sticky sessions
  ssl-params.conf            ✓ TLS hardening
monitoring/
  prometheus.yml              ✓ Metrics scrape config
  alert-rules.yml            ✓ Alert thresholds
  grafana/                   ✓ Dashboard provisioning
  loki-config.yml            ✓ Log aggregation
```

## Python Code Standards

### Naming Conventions

| Element | Style | Example |
|---------|-------|---------|
| Modules | kebab-case (if optional) | `browser_auth.py`, `llm_cache.py` |
| Classes | PascalCase | `BrowserAuth`, `QualityScorer` |
| Functions | snake_case | `_check_database()`, `capture_deepseek_credentials()` |
| Constants | UPPER_SNAKE_CASE | `CDP_PORT`, `AUTH_PROFILES_PATH` |
| Private vars | `_leading_underscore` | `_instance`, `_health_engine` |

### Imports

```python
# Standard library first
import logging
import os
import threading
from typing import Optional

# Third-party (blank line before)
import fastapi
from fastapi import APIRouter
import redis

# Local imports (blank line before)
from config import ConfigManager
from services.llm import LLMClient
```

### Type Hints

Required for all public functions:

```python
def score_chapter(text: str, dimensions: list[str]) -> dict[str, float]:
    """Score a chapter across quality dimensions.

    Args:
        text: Raw chapter text to evaluate.
        dimensions: List of dimension names.

    Returns:
        Mapping of dimension name to score in [0.0, 1.0].
    """
    ...
```

### Docstrings

Use triple quotes for all public functions/classes:

```python
class BrowserAuth:
    """Backward-compatible singleton facade over BrowserManager/AuthFlow.

    Credential methods read path constants via _this_module() so that
    mock.patch is respected.

    Attributes:
        _instance: Singleton instance.
        _lock: Thread lock for safe initialization.
    """

    def capture_deepseek_credentials(self, timeout: int = 300) -> tuple[bool, str]:
        """Capture browser cookies and bearer token from DeepSeek.

        Args:
            timeout: Seconds to wait for user login.

        Returns:
            (success: bool, message: str)
        """
        ...
```

### File Length

Target: **< 200 lines per file** (split larger modules into focused sub-modules).

**Example refactor**:
```python
# Before: services/browser_auth.py (400 lines)
class BrowserAuth: ...
class CredentialStore: ...
class BrowserManager: ...

# After (DRY):
services/browser_auth/
  ├── __init__.py           → BrowserAuth re-export
  ├── browser_manager.py    → BrowserManager class
  ├── token_extractor.py    → CredentialStore class
  └── auth_flow.py          → AuthFlow class
```

### Comments & Warnings

Use warnings module for user-facing deprecation (not logging):

```python
import warnings

# In BrowserAuth.__init__():
warnings.warn(
    "BrowserAuth is deprecated and will be removed in v4.0. "
    "Use API key authentication instead.",
    DeprecationWarning,
    stacklevel=2,
)

# In settings_tab.py, centralize via helper:
def _get_browser_auth():
    """Import BrowserAuth with deprecation warning."""
    _log.warning(_DEPRECATION_MSG)
    from services.browser_auth import BrowserAuth
    return BrowserAuth()
```

## Design Patterns

### 1. Singleton Configuration

```python
# config.py
class ConfigManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
            return cls._instance
```

### 2. Thin API Layer

API routes stay thin, business logic lives in services:

```python
# ❌ BAD: Business logic in route
@router.get("/api/score")
async def score_story(text: str):
    dimensions = ["coherence", "drama", "character", "style"]
    scores = {}
    for dim in dimensions:
        score = llm_call(text, dim)  # <- Belongs in services/
        scores[dim] = score
    return scores

# ✓ GOOD: Thin route, logic in service
@router.get("/api/score")
async def score_story(text: str):
    return QualityScorer().score(text)
```

### 3. Stateless Agents

Pipeline agents are stateless, receive all context as arguments:

```python
# ✓ Stateless
def evaluate_drama(chapter: str, characters: list[str], context: dict) -> float:
    """Pure function: inputs → score, no side effects."""
    ...

# ❌ Avoid: Agent with mutable state
class CharacterAgent:
    self.memory = []  # Shared state across instances
```

### 4. Cached Global Instances

For expensive resources (database, cache clients), use global caching:

```python
# api/health_routes.py
_health_engine = None

def _check_database():
    global _health_engine
    if _health_engine is None:
        _health_engine = create_engine(db_url, pool_pre_ping=True)
    with _health_engine.connect() as conn:
        conn.execute(text("SELECT 1"))
```

### 5. Pydantic for Validation

All API inputs/outputs use Pydantic schemas:

```python
from pydantic import BaseModel, Field

class StoryRequest(BaseModel):
    prompt: str = Field(..., min_length=10, max_length=1000)
    genre: str = Field(default="fantasy")
    language: str = Field(default="en")

@router.post("/api/generate")
async def generate(req: StoryRequest):
    ...
```

## Frontend Standards (TypeScript)

### Directory Structure

```
web/js/
  app.ts                      → Main Alpine instance + router
  components/
    dialog.ts                 → Modal component
    story-card.ts            → Reusable story card
  pages/
    create.ts                → Creation page logic
    reader.ts                → Reading + annotations
  utils/
    api.ts                   → HTTP client (fetch wrapper)
    theme.ts                 → Dark/Light mode toggle
```

### Type Safety

```typescript
// ✓ Typed API client
async function fetchStory(id: string): Promise<Story> {
    const resp = await fetch(`/api/stories/${id}`);
    return (await resp.json()) as Story;
}

// ✓ Alpine component with types
interface StoryState {
    title: string;
    status: "generating" | "done" | "error";
    progress: number;
}

export function createStoryComponent(): StoryState {
    return {
        title: "",
        status: "generating",
        progress: 0,
    };
}
```

## Testing Standards

### Test Organization

```
tests/
  conftest.py                 → Pytest fixtures, mocks
  test_health_routes.py       → API endpoint tests
  test_layer2_enhance.py      → Agent logic tests
  integration/
    test_pipeline_end_to_end.py
  fixtures/
    sample_stories.json       → Mock data
```

### Naming & Coverage

- Test files: `test_*.py`
- Test functions: `test_<feature>`
- Coverage target: > 80% (services, api, pipeline)
- Minimum: Core services + critical paths

```python
# tests/test_quality_scorer.py
class TestQualityScorer:
    def test_score_returns_4_dimensions(self):
        scorer = QualityScorer()
        result = scorer.score("Sample story text")
        assert "coherence" in result
        assert "character" in result
```

## Linting & Formatting

### Ruff

```bash
# Check for issues
ruff check .

# Auto-format
ruff format .
```

### Pre-Commit

Projects use pre-commit hooks to enforce standards before commits.

```bash
git commit  # Auto-runs: ruff check, ruff format, tests
```

## No Circular Dependencies

- `api/` may import from `services/` or `pipeline/`
- `services/` may NOT import from `api/`
- `pipeline/` may import from `services/` but NOT vice-versa

```
api/       ─→  services/  ─→  pipeline/
              ↖________________↙
              (bidirectional models/ only)
```

## Documentation Requirements

- All public functions: docstring with Args, Returns, Raises
- Complex logic: inline comments explaining "why", not "what"
- Architecture: `docs/system-architecture.md`
- Deprecations: `docs/deprecations-v4-migration.md`
- Deployment: `docs/deployment-production.md`

## Error Handling

```python
# ✓ Specific exceptions, informative messages
class LLMClientError(Exception):
    """Raised when LLM API call fails."""
    pass

try:
    response = llm_client.generate(prompt)
except requests.RequestException as e:
    raise LLMClientError(f"LLM API unreachable: {e}") from e

# In routes:
try:
    result = QualityScorer().score(text)
except LLMClientError as e:
    logger.error(f"Scoring failed: {e}")
    return JSONResponse(status_code=503, content={"error": str(e)})
```

## Security Best Practices

1. **Never log secrets**: API keys, passwords, tokens
2. **Use environment variables**: `.env` for dev, `.env.production` for prod
3. **Validate inputs**: Pydantic schemas for all API routes
4. **Rate limiting**: Redis-backed per-IP throttling enabled by default
5. **CORS**: Whitelist via `ALLOWED_ORIGINS` env var
6. **JWT**: Always sign tokens with `SECRET_KEY`

## Performance Checklist

- Connection pooling enabled (PostgreSQL, Redis)
- Caching layer for LLM responses (SQLite, 7-day TTL)
- Gzip compression enabled on HTTP responses
- HTTP/2 support in nginx
- Async/await for I/O (database, HTTP, file ops)
- Query optimization: no N+1 queries

## Deprecation Process

1. Add `DeprecationWarning` with clear migration path
2. Log warning whenever deprecated code is used
3. Document in `docs/deprecations-v4-migration.md`
4. Mark removal version (e.g., v4.0)
5. Remove in major version bump

Example:
```python
# v3.x
def deprecated_function():
    warnings.warn("...", DeprecationWarning)

# v4.0
# Function removed entirely
```
