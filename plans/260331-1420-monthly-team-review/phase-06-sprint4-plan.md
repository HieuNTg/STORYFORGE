# Phase 06 — Sprint 4 Plan

**Sprint**: May 13 - May 26, 2026 | **Duration**: 2 weeks | **Team**: 8 members

**Status**: DONE | **Completed**: 2026-04-01

---

## Sprint Goal

Deliver multi-tenancy MVP, analytics dashboard, fix Sprint 3 review findings (unbounded events, input validation, metrics auth), skeleton loader, and split remaining large files.

---

## Selected Items

| ID | Item | Owner | Effort | Priority |
|----|------|-------|--------|----------|
| CR-3 | Fix Sprint 3 code review findings | Minh Tuan | 3h | P1 |
| P2-6 | Multi-tenancy MVP (JWT auth + user-scoped storage) | Hai Long + Quang Huy | 20h | P2 |
| P2-7 | Analytics dashboard (Chart.js) | Duc Tri + Mai Lan | 16h | P2 |
| P3-1 | Skeleton loader for page init | Thanh Ha | 2h | P3 |
| P3-7b | Split tts_audio_generator.py (554 lines) | Minh Tuan | 6h | P3 |
| P3-7c | Split llm_client.py (573 lines) | Minh Tuan | 6h | P3 |
| — | Testing & review overhead | Phuong Linh | 4h | — |

**Total Sprint Effort**: 57h across 8 people

---

## Task Details

### CR-3: Fix Sprint 3 code review findings (3h)

Address 3 high-priority findings from code review:
1. **OnboardingTracker unbounded events**: Add max_events cap (10,000) with FIFO eviction
2. **Analytics input validation**: Add max_length constraints on session_id (64) and step (128) fields
3. **Metrics endpoint auth**: No change — metrics endpoints are typically unauthenticated for Prometheus scraping. Document this decision.

**Files**: `services/onboarding_analytics.py`, `api/analytics_routes.py`
**Success Criteria**: Events list capped. Input validated. No behavior regression.

### P2-6: Multi-tenancy MVP (20h)

JWT-based authentication middleware. User registration/login endpoints. User-scoped story storage using SQLite database (per validation decision). Pipeline runs bound to authenticated user.

**Files**: `services/auth.py` (new), `api/auth_routes.py` (new), `services/user_store.py` (new), `middleware/auth_middleware.py` (new), `app.py` (wire middleware)
**Dependencies**: P0-2 (secrets encryption — done)
**Success Criteria**: Two users create stories without seeing each other's data. JWT validated on protected endpoints. Registration + login functional.

### P2-7: Analytics dashboard (16h)

Dashboard page at `/dashboard` with Chart.js visualizations. Quality score trends, genre distribution, pipeline success/failure rates, onboarding funnel. Data from Prometheus metrics + onboarding analytics APIs.

**Files**: `web/dashboard.html` (new), `web/js/dashboard.js` (new), `api/dashboard_routes.py` (new)
**Dependencies**: P2-3 (Prometheus metrics — done), P1-10 (onboarding analytics — done)
**Success Criteria**: Dashboard renders with real data. Charts: quality score trend, pipeline runs by status, onboarding funnel. Accessible at `/dashboard`.

### P3-1: Skeleton loader for page init (2h)

Show CSS skeleton placeholder while Alpine.js initializes and storageManager loads saved state. Replace flash of empty content.

**Files**: `web/index.html` (skeleton markup + CSS)
**Success Criteria**: No flash of unstyled/empty content on page load. Skeleton visible for >100ms on slow connections.

### P3-7b: Split tts_audio_generator.py (6h)

Break `services/tts_audio_generator.py` (554 lines) into logical modules: `tts/voice_generator.py`, `tts/audio_processor.py`, `tts/storyboard_narrator.py`. Keep `tts_audio_generator.py` as re-export hub.

**Files**: `services/tts/` (new package)
**Success Criteria**: All files <200 lines. All imports unchanged via re-exports.

### P3-7c: Split llm_client.py (6h)

Break `services/llm_client.py` (573 lines) into: `llm/base_client.py`, `llm/provider_handlers.py`, `llm/retry_logic.py`. Keep `llm_client.py` as re-export hub.

**Files**: `services/llm/` (new package)
**Success Criteria**: All files <200 lines. All imports unchanged via re-exports.

---

## Definition of Done

1. Code merged to master
2. All existing tests pass (1362+ baseline)
3. New tests added per item criteria
4. Code review score >= 8/10
5. No new files over 200 lines
