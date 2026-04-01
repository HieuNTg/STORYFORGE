# Code Review — Sprint 5

**Date:** 2026-04-01
**Branch:** master
**Scope:** Sprint 5 changes (OR-1, P3-2, P3-3, P3-4)

---

## Scope

- Files reviewed: `config.py`, `services/llm/client.py`, `api/config_routes.py`, `services/ab_testing.py`, `api/ab_routes.py`, `tests/conftest.py`, `api/dashboard_routes.py`, `web/css/tokens.css`, `api/__init__.py`
- Lines of code analyzed: ~700
- Review focus: Sprint 5 new features — OR-1 model presets, A/B testing, CI timing dashboard, design tokens
- Updated plans: none (no plan file provided; task #56 updated to completed)

---

## Overall Assessment

Code quality is solid overall. Thread-safety design in `ABTestManager` is correct; CI timing plugin is non-intrusive. Three issues warrant attention: a `ZeroDivisionError` crash in the A/B service layer, unbounded memory growth from unlimited experiment creation, and missing auth on sensitive write endpoints. Everything else is medium/low.

---

## Critical Issues

None.

---

## High Priority Findings

### H1 — ZeroDivisionError crash: `assign_variant` with empty variant list

**File:** `services/ab_testing.py:43`

The route-layer Pydantic guard (`min_length=2` on `variants`) prevents this via the API, but `ABTestManager.assign_variant` is a public method callable directly (tests, internal code, future integrations). If `variants` is empty, `int(digest, 16) % len(variants)` raises `ZeroDivisionError`.

```python
# current
index = int(digest, 16) % len(variants)

# fix
if not variants:
    raise ValueError(f"Experiment {experiment_id!r} has no variants")
index = int(digest, 16) % len(variants)
```

### H2 — No cap on experiment count → unbounded memory

**File:** `services/ab_testing.py`

`_experiments` dict grows without bound. Each experiment also allocates a result list. With no auth on `POST /ab/experiments`, any caller can create unlimited experiments and exhaust memory.

Recommend adding `MAX_EXPERIMENTS = 500` and raising `ValueError` in `create_experiment` when exceeded, similar to the existing `MAX_RESULTS` cap.

### H3 — No authentication on A/B write endpoints

**File:** `api/ab_routes.py`

`POST /api/ab/experiments` and `POST /api/ab/experiments/{id}/result` are unauthenticated. Combined with H2, this allows anonymous DoS (memory exhaustion). Other routes in the project use `Depends(get_current_user)` from `middleware/auth_middleware.py`.

```python
from middleware.auth_middleware import get_current_user
from fastapi import Depends

@router.post("/experiments", status_code=201)
def create_experiment(body: CreateExperimentBody, _user=Depends(get_current_user)):
    ...
```

---

## Medium Priority Improvements

### M1 — `model_for_layer` reads `_current_model` without lock

**File:** `services/llm/client.py:85`

`_current_model` is written inside `_client_lock` in `_get_client()` but read in `model_for_layer` without acquiring the lock. Under concurrent requests this is a benign data race (worst case: stale model name, not a crash), but inconsistent with the existing lock discipline.

```python
def model_for_layer(self, layer: int) -> str:
    ConfigManager, _, _ = _imports()
    config = ConfigManager()
    layer_map = {1: config.llm.layer1_model, 2: config.llm.layer2_model, 3: config.llm.layer3_model}
    layer_model = layer_map.get(layer, "")
    with self._client_lock:
        fallback = self._current_model or config.llm.model
    return layer_model or fallback
```

### M2 — `model_for_layer` is dead code

**File:** `services/llm/client.py:72`

No callers exist anywhere in the codebase (`grep` confirms zero usages outside definition). The per-layer routing fields (`layer1_model`, etc.) are stored in config and returned by `GET /config`, but no generation path reads them yet. Either wire it into `_build_fallback_chain` / `generate()` or document explicitly that it is a stub for future use.

### M3 — `PUT /api/config` cannot update layer-specific models

**File:** `api/config_routes.py:16-30`

`ConfigUpdate` Pydantic schema exposes `layer1_model`/`layer2_model`/`layer3_model` in `GET /api/config` response (lines 47-49) but omits them from the write schema. Users can only set layer models via `POST /api/config/model-presets/{key}`, not via manual save. Add the three fields to `ConfigUpdate` for consistency.

```python
class ConfigUpdate(BaseModel):
    ...
    layer1_model: Optional[str] = None
    layer2_model: Optional[str] = None
    layer3_model: Optional[str] = None
```

### M4 — `POST /api/config/presets/{key}` and `POST /api/config/model-presets/{key}` return HTTP 200 on not-found

**File:** `api/config_routes.py:117-130, 139-155`

Both endpoints return `{"status": "error", ...}` with HTTP **200** when key is not found. FastAPI conventions and client JS error-checking expect 4xx. Use `HTTPException(status_code=404)` as done in `ab_routes.py`.

```python
from fastapi import HTTPException
...
if not preset:
    raise HTTPException(status_code=404, detail=f"Preset '{key}' not found")
```

### M5 — Dashboard HTML cached forever in-process, no way to refresh

**File:** `api/dashboard_routes.py:124-127`

`_DASHBOARD_CACHE` is a module-level string set once and never invalidated. In production with hot-reload disabled, deploying an updated `dashboard.html` requires a process restart. Low risk now but worth noting. Could use `functools.lru_cache` with a TTL or simply remove the cache (file I/O is cheap for a dashboard hit).

### M6 — `LLMClient._instance = None` reset called directly from route handlers

**File:** `api/config_routes.py:89, 98, 154`

Three route handlers directly mutate the private `_instance` class variable to force LLMClient re-initialization. This bypasses any future teardown logic and is not thread-safe (another thread could be mid-call). A `LLMClient.reset()` classmethod with proper lock acquisition would be cleaner and safer.

---

## Low Priority Suggestions

### L1 — MD5 in `assign_variant`

**File:** `services/ab_testing.py:42`

MD5 is used purely for deterministic hash distribution, not cryptographic purposes — this is fine. However, some security scanners will flag it. Consider `hashlib.sha256(...).hexdigest()` as a drop-in replacement with no functional difference and no scanner warnings.

### L2 — `backend_type` accepted without validation in `save_config`

**File:** `api/config_routes.py:77-78`

Any string is accepted for `backend_type`. The system only supports `"api"` and `"web"`. Add a Pydantic validator or an enum:

```python
from typing import Literal
backend_type: Optional[Literal["api", "web"]] = None
```

### L3 — `MAX_RESULTS` cap implementation is O(n) slice on every insert when over limit

**File:** `services/ab_testing.py:61-62`

```python
if len(self._results[experiment_id]) > MAX_RESULTS:
    self._results[experiment_id] = self._results[experiment_id][-MAX_RESULTS:]
```

This copies the entire 1000-element list on every insert above the cap. Use `collections.deque(maxlen=MAX_RESULTS)` for O(1) FIFO — the existing `list()` snapshot in `get_results` would still work.

### L4 — Design tokens: no `color-scheme` property set

**File:** `web/css/tokens.css:80-94`

The `@media (prefers-color-scheme: dark)` block overrides surface/text tokens but doesn't add `color-scheme: dark` to `:root`. Browsers use `color-scheme` to style scrollbars and form controls. Add:

```css
@media (prefers-color-scheme: dark) {
  :root {
    color-scheme: dark;
    ...
  }
}
```

### L5 — `conftest.py` timing file: no upper bound on `_timing_records` list in memory

**File:** `tests/conftest.py:23-38`

`_timing_records` accumulates all test results in memory during the session and is sliced to top-50 only at session end. For a large test suite (thousands of tests) this is negligible, but the top-50 slice could be applied per-append or use a `heapq.nlargest` call at the end.

---

## Positive Observations

- `ABTestManager` locking is correct: lock acquired before reading `_experiments`, released before calling `assign_variant` (which re-acquires), preventing deadlock
- `pytest_sessionfinish` never raises — `OSError` is caught and silenced, protecting the test run
- `GET /api/config/model-presets` intentionally strips model names from the response (returns only `label`), preventing accidental exposure of internal model routing
- `apply_model_preset` correctly uses `hasattr` guard preventing arbitrary attribute injection
- `config.py` save method explicitly excludes all API keys from the JSON file with inline comments explaining the pattern
- Design tokens follow a clear `--sf-{category}-{name}` convention and are comprehensive (color, typography, spacing, shadow, radius, animation)
- Static file mount (`/static`) is correctly configured in `app.py`, so `tokens.css` link in HTML will resolve

---

## Recommended Actions

1. **(H1) Fix `ZeroDivisionError`** — add guard in `assign_variant` before the modulo
2. **(H2) Add `MAX_EXPERIMENTS` cap** — prevent unbounded memory growth in `ABTestManager`
3. **(H3) Add auth to A/B write endpoints** — use existing `Depends(get_current_user)` pattern
4. **(M2) Wire or document `model_for_layer`** — it's dead code; either integrate into generation path or add docstring marking as "not yet integrated"
5. **(M3) Add layer model fields to `ConfigUpdate`** — read/write symmetry for API
6. **(M4) Fix preset 404 responses** — raise `HTTPException(404)` not `{"status": "error"}` with 200
7. **(L2) Validate `backend_type`** — use `Literal["api", "web"]` in Pydantic schema
8. **(L3) Use `deque(maxlen=MAX_RESULTS)`** — O(1) FIFO vs O(n) slice

---

## Metrics

- Type Coverage: N/A (Python, no mypy config found)
- Test Coverage: Not measured in this review
- Linting Issues: 0 syntax errors (all files compile clean)
- Findings: 0 Critical, 3 High, 6 Medium, 5 Low

---

## Unresolved Questions

1. Is the A/B testing API intentionally public (no auth required for reads)? Read endpoints (`GET /experiments`, `GET /experiments/{id}/results`) are also unauthenticated — this may be intentional for analytics dashboards but should be confirmed.
2. Is `model_for_layer` planned to be wired into the generation pipeline in Sprint 6, or is it intended as a utility method for external callers only?
3. Should `_DASHBOARD_CACHE` be invalidated between deploys? If the app restarts on deploy this is moot, but if it uses live reload it will serve stale HTML.
