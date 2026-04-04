# Changelog

All notable changes to **StoryForge** are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

---

## [Unreleased]

### Removed
- Layer 3 video storyboarding pipeline
- TTS/voice narration (edge-tts)
- Audio player component
- Video composer and exporter

### Added
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

[1.0.0]: https://github.com/your-org/storyforge/releases/tag/v1.0.0
