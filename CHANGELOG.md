# Changelog

All notable changes to **StoryForge** are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added

- **Chapter length gate (L1)** — a chapter that comes back materially under its word-count target gets one expansion pass built from real material (expanded scenes, dialogue, interiority), never a padding loop; an "expansion" that returns shorter is rejected and the original kept. Toggle + threshold in Settings → Nâng cao L1 (`enable_length_gate`, `length_gate_min_ratio`, default 85%)
- **Streaming stall timeouts are configurable** — `stream_first_chunk_timeout` (180s) and `stream_chunk_timeout` (30s) replace the hard-coded 60s/30s; a reasoning model's time-to-first-token measured a 106s max through the local bridge, so the old ceiling discarded calls mid-thought and silently demoted them down the model chain
- **Colour steering in every image prompt** — panel, scene, refiner, avatar and cover prompts now ask for full colour and negate monochrome/grayscale; comic-style wording ("cel shading", "bold ink lines") otherwise lands on the black-and-white slice of the training data
- **Qwen local proxy image provider** (`image_provider="qwen-local"`) — generate panels through a locally-run OpenAI-compatible proxy in front of chat.qwen.ai. Selectable in Settings → General with its own panel (base URL, API key, model, aspect ratio, timeout, reachability probe). Reference images go to the proxy's edit endpoint, so character likeness is preserved instead of being re-described in text; toggle with `qwen_local_use_edit_for_refs`. See `docs/qwen-local-provider.md`
- **Phase E: Contract Gate** — Validate enhanced chapters against `ChapterContract` (Phase 1 constraints); auto-rewrite if ≥2 critical failures or (≥1 critical + ≥2 warnings); integrated post-causal-audit; feature-flagged `config.pipeline.l2_contract_gate` (default True)

### Removed
- Layer 3 video storyboarding pipeline
- TTS/voice narration (edge-tts)
- Audio player component
- Video composer and exporter

### Changed

- **One comic path for both entry points** — the pipeline media stage ran its own legacy routine (no shot list, no dialogue, no page composition) while the Reader's on-demand button ran the full comic flow, so an end-to-end story came out as loose illustrations. Both now call `services/media/comic_chapter.py`
- **Comic paneling is on by default** — `comic_shot_list_enabled` and `comic_compositor_enabled` flipped to `True`; with them off the product generates illustrations rather than a comic. Failures still degrade to loose panels

### Fixed

