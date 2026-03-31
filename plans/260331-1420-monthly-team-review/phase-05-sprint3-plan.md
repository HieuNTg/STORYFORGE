# Phase 05 — Sprint 3 Plan

**Sprint**: April 29 - May 12, 2026 | **Duration**: 2 weeks | **Team**: 8 members

**Status**: DONE | **Completed**: 2026-03-31

---

## Sprint Goal

Close all remaining P1 items (async tests, SSE integration tests, onboarding analytics), deliver frontend resilience (IndexedDB fallback), observability (Prometheus metrics), and accessibility baseline.

---

## Selected Items

| ID | Item | Owner | Effort | Priority |
|----|------|-------|--------|----------|
| P1-7 | Async test migration (batch 1) | Phuong Linh | 10h | P1 |
| P1-9 | SSE integration tests | Phuong Linh | 6h | P1 |
| P1-10 | Onboarding analytics | Mai Lan + Quang Huy | 4h | P1 |
| P2-2 | IndexedDB fallback for storage | Thanh Ha | 6h | P2 |
| P2-3 | Prometheus metrics endpoint | Quang Huy | 8h | P2 |
| P2-4 | Accessibility baseline | Mai Lan | 10h | P2 |
| P3-7a | Split prompts.py (571 lines) | Minh Tuan | 4h | P3 |
| — | Testing & review overhead | Phuong Linh | 4h | — |

**Total Sprint Effort**: 52h across 8 people

---

## Task Details

### P1-7: Async test migration batch 1 (10h)

Migrate top 50 endpoint tests from sync `TestClient` to `httpx.AsyncClient`. Add `pytest-asyncio` for async test support. Prioritize `api/pipeline_routes.py` and SSE endpoints.

**Files**: `tests/test_api_async.py` (new), `requirements.txt` (add pytest-asyncio)
**Success Criteria**: 50 tests migrated to async. CI green. Async-specific bugs logged.

### P1-9: SSE integration tests (6h)

Add end-to-end SSE stream tests: connection lifecycle, event ordering, interruption detection, reconnection behavior.

**Files**: `tests/test_sse_integration.py` (new)
**Dependencies**: P1-7 (async test infrastructure)
**Success Criteria**: 8+ SSE lifecycle tests covering connect/stream/interrupt/resume.

### P1-10: Onboarding analytics (4h)

Instrument OnboardingManager with event tracking. Track wizard step completion times, drop-off points. Expose via `/api/analytics/onboarding` endpoint.

**Files**: `services/onboarding_analytics.py` (new), `api/analytics_routes.py` (new)
**Success Criteria**: Each wizard step emits structured log event. Completion funnel queryable via API.

### P2-2: IndexedDB fallback for storage (6h)

When sessionStorage exceeds 5MB quota, auto-fallback to IndexedDB. Transparent to app layer — same API surface. Async read/write with promise-based interface.

**Files**: `web/js/storage-manager.js` (new)
**Success Criteria**: Stories >5MB persist across page refresh. Safari/Chrome/Firefox compatible.

### P2-3: Prometheus metrics endpoint (8h)

Add `/metrics` endpoint with key counters/gauges: pipeline_runs_total, pipeline_duration_seconds, llm_requests_total, llm_errors_total, quality_score_histogram. Use lightweight manual implementation (no heavy dependencies).

**Files**: `services/metrics.py` (new), `api/metrics_routes.py` (new), `app.py` (wire route)
**Success Criteria**: Metrics scrapeable by Prometheus at `/metrics`. Text exposition format.

### P2-4: Accessibility baseline (10h)

Add ARIA labels on all interactive elements in web UI. Keyboard navigation for pipeline controls. `aria-live` regions for SSE status updates. Focus management for modals/panels.

**Files**: `web/index.html`, `web/js/*.js` (ARIA attributes)
**Success Criteria**: Keyboard-only navigation functional for core generate/export flows. ARIA landmarks on all sections.

### P3-7a: Split prompts.py (4h)

Break `services/prompts.py` (571 lines) into logical modules: `prompts/story_prompts.py`, `prompts/analysis_prompts.py`, `prompts/system_prompts.py`. Keep `prompts.py` as re-export hub.

**Files**: `services/prompts/` (new package)
**Success Criteria**: All files <200 lines. All imports unchanged via re-exports.

---

## Definition of Done

1. Code merged to master
2. All existing tests pass (1327+ baseline)
3. New tests added per item criteria
4. Code review score >= 8/10
5. No new files over 200 lines
