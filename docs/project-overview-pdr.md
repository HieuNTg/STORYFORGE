# Novel Auto Pipeline — Product Development Requirements (PDR)

## Project Overview

**Novel Auto** (StoryForge) is an automated three-layer pipeline for generating dramatic multimedia content (novels, enhanced narratives, video storyboards, audio, images) from story concepts using AI-powered language models.

**Vision**: Democratize drama-driven storytelling by automating character consistency, plot depth, visual adaptation, and audio narration across formats.

## Product Definition

### What Is Novel Auto?

A modular AI pipeline that transforms a genre + story idea into:
1. **Layer 1**: Complete novel draft (10-50 chapters) with rolling character state tracking
2. **Layer 2**: Drama-enhanced narrative via multi-agent feedback loops
3. **Layer 3**: Video storyboards with shot-level metadata + audio + images

### Core Features

**Story Generation (Layer 1)**
- Character generation: personality, motivation, relationships
- World-building: settings, rules, locations
- Chapter-by-chapter outline + full chapter writing
- **Character State Tracking**: mood, arc, knowledge per chapter
- **Plot Event Extraction**: major events + character involvement
- **Rolling Context Window**: last N chapters + capped plot events (50 max)

**Drama Enhancement (Layer 2)**
- Multi-agent simulation (6+ agents)
- Character consistency verification, plot hole detection, dialogue scoring
- Drama intensity feedback loops
- **Context-aware escalation**: agents escalate priority when thresholds breached

**Video Storyboarding (Layer 3)**
- Scene-level breakdown (shots per chapter)
- Camera direction generation

**TTS Audio Generation (NEW)**
- `edge-tts` integration for Vietnamese voice synthesis
- Multiple Vietnamese voices: `vi-VN-HoaiMyNeural`, `vi-VN-NamMinhNeural`
- Per-chapter MP3/WAV output
- Wired to all pipeline entry points via feedback loop

**Image Generation (NEW)**
- Pluggable provider: DALL-E, Stable Diffusion API, or disabled (`none`)
- One image per storyboard panel from exported image prompts
- Batch generation (ThreadPoolExecutor, max 3 workers)

**Credit / Monetization System (NEW)**
- Per-user credit accounts with bcrypt-hashed passwords
- Deduction on LLM call completion; configurable rates for TTS/image
- Top-up API; audit log per user
- `InsufficientCreditsError` surfaces top-up prompt in UI

**Security (NEW)**
- bcrypt password hashing for all user accounts
- API keys stored in env vars (never in code or logs)

**Story Continuation & Editing (Phase 6)**
- `continue_story()`, `rebuild_context()`, `remove_chapters()`
- Character edits reflected in subsequent generation
- Checkpoint-based workflow preserves coherence

**Multi-Language Support (Phase 5)**
- `services/i18n.py`: thread-safe singleton, JSON locale lookup
- `locales/vi.json` + `locales/en.json`: 200+ strings each
- 167+ `_t()` call sites in app.py
- `localize_prompt()` wrapper in prompts.py
- Automatic prompt localization in `llm_client.generate()`

**Quality Scoring**
- LLM-as-judge: coherence, character_consistency, drama, writing_quality (1-5)
- Layer 1 + Layer 2 scoring + improvement delta
- Parallel scoring (max 3 workers), cheap model tier, temp=0.2

**Export Formats**
- TXT, Markdown, JSON, HTML (self-contained reader), ZIP bundle
- SRT subtitles, voiceover script, image prompts, CapCut JSON, CSV timeline
- Per-chapter audio (MP3), per-panel images

**UI Modularization**
- `app.py` delegates to `ui/tabs/` modules
- 4 consolidated output tabs (Truyen | Mo Phong | Video | Danh Gia)
- Progress bar, status badges, mobile-responsive CSS, XSS-safe rendering
- Collapsed detail log accordion

**CI/CD Pipeline (NEW)**
- GitHub Actions: lint (flake8), typecheck (mypy), test (pytest --cov), build validation
- Triggers on push/PR to main