- **Arc-execution warnings now reach the consistency rewrite** — `arc_execution_validator` wrote `arc_execution_warnings` to the story context and nothing read it, so a chapter that never executed its planned arc stage was flagged to the log and then shipped unchanged. Both arc warning lists now feed the rewrite (and are cleared together once the content they described is replaced), and the warning is surfaced on the progress channel instead of only the server log
- **`panels_max` is enforced** — nothing bounded the panel count end to end: the coverage verifier inserts up to 6 panels and the bubble rules split more, so a chapter could ship well past the configured ceiling, each extra panel costing an image. Over the ceiling, panels split from the same beat are merged back (same beat + subject + shot, within the 2-bubble limit); beats are never dropped
- **Length-gate and streaming knobs persist** — the four settings existed as code defaults only, so a change never survived a restart and never appeared in the API or the UI
- **Comic pages: balloons no longer escape their panel** — the bubble fitter only ever fit width, so a long line grew the balloon downward past the frame and over the panel below. Height is now budgeted (body + tail ≤ 66% of the frame) and the text shrinks/tightens to fit
- **Comic pages: over-long dialogue is split into several balloons** — `enforce_rules` only moved a long speaker into another panel when it was NOT the first bubble, so the common case (one speaker, one long line) reached the compositor whole. Long lines now split at sentence/clause boundaries into ≤20-word balloons, text preserved in order
- **Comic pages: panels are generated at their cell's aspect** — every panel was square and then center-cropped into its layout cell, discarding >50% of a panel on a `THREE_TIER` page. `panel_target_sizes()` derives WxH per panel from the layout; DALL·E/Codex sizes snap to the nearest supported aspect
- **Comic pages: no more silently dropped panels** — a 5-panel page routed to the 3-cell `BIG_PLUS_TWO` lost two beats. Added `BIG_PLUS_FOUR` (5 cells) and `layout_cells` now widens the layout instead of dropping panels
- **Comic pages: a lone leftover panel fills its page** — it was labelled `TWO_TIER`, leaving the bottom half blank. Added the `SOLO` layout (single cell, without SPLASH's dramatic meaning)
- **Pipeline panel count honours the auto-sizing knobs** — the media stage read `panels_per_chapter` directly and ignored `panels_auto` / `panels_min` / `panels_max` / `words_per_panel`, so the same chapter got a different panel count depending on which route generated it (shared `panels_for_chapter()`)
- **Legacy scene extractor sees the whole chapter** — it truncated prose at 3000 chars (the shot-list path had already moved to 8000), so half of a typical chapter could never be picked as a scene

### Changed
- Thread-safe SSE streaming (RLock + snapshot pattern)
- 98 RBAC + rate limiter middleware tests
- Graceful pipeline shutdown handler
- Form label accessibility (16 inputs)
- PostgreSQL streaming replication standby
- Redis Sentinel failover configuration
- Real staging deployment in CI

### Changed
- Pipeline is now 2-layer: Story Generation → Drama Simulation
- Image generation focuses on character consistency + scene backgrounds
- Dependency pins relaxed to allow patch updates
- Dashboard uses production CSS build instead of Tailwind CDN
- CI security scanning now blocks pipeline on CVE findings

### Fixed

**SSE / pipeline reliability sprint** (multi-agent re-review, 2026-05-29)

- **Dropped logs on disconnect (C1)** — SSE drain loop no longer discards queued log events when the client briefly stalls
- **Errors misreported as `done` (C2/H3)** — failed runs now surface the real error reason instead of a generic message or a false `done`
- **Cancel-on-disconnect data loss (C3)** — the 4 continuation generators (`/continue`, `/regenerate`, `/insert`, `/write-from-outlines`) now run under the job registry and persist their terminal state, so a disconnected client can recover a minutes-long draft instead of silently losing it
- **`/choose/stream` abandonment (C4)** — branch generation runs in a worker thread with a heartbeat and disconnect detection, and still persists the generated node on disconnect (a retry hits the cached path)
- **Duplicate terminal callbacks (C5)** — `onError`/`onClose` no longer fire twice
- **Unbounded queue after disconnect (H4)** — progress callbacks stop enqueueing once the client is gone while still recording logs for recovery
- **Reaper / shutdown robustness (H1/H2)** — strong refs prevent the reaper task being GC'd, stuck `running` jobs are evicted, and pending workers are logged on shutdown
- **Sticky `interrupted` state (H5/H6)** — second runs hydrate correctly and phase-1 progress freezes to total on `done`
- **Torn checkpoint writes (#15)** — checkpoints write to a temp file then `os.replace` atomically, so a crash mid-write can't leave torn JSON
- **Double-unwrapped `done` frame (#17)** — `pipelineBridge` unwraps the done envelope exactly once and hands the same canonical summary to both the store and the caller, removing the scattered `p.data ?? p` fallbacks
- **Chapter-scope clamp + genre override (#18)** — lowering "tổng số chương" now live-clamps "chương phiên này"; a user-edited total is tracked with an explicit touched-flag so a later genre switch never overwrites it
- **Per-IP session cap TOCTOU (#19)** — the session count and insert now happen under a single lock acquire, so concurrent same-IP requests can't blow past `_MAX_SESSIONS_PER_IP`
- **Dead `useEventSource` hook (#20)** — removed unused SSE hook (reconnect-storm footgun); `usePostStream` is the only SSE consumer
- **Misleading sqlite `busy_timeout` (#21)** — dropped the init-only `PRAGMA busy_timeout=5000` that never reached per-op connections; `sqlite3.connect(timeout=30.0)` already installs a uniform 30s busy handler

---

## [1.1.0] — 2026-04-17

### Added

**L1 Improvements**
- **NarrativeContextBlock** — unified prompt context for consistent chapter generation
- **Self-critique with rollback** — automatic rollback on score regression
- **Per-character arc memory cache** — improved character consistency across chapters
- **Consistency block-and-rewrite thresholds** — configurable quality gates
- **Pacing enforcement** — LLM classification for scene pacing (`pacing_enforcer.py`)

**L2 Improvements**
- **Parallel feedback rewrite** — `asyncio.gather` for concurrent chapter processing
- **Knowledge constraints** — prevent hallucination with grounded context
- **Inline contract/voice validation** — real-time validation during enhancement
- **Agent chain-of-thought reasoning** — improved multi-agent debate quality
- **Per-chapter drama intensity** — adaptive drama based on `pacing_type`
- **Coherence pre-check block-and-inject** — catch inconsistencies before enhancement

**Pipeline Features**
- **Per-chapter L2 retry** — exponential backoff on transient failures
- **L3 sensory polish layer** (opt-in) — prose refinement pass
- **Reader simulator agent** (opt-in) — engagement prediction
- **Incremental chapter streaming callback** — real-time chapter delivery

**New Config Flags**
- `l2_chapter_retry_max`, `l2_chapter_retry_backoff` — retry configuration
- `enable_sensory_polish`, `sensory_polish_model` — L3 polish layer
- `enable_reader_simulation`, `reader_engagement_threshold` — reader simulation
- `enable_incremental_publish` — streaming chapter output
- `chapter_critique_every_n_chapters`, `chapter_critique_rollback` — critique controls
- `enable_pacing_enforcement`, `pacing_enforcement_confidence` — pacing enforcement

**New Files**
- `pipeline/layer1_story/pacing_enforcer.py`
- `pipeline/layer1_story/narrative_context_block.py`
- `pipeline/layer2_enhance/sensory_polish.py`
- `pipeline/agents/reader_simulator.py`

---

## [1.0.0] — 2026-04-02

### Added

- **Story Generation Pipeline** — multi-layer AI pipeline (Layer 1 outline,
  Layer 2 drama enhancement, Layer 3 prose) with per-layer model routing
- **Multi-Agent Debate** — LLM-backed debate between named agents to improve
  chapter quality; lite mode for faster runs
- **Story Library UI** — browse, resume, and delete saved stories with hash
  routing and loading states
- **Dynamic Model Discovery** — auto-fetch available OpenRouter models at
  startup; tokenizer improvements
- **Dark Mode + Accessibility** — dark mode toggle, form persistence, ARIA
  improvements, mobile responsive layout
- **Scoring & Calibration** — golden evaluation dataset, LLM-as-judge scoring,
  calibration service, structured output helper
- **Plugin Architecture** — extensible plugin registry for custom agents and
  exporters
- **Vite + Tailwind Build Pipeline** — production-optimised frontend with
  error boundary
- **Voice Narration / TTS** — pluggable TTS provider (XTTS / gTTS), voice
  emotion synthesis
- **RAG World-Building** — retrieval-augmented generation for consistent
  world state across chapters
- **Character-Consistent Images** — IP-Adapter integration for visual
  character profiles
- **EPUB / HTML / Video Export** — EPUB pipeline, HTML reader, SRT + CapCut
  + voiceover video export
- **JWT Key Rotation Manager** — automated JWT secret rotation with audit log
- **SQLAlchemy Async + Alembic** — async ORM with PostgreSQL schema (7 tables)
  and migration support
- **API v1 Router** — versioned REST API with OpenAPI docs, SSE streaming,
  feedback endpoint
- **Redis Rate Limiter + Thread Pool Manager** — production-grade concurrency
  controls
- **Config Repository Pattern** — centralised settings with per-layer model
  presets
- **Community & Open-Source Docs** — CONTRIBUTING.md, setup scripts, feedback UI

### Changed

- Replaced Gradio UI with a custom browser-based web UI (English-first,
  bilingual Vietnamese/English)
- Modularised `config.py`, orchestrator, and Layer 1 prompts into separate
  files (max 200 lines each)
- Upgraded multi-agent debate from prototype to full LLM-backed implementation
- Switched model presets to currently available OpenRouter free models
- Renamed project from **Novel Auto Pipeline** to **StoryForge**

### Fixed

- Vietnamese language drift in later chapters — added language-lock prompt
  layer
- PDF export Vietnamese font — auto-download NotoSans, removed deprecated
  `uni` parameter
- Markdown rendering issues in chapter preview
- Drama score scale calibration off-by-one
- Save logic and page rendering audit — sessionStorage persistence, SSE
  resilience, reactivity fixes
- 31 tracked bugs across cache, pipeline, scoring, RAG, and brancher modules
- Removed broken logo reference and invalid OpenRouter free model IDs

### Security

- Encrypted API keys at rest using Fernet symmetric encryption
- Rate limiting on all public endpoints (configurable per route)
- CORS hardening — explicit origin allowlist, removed wildcard
- Path traversal fix — sanitise all file-path inputs before disk access
- Pip-audit integrated into CI for dependency CVE scanning
- JWT audit logging system for all authentication events
- Production Nginx config with security headers (HSTS, CSP, X-Frame-Options)

### Infra / CI

- 3-stage Dockerfile with Vite build, optimised layer caching, healthcheck
- GitHub Actions CI — lint (ruff), security audit (pip-audit), unit tests
  with coverage, E2E tests, Docker build
- Production Docker Compose with Nginx reverse proxy and Prometheus monitoring
- Backup, restore, and rollback scripts
- Locust load tests and pytest benchmark suite

[1.1.0]: https://github.com/your-org/storyforge/releases/tag/v1.1.0
[1.0.0]: https://github.com/your-org/storyforge/releases/tag/v1.0.0
