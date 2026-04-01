# Phase 07 — Sprint 5 Plan

**Sprint**: May 27 - June 9, 2026 | **Duration**: 2 weeks

**Status**: Done

---

## Sprint Goal

Add OpenRouter free model presets with per-layer routing, plus remaining P3 backlog items (skeleton loader already done in S4, A/B framework, design tokens, CI dashboard).

---

## Selected Items

| ID | Item | Effort | Priority |
|----|------|--------|----------|
| OR-1 | OpenRouter free model presets + per-layer routing | 12h | P1 |
| P3-2 | A/B testing framework for adaptive prompts | 8h | P3 |
| P3-3 | CI timing dashboard | 2h | P3 |
| P3-4 | Design token system | 8h | P3 |

**Total Sprint Effort**: 30h

---

## Task Details

### OR-1: OpenRouter Free Model Presets (12h)

Add OpenRouter free model configurations with per-layer model routing.

**Changes:**

1. **config.py** — Add `MODEL_PRESETS` dict with OpenRouter free tier configs:
   - `openrouter-free-basic`: Single model (Llama-3.3-70B) for all layers
   - `openrouter-free-optimized`: Per-layer routing (Qwen3.6 L1, Llama-3.3 L2, Gemma-3-12B L3)
   - Each preset sets: base_url, model, cheap_model, fallback_models

2. **config.py** — Add `layer_models` field to LLMConfig:
   - `layer1_model`: Model for story generation (optional, falls back to primary)
   - `layer2_model`: Model for drama analysis (optional)
   - `layer3_model`: Model for video/storyboard (optional)

3. **services/llm/client.py** — Add `model_for_layer(layer: str)` method:
   - Returns the configured model for a given layer (1/2/3)
   - Falls back to primary model if layer-specific not set

4. **api/config_routes.py** — Add `POST /api/config/model-presets/{key}` endpoint:
   - Apply a model preset (sets LLM config fields)
   - `GET /api/config/model-presets` — List available presets

5. **web/index.html** — Add "Model Preset" quick-select in Settings page:
   - Dropdown/buttons: "OpenRouter Free (Basic)", "OpenRouter Free (Optimized)", "Custom"
   - Selecting a preset auto-fills base_url, model, API key fields

### P3-2: A/B Testing Framework (8h)

Simple A/B test manager for comparing prompt variants.

**Files:** `services/ab_testing.py` (new), `api/config_routes.py` (add endpoint)
- `ABTestManager` class: define experiments, assign variants, track results
- In-memory storage (like onboarding_analytics)
- API: `POST /api/ab/experiment`, `GET /api/ab/results`

### P3-3: CI Timing Dashboard (2h)

Track and display test execution times.

**Files:** `tests/conftest.py` (add timing fixture), `api/dashboard_routes.py` (add endpoint)
- pytest fixture records per-test duration to `data/test_timings.json`
- Dashboard endpoint returns timing data

### P3-4: Design Token System (8h)

CSS custom properties for consistent theming.

**Files:** `web/css/tokens.css` (new), `web/index.html` (link tokens), `web/dashboard.html` (link tokens)
- Color tokens, spacing, typography, shadows extracted from current Tailwind config
- Dark mode support via `prefers-color-scheme`