### User Personas

| Persona | Use Case | Needs |
|---------|----------|-------|
| **Author** | Generate novel drafts | Character consistency, plot coherence |
| **Screenwriter** | Adapt to video | Scene breakdown, visual metadata, SRT |
| **Publisher** | Quality at scale | Consistency checks, drama control |
| **Creator** | Multi-format content | Audio, images, CapCut export |
| **Platform Owner** | Monetization | Credit system, bcrypt accounts |

## Technology Stack

| Component | Technology | Notes |
|-----------|-----------|-------|
| Language | Python 3.10+ | LLM ecosystem |
| Web UI | Gradio | Modular tabs via ui/tabs/ |
| Data Model | Pydantic v2 | Type-safe validation |
| LLM API | OpenAI SDK | OpenAI-compatible or DeepSeek web |
| Cache | SQLite | No external DB |
| Async | ThreadPoolExecutor | Parallel extraction + scoring |
| TTS | edge-tts | Vietnamese voice synthesis |
| Password | bcrypt | Account security |
| CI/CD | GitHub Actions | lint + typecheck + test |
| i18n | JSON locales | vi + en, 200+ strings |
| Browser auth | Playwright + Chrome CDP | DeepSeek free web API |
| Image gen | DALL-E / SD API | Pluggable, disabled by default |

## Functional Requirements

### Layer 1: Story Generation

- **Req-1.1**: Generate characters from genre + idea
- **Req-1.2**: Generate world/setting
- **Req-1.3**: Generate chapter outlines (full story structure)
- **Req-1.4**: Write full novel chapter-by-chapter
- **Req-1.5**: Extract character state per chapter (mood, arc, knowledge, relationships, last_action)
- **Req-1.6**: Extract plot events per chapter
- **Req-1.7**: Maintain rolling context window (bounded: summaries×N + states + 50 events)
- **Req-1.8**: Generate end-to-end story draft < 30 min for 10 chapters

### Layer 2: Drama Enhancement

- **Req-2.1**: Multi-agent feedback simulation (6+ agents)
- **Req-2.2**: Character consistency validation
- **Req-2.3**: Drama intensity scoring + escalation patterns

### Layer 3: Video

- **Req-3.1**: Scene breakdown (shots_per_chapter)
- **Req-3.2**: Shot-level metadata (camera, angle, dialogue)
- **Req-3.3–3.10**: Video export: SRT, voiceover, image prompts, CapCut, CSV, ZIP (max 200 panels)

### TTS / Audio (NEW)

- **Req-TTS.1**: edge-tts synthesis per chapter → MP3/WAV
- **Req-TTS.2**: Multiple Vietnamese voices; configurable speed/pitch
- **Req-TTS.3**: Wired to pipeline feedback loop at all entry points

### Image Generation (NEW)

- **Req-IMG.1**: Pluggable provider (none | dalle | sd) via `STORYFORGE_IMAGE_PROVIDER`
- **Req-IMG.2**: One image per storyboard panel from image prompt list
- **Req-IMG.3**: Graceful disable when provider=none (skip, log)

### Credit System (NEW)

- **Req-CRD.1**: bcrypt account creation + authentication
- **Req-CRD.2**: Credit deduction on LLM call; `InsufficientCreditsError` stops pipeline
- **Req-CRD.3**: Top-up API; audit log per user
- **Req-CRD.4**: Separate rates for LLM, TTS, image calls

### CI/CD (NEW)

- **Req-CI.1**: GitHub Actions on push/PR to main
- **Req-CI.2**: Lint (flake8), typecheck (mypy), test (pytest), smoke import
- **Req-CI.3**: Coverage report as artifact

## Non-Functional Requirements

### Performance
- 10 chapters: < 30 min (parallel extraction)
- Each chapter: < 3 min (write + extraction)
- Image batch: < 60 sec for 10 panels (parallel)
- TTS per chapter: < 30 sec

### Reliability
- LLM: retry 3× with exponential backoff
- Cache results 7 days (TTL)
- TTS/image failures non-blocking (pipeline continues)
- Credit errors blocking (stop pipeline, surface to UI)

### Security
- bcrypt for all passwords (never plain text)
- API keys in env vars only
- Logs scrubbed of secrets

### Scalability
- max_parallel_workers=3 for extraction, scoring, image batch
- Credit system thread-safe

## Acceptance Criteria (Current Release)

### Phase 7 (NEW — COMPLETE)
- [x] `services/tts_audio_generator.py` with edge-tts, Vietnamese voices
- [x] `services/image_generator.py` with dalle/sd/none providers
- [x] `services/credit_manager.py` with bcrypt + balance/deduct/top-up/audit
- [x] `STORYFORGE_IMAGE_PROVIDER`, `IMAGE_API_KEY`, `IMAGE_API_URL` env vars
- [x] `.github/workflows/ci.yml` with lint + typecheck + test + build-validate
- [x] `ui/tabs/` modularization (pipeline, web_auth, output, quality, export, continuation)
- [x] Feedback loop wired to all pipeline entry points (TTS + image + scoring)

### Phase 6 (COMPLETE)
- [x] `continue_story()`, `rebuild_context()`, `remove_chapters()` in generator
- [x] Orchestrator continuation orchestration methods
- [x] Continuation UI tab (chapter slider, character editor, delete/re-enhance)

### Phase 5 (COMPLETE — i18n)
- [x] `services/i18n.py`, `locales/vi.json`, `locales/en.json`
- [x] 167+ `_t()` call sites, language selector
- [x] `localize_prompt()` + automatic prompt localization in llm_client

### Phase 4 (COMPLETE — HTML Export)
- [x] `services/html_exporter.py` self-contained HTML reader
- [x] Dark/light mode, chapter nav, character cards
- [x] HTML format in export_output() + ZIP bundling

### Phase 3 (COMPLETE — Video Export)
- [x] VideoExporter (SRT, voiceover, image prompts, CapCut JSON, CSV, ZIP)
- [x] MAX_PANELS=200, orchestrator.export_video_assets(), UI button

### Phase 2 (COMPLETE — UI Polish)
- [x] Progress bar (3-segment), status badges (4 states)
- [x] Layer detection (Vietnamese diacritics), 4-tab consolidation
- [x] Mobile CSS, XSS-safe rendering, resume streaming

### Phase 1 (COMPLETE — Character Tracking + Quality Scoring)
- [x] CharacterState, PlotEvent, StoryContext, rolling context
- [x] QualityScorer (4 dimensions, parallel, cheap tier)
- [x] 77 test cases passed

## Roadmap

| Phase | Status | Date |
|-------|--------|------|
| Phase 1 — Character Tracking | COMPLETE | 2026-03-23 |
| Phase 2 — UI Polish | COMPLETE | 2026-03-23 |
| Phase 3 — Video Export | COMPLETE | 2026-03-23 |
| Phase 4 — HTML Export | COMPLETE | 2026-03-23 |
| Phase 5 — i18n | COMPLETE | 2026-03-23 |
| Phase 6 — Story Continuation | COMPLETE | 2026-03-23 |
| Phase 7 — TTS, Images, Credits, CI/CD | COMPLETE | 2026-03-24 |
| Phase 8 — PDF/EPUB export, multi-tenancy | PLANNED | TBD |

## Known Limitations

1. Chrome dependency for web auth (not headless-server friendly)
2. `data/auth_profiles.json` stores credentials in plain JSON (encrypt for production)
3. No multi-tenancy — all stories global scope (Phase 8)
4. Manual review required — generated content needs human editing
5. Image generation rate-limited by provider API quotas

---

**Document Version**: 1.4 (Phase 7: TTS, Images, Credits, CI/CD, UI Modularization)
**Last Updated**: 2026-03-24
**Status**: Phases 1-7 Complete. Phase 8 planned.
