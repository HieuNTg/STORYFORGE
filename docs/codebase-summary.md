# Novel Auto Pipeline - Codebase Summary

## Overview

**Novel Auto** (StoryForge) is a three-layer automated pipeline for creating dramatic, multimedia content from story ideas.

| Layer | Purpose | Input | Output |
|-------|---------|-------|--------|
| **Layer 1** | Story generation | Genre, idea, character specs | Full novel draft with rolling character/plot context |
| **Layer 2** | Drama enhancement | Story draft | Intensified narrative with agent feedback loops |
| **Layer 3** | Video production | Enhanced story | Storyboards, shots, video metadata |

## Project Structure

```
novel-auto/
├── app.py                          # FastAPI thin entry point (79 lines): launches web UI, API routes, Gradio fallback
├── ui/gradio_app.py                # Gradio UI (1160 lines): all tab logic extracted from app.py
├── config.py                       # ConfigManager (singleton), LLMConfig, PipelineConfig
├── models/
│   └── schemas.py                  # Pydantic models for all layers + quality scoring
├── services/
│   ├── llm_client.py               # LLM wrapper: provider-aware retry with Retry-After header parsing
│   ├── llm_cache.py                # SQLite-based prompt result caching
│   ├── secret_manager.py           # Fernet encryption for secrets at rest (NEW - Sprint 1)
│   ├── input_sanitizer.py          # Prompt injection detection: 8 regex patterns (NEW - Sprint 1)
│   ├── emotion_classifier.py       # Bilingual (vi+en) emotion classification with auto-detect (MODIFIED - Sprint 1)
│   ├── prompts.py                  # Centralized prompt templates (localize_prompt wrapper)
│   ├── browser_auth.py             # Chrome CDP + Playwright credential capture
│   ├── deepseek_web_client.py      # DeepSeek web API client with PoW challenge solver
│   ├── quality_scorer.py           # LLM-as-judge quality metrics (4 dimensions, 1-5 scale)
│   ├── structured_logger.py        # JSON logging when LOG_FORMAT=json (NEW Sprint 2)
│   ├── video_exporter.py           # SRT, voiceover, image prompts, CapCut JSON, CSV, ZIP
│   ├── html_exporter.py            # Self-contained HTML reader (dark/light mode, chapter nav)
│   ├── tts_audio_generator.py      # Multi-provider TTS (edge-tts, kling, xtts), Vietnamese voices
│   ├── image_generator.py          # DALL-E / SD API image generation; now with character consistency
│   ├── image_prompt_generator.py   # Scene/panel image prompts; frozen visual descriptions (Phase 14)
│   ├── replicate_ip_adapter.py     # IP-Adapter client for Replicate API (Phase 14)
│   ├── character_visual_profile.py # Persistent character visual profiles (Phase 14)
│   ├── credit_manager.py           # Credit/monetization system with bcrypt-hashed accounts
│   ├── self_review.py              # CoT+CAI self-review for chapter quality assessment
│   ├── story_brancher.py           # Interactive story branching with DAG management
│   ├── wattpad_exporter.py         # Wattpad/NovelHD export service
│   ├── rag_knowledge_base.py       # RAG with ChromaDB + sentence-transformers (500-char chunks)
│   ├── i18n.py                     # Thread-safe i18n singleton (vi/en JSON locales)
│   ├── adaptive_prompts.py         # 12 genre + 4 score-booster adaptive prompt templates (Phase 18)
│   ├── quality_gate.py             # Inline quality gate between pipeline layers (Phase 18)
│   ├── onboarding.py               # 4-step onboarding wizard state machine (Phase 19)
│   ├── knowledge_graph.py          # Story entity knowledge graph; NetworkX + pure Python fallback (Phase 19)
│   └── progress_tracker.py         # Structured event tracker for pipeline milestones (Phase 20)
├── pipeline/
│   ├── orchestrator.py             # Main workflow coordinator
│   ├── layer1_story/
│   │   ├── generator.py            # OrchestrationShell (refactored ~495 lines): routes to submodules
│   │   ├── character_generator.py   # Character generation + state extraction (65 lines, NEW Sprint 2)
│   │   ├── chapter_writer.py        # Chapter writing + prompt building + context (246 lines, NEW Sprint 2)
│   │   ├── outline_builder.py       # Title suggestion + world + outline generation (87 lines, NEW Sprint 2)
│   │   └── story_bible_manager.py   # Story context + state tracking
│   ├── layer2_enhance/
│   │   ├── simulator.py            # Drama simulation with agent loops
│   │   ├── analyzer.py             # Post-simulation analysis
│   │   ├── enhancer.py             # Narrative enhancement
│   │   └── _agent.py               # Agent registry & base class
│   ├── layer3_video/
│   │   └── storyboard.py           # Shot & scene generation
│   ├── agents/
│   │   ├── base_agent.py           # BaseAgent interface with depends_on & prior_reviews
│   │   ├── agent_graph.py          # AgentDAG — topological sort + 4-tier execution (Phase 13)
│   │   ├── character_specialist.py
│   │   ├── continuity_checker.py
│   │   ├── dialogue_expert.py
│   │   ├── drama_critic.py
│   │   ├── editor_in_chief.py
│   │   └── agent_registry.py
│   └── __init__.py
├── ui/
│   └── tabs/                       # Modular Gradio tab components
│       ├── pipeline_tab.py         # Main generation form
│       ├── web_auth_tab.py         # Browser auth UI
│       ├── output_tab.py           # Story/simulation/video output
│       ├── quality_tab.py          # Quality metrics display
│       ├── export_tab.py           # Export format selection + download
│       ├── continuation_tab.py     # Chapter continuation & character editing
│       └── branching_tab.py        # Story branching UI with fork/merge controls
├── errors/                         # Error handling layer (NEW Sprint 2)
│   ├── exceptions.py               # Typed exception hierarchy: StoryForgeError base
│   ├── handlers.py                 # FastAPI exception handler middleware
│   └── __init__.py                 # Re-exports
├── locales/
│   ├── vi.json                     # Vietnamese locale strings (200+)
│   └── en.json                     # English locale strings (200+)
├── .env.example                    # Environment variable template (NEW - Sprint 1)
├── .github/
│   └── workflows/
│       └── ci.yml                  # GitHub Actions CI/CD (parallel lint/typecheck/test + staging-deploy, Phase 20)
├── docker-compose.staging.yml      # Staging environment stack (Phase 20)
├── data/
│   ├── config.json                 # LLM & pipeline configuration
│   ├── templates/
│   │   └── story_templates.json    # 13 story templates (zero-config onboarding)
│   ├── auth_profiles.json          # Cached browser auth credentials
│   └── cache.db                    # SQLite cache for LLM results
├── web/
│   ├── index.html                  # Single-page app (professional UI - Sprint 1)
│   ├── js/api-client.js            # API client with streamBuffered() SSE batch method (MODIFIED - Sprint 1)
│   └── (CSS, static assets)
└── output/                         # Generated stories (TXT, MD, JSON, HTML, ZIP)
```

## Core Models (schemas.py)

### Layer 1 — Story Generation

- **Character**: Protagonist/antagonist/support with personality, background, motivation, relationships
- **WorldSetting**: Fictional universe context (era, locations, rules)
- **ChapterOutline**: Chapter structure with summary, events, character involvement, emotional arc
- **Chapter**: Full written chapter (content, word count, summary)
- **CharacterState**: Rolling snapshot per chapter — mood, arc_position, knowledge, relationship_changes, last_action
- **PlotEvent**: Major story event with chapter reference and character involvement list
- **StoryContext**: Rolling context window — recent summaries (limited to `context_window_chapters`), character states, plot events (cap 50)
- **StoryDraft**: Complete story artifact; includes `character_states`/`plot_events` for Layer 2 handoff

### Layer 2 — Drama Enhancement

- **DramaSimulation, AgentFeedback, SimulationResult**: Multi-agent feedback loops

### Layer 3 — Video Production

- **Shot, Scene, Storyboard**: Scene-level video metadata

### Quality Scoring

- **ChapterScore**: 4 dimensions (coherence, character_consistency, drama, writing_quality) + overall mean
- **StoryScore**: Aggregate story scores (avg per dimension, weakest chapter, layer marker)

## Services Overview

### llm_client.py
- Singleton with dual-backend routing (`api` → OpenAI-compatible, `web` → DeepSeek browser auth)
- Retry logic: MAX_RETRIES=3 with exponential backoff
- Cache: SQLite with configurable TTL
- Auto prompt localization via `localize_prompt()` in `generate()` / `generate_stream()`
- `generate_json(max_tokens)` — compact extraction with token control

### tts_audio_generator.py
- Multi-provider TTS: edge-tts (default), kling, xtts (Phase 13), or none
- **Phase 13 XTTS**: Per-character voice cloning via reference audio clips; fallback to edge-tts on failure
- Vietnamese voice support (multiple voices, speed/pitch control)
- Per-chapter audio generation; outputs MP3/WAV
- Character voice mapping via `character_voice_map` config (Phase 13)
- Wired to pipeline feedback loop at all Layer 1/2/3 entry points
- **Phase 15**: Emotion-aware rate/pitch adjustment via EmotionClassifier; `_resolve_xtts_reference()` fallback support

### image_generator.py
- Pluggable provider interface: DALLE, SD-API, Seedream, Replicate, or none
- Generates images per storyboard panel from `export_image_prompts()`
- **Phase 14**: `generate_with_reference()` routes to seedream/replicate for character consistency
- Provider selection via `STORYFORGE_IMAGE_PROVIDER` env var
- API key/URL injected from environment (`IMAGE_API_KEY`, `IMAGE_API_URL`, `SEEDREAM_API_KEY`, `REPLICATE_API_KEY`)

### credit_manager.py
- Credit/monetization system for metered usage
- bcrypt password hashing for account security
- Per-user credit balance; deducts on LLM call completion
- Top-up and balance query APIs

### quality_scorer.py
- `score_chapter(chapter, context)` → ChapterScore — excerpt strategy: head 2600 + tail 1400 chars
- `score_story(chapters, layer)` → StoryScore — parallel (max 3 workers), sequential context
- Uses cheap model tier, temp=0.2, max 500 tokens

### agent_graph.py (Phase 13)
- AgentDAG: Directed Acyclic Graph with topological sort (Kahn's algorithm)
- 4-tier execution: CharacterSpecialist → [Continuity, Dialogue, Style, Pacing] → [DramaCritic, DialogueBalance] → EditorInChief
- BaseAgent.depends_on class attribute + prior_reviews param on review()
- Validates cycles, resolves dependencies, handles missing agents gracefully
- agent_registry.py run_review_cycle() uses tiered execution; flat-parallel fallback if DAG disabled
- Pure Python, no external dependencies

### debate_orchestrator.py (Phase 16, Phase 16.5 LLM upgrade)
- `DebateOrchestrator` — 3-round multi-agent debate protocol for story decisions
- **Phase 16.5**: Agents now use LLM-powered debate_response() (with rule-based fallback) instead of static keyword matching
- Agents challenge/support peers using LLM analysis; produces `revised_score` (0.0-1.0) per DebateEntry
- Integration: agent_registry.py `run_review_cycle()` wires debate into feedback loop
- Schemas: DebateStance (position, reasoning, evidence), DebateEntry (agent, stance, rebuttal, revised_score), DebateResult (consensus, votes)
- Config: `enable_agent_debate` (bool), `max_debate_rounds` (int)
- **Phase 16.5**: A/B test threshold changed from 1.5 → 0.10 (validates +0.10 drama delta)

### i18n.py
- Thread-safe singleton; JSON locale lookup with fallback chain: requested → `vi` → raw key
- 200+ strings per locale
- `_t(key)` shorthand used throughout app.py (167+ call sites)

### token_counter.py (Phase 15)
- `estimate_tokens(text, model)` — approximate token count via word count heuristic
- `fits_in_context(text, model, context_limit)` — check if text fits within context window
- Supports model context windows: GPT-4/4o (128k), 3.5-turbo (4k), deepseek (4k)

### long_context_client.py (Phase 15)
- `LongContextClient` — OpenAI-compatible long-context LLM client for full chapter handling
- Methods: `generate(prompt, max_tokens)`, `generate_stream(prompt)` with streaming
- Retry logic: 3 attempts with exponential backoff; JSON mode support
- Context window aware: splits chapters if exceeding limit via token_counter
- Config: `use_long_context`, `long_context_model`, `long_context_base_url`, `long_context_timeout_seconds`

### emotion_classifier.py (Phase 15, MODIFIED Sprint 1)
- `classify_emotion(text)` — Rule-based bilingual (Vietnamese + English) emotion detection
- Auto-detects language by checking Vietnamese diacritical mark frequency
- Emotions: sad, happy, angry, tense, neutral (with fallback between languages)
- Voice modulation params: rate/pitch adjustments per emotion
- No LLM calls; keyword-based with `_detect_language()` fallback support
- Input: any text; output: emotion label with confidence (0.0-1.0)

### secret_manager.py (NEW - Sprint 1)
- Fernet symmetric encryption for secrets at rest
- `_get_fernet()` — derives Fernet key from `STORYFORGE_SECRET_KEY` env var via SHA256 hash
- `encrypt_json(data)` — encrypts dict as JSON bytes (graceful fallback to plaintext if no key)
- `decrypt_json(data)` — decrypts bytes to dict with plaintext JSON fallback for backward compatibility
- `save_encrypted(filepath, data)` — persist encrypted data
- `load_encrypted(filepath)` — load + decrypt with error handling (returns {} on failure)
- Purpose: Secure storage of API keys, auth tokens, credentials at rest

### input_sanitizer.py (NEW - Sprint 1)
- Prompt injection detection via 8 regex patterns
- Patterns detect: system prompt overrides, role switches, tag/token injection, safety bypasses
- `SanitizationResult` — immutable result class: is_safe (bool), cleaned_text (str), threats_found (list)
- `sanitize_input(text)` — checks text against all patterns; does NOT modify (caller decides action)
- `sanitize_story_input(title, idea, genre)` — combines all inputs before sanitization
- Returns early if text empty; logs each threat at WARNING level
- Integration: Call before storing user-provided inputs in pipeline config

### prompts.py (MODIFIED Sprint 2)
- `localize_prompt(template, lang)` wrapper for all generation prompts
- Key prompts: WRITE_CHAPTER, EXTRACT_CHARACTER_STATE, EXTRACT_PLOT_EVENTS, SUMMARIZE_CHAPTER,
  SCORE_CHAPTER, SUGGEST_TITLE, GENERATE_CHARACTERS, GENERATE_WORLD, GENERATE_OUTLINE,
  CONTINUE_OUTLINE
- **Phase 13**: RAG_CONTEXT_SECTION — injected into world-building & chapter prompts when RAG enabled
- **Phase 16.5**: DRAMA_DEBATE, CHARACTER_DEBATE — LLM debate templates for agent analysis (DramaCriticAgent, CharacterSpecialistAgent)
- **Phase 17**: SMART_REVISE_CHAPTER — targeted revision prompt with aggregated agent issues/suggestions
- **Sprint 2**: Language policy docs + vi-only markers in prompts

### smart_revision.py (Phase 17)
- `SmartRevisionService` — auto-detect and revise weak chapters
- `revise_weak_chapters(enhanced_story, quality_scores, reviews, genre)` → dict with revision stats
  - Identifies chapters with `overall < smart_revision_threshold` (1.0-5.0 scale)
  - Aggregates agent review issues/suggestions per chapter via regex word-boundary matching
  - Revises with targeted guidance; re-scores to validate; accepts if delta >= +0.3
  - Max 2 passes per chapter (configurable)
- Feature gated by `enable_smart_revision` config (default False)

### adaptive_prompts.py (Phase 18)
- `AdaptivePrompts` — 12 genre-specific emphasis prompts + 4 score-booster templates
- `get_genre_prompt(genre)` → genre-tuned emphasis string (romance, mystery, fantasy, sci-fi, thriller, drama, comedy, horror, historical, action, slice-of-life, literary)
- `get_score_booster(dimension)` → booster for weakest quality dimension (coherence/character/drama/writing)
- `build_adaptive_prompt(genre, quality_scores)` → combined prompt injected into chapter generation
- Integration: `generator.py` `_build_chapter_prompt()` appends adaptive section

### quality_gate.py (Phase 18)
- `QualityGate` — inline scoring gate between pipeline layers
- `check(story_score, layer)` → `GateResult(passed, score, threshold, layer)`
- Raises `QualityGateError` if `score < quality_gate_threshold` and gate enabled
- Emits structured event via ProgressTracker on each check
- Config: `enable_quality_gate` (bool, default False), `quality_gate_threshold` (float 1.0-5.0)
- Integration: orchestrator calls gate between L1→L2 and L2→L3

### onboarding.py (Phase 19)
- `OnboardingManager` — 4-step wizard state machine: genre → characters → style → confirm
- `step_genre()`, `step_characters()`, `step_style()`, `step_confirm()` → sequential state transitions
- `step_confirm()` returns populated `PipelineConfig`; `reset()` clears state
- Reduces first-run misconfiguration; UI wizard tab calls steps sequentially

### knowledge_graph.py (Phase 19, MODIFIED Sprint 2)
- `StoryKnowledgeGraph` — entity relationship graph for story artifacts
- `index_story(story_draft)` — extracts character/location/event nodes + edges from L1 output
- `get_character_relationships(name)` → list of edges for entity
- `get_entity_context(name)` → formatted context string (for future prompt injection, added Sprint 2)
- `export_graph()` → serializable `{nodes, edges}` dict
- NetworkX DiGraph if installed; pure Python adjacency dict fallback (zero hard deps)

### progress_tracker.py (Phase 20)
- `ProgressTracker` — structured event emission throughout pipeline
- `emit(event, data)` — logs structured event + calls registered Gradio callback
- Standard events: `gate_checked`, `revision_done`, `scoring_complete`, `layer_start`, `layer_complete`
- Injected by orchestrator; services call `tracker.emit()` at milestones

### Error Handling Layer (NEW Sprint 2)

#### exceptions.py — Typed Exception Hierarchy
- `StoryForgeError` — base exception class (all project errors inherit)
  - `ConfigError` — configuration validation failures
  - `LLMError` — LLM provider/API errors
  - `PipelineError` — pipeline execution errors
  - `ValidationError` — input/output validation failures
  - Additional domain-specific exceptions as needed

#### handlers.py — FastAPI Exception Middleware
- `StoryForgeExceptionHandler` — maps domain exceptions → HTTP responses
- Logs all exceptions at appropriate levels (ERROR/WARNING)
- Returns structured JSON error responses to client
- Integration: wired in `app.py` via exception handlers

### structured_logger.py (NEW Sprint 2)
- JSON logging when `LOG_FORMAT=json` env var is set
- Structured event emission: timestamp, level, message, context (dict)
- Backward compatible: defaults to standard logging format
- Integration: services can emit structured events for monitoring

### Frontend Resilience & Persistence (save-logic-render-audit)

#### sessionStorage Persistence (web/js/app.js)
- `savePipelineResult(data)` — saves pipeline output to sessionStorage with error handling
- Strips transient fields (e.g., livePreview) before storing
- Size checks: warns if >4MB (typical 5MB limit)
- `init()` — restores pipeline result on page load; graceful fallback if JSON invalid
- Graceful degradation: if storage fails, warning shown ("Result too large to cache")

#### SSE Interruption Detection (web/js/api-client.js)
- `fetchSSE(path)` — robust SSE stream consumption
- Yields `{ type: 'interrupted', data: '...' }` if:
  - Stream connection lost (network error)
  - Stream ends without 'done' event (unexpected termination)
- Timeout safeguard: aborts after 30 seconds without data
- On interrupt, UI status set to 'interrupted' (allows manual resume)

#### Checkpoint Resume API (api/pipeline_routes.py)
- `POST /api/pipeline/resume` — resume from saved checkpoint
- Path traversal fix: uses `pathlib.Path(body.checkpoint).name` to prevent directory traversal
- Validates checkpoint exists before resuming
- Returns SSE stream with same event types as `/api/pipeline/run`
- Logs streamed with same progress_callback pattern

#### Interrupted UI Status (web/index.html)
- Pipeline status: 'idle' | 'running' | 'done' | 'error' | **'interrupted'** (new)
- On interrupt, resume button shows in UI; users can click to continue from checkpoint
- Storage warning banner: informs users if sessionStorage save failed

### rag_knowledge_base.py (Phase 13)
- RAGKnowledgeBase service using ChromaDB + sentence-transformers
- Methods: `add_file()`, `add_documents()`, `query()`, `clear()`, `count()`
- Chunking: 500-char chunks with 50-char overlap; sentence-boundary aware
- File support: .txt, .md, .pdf (10 MB max, graceful degradation if libs not installed)
- Integration: `generator.py` `generate_world()` & `_build_chapter_prompt()` inject RAG context when enabled
- Dependencies: chromadb>=0.4.0, sentence-transformers>=2.2.0
- **Sprint 0 Fix**: SHA256 document IDs for deterministic hashing; error-level logging on init failure

### video_exporter.py
- Input: `VideoScript` (panels, voice_lines, character descriptions)
- Exports: SRT, voiceover script, image prompts, CapCut JSON, CSV, ZIP bundle
- Max 200 panels; ZIP returned via `export_all(output_dir)`

### html_exporter.py
- Self-contained HTML story reader
- Dark/light mode toggle, chapter navigation, character info cards
- Responsive for mobile & desktop

## UI Modularization (ui/tabs/)

`app.py` delegates tab creation to discrete modules:

| Module | Responsibility |
|--------|----------------|
| `pipeline_tab.py` | Genre dropdown, template selector, generation form |
| `web_auth_tab.py` | Chrome CDP launcher, credential capture/clear |
| `output_tab.py` | Story/simulation/video storyboard display |
| `quality_tab.py` | Quality metrics, ChapterScore/StoryScore display |
| `export_tab.py` | TXT/MD/JSON/HTML format checkboxes, ZIP download |
| `continuation_tab.py` | Chapter slider, character editor, re-enhance |

**Output tabs**: Truyen | Mo Phong | Video | Danh Gia (consolidated from 6 → 4)

## Configuration (config.py)

### LLMConfig
- `api_key`, `base_url`, `model` (default: gpt-4o-mini)
- `temperature` (0.8 generation / 0.3 extraction)
- `max_tokens` (4096 default)
- `backend_type` ("api" or "web"), `web_auth_provider` ("deepseek-web")
- `cache_enabled`, `cache_ttl_days`, `max_parallel_workers`
- `cheap_model`, `cheap_base_url` (for cost control on scoring)

### PipelineConfig
- `num_chapters`, `words_per_chapter`
- `genre`, `sub_genres`, `writing_style`
- `context_window_chapters` (default: 2)
- Layer 2: `num_simulation_rounds`, `num_agents`, `drama_intensity`
- Layer 3: `shots_per_chapter`, `video_style`
- `language` ("vi" / "en")
- `enable_self_review` (bool, default: False) — opt-in CoT self-review
- `self_review_threshold` (float 1.0-5.0, default: 3.0) — quality threshold for auto-revision
- **Phase 13**: `rag_enabled` (bool, default: False), `rag_persist_dir` — RAG knowledge base config
- **Phase 13**: `xtts_api_url`, `xtts_reference_audio`, `character_voice_map` — XTTS voice cloning
- **Phase 14**: `enable_character_consistency` (bool, default: False) — character visual consistency
- **Phase 14**: `replicate_api_key` (str) — Replicate API key for IP-Adapter
- **Phase 14**: `character_consistency_provider` (str, "seedream" | "replicate") — provider selection
- **Phase 15**: `use_long_context` (bool, default: False) — enable long-context LLM for full chapters
- **Phase 15**: `long_context_model`, `long_context_base_url` — long-context LLM endpoints
- **Phase 15**: `long_context_timeout_seconds` (int, default: 120) — context window operation timeout
- **Phase 15**: `enable_voice_emotion` (bool, default: False) — emotion-aware TTS rate/pitch
- **Phase 16**: `enable_agent_debate` (bool, default: False) — multi-agent debate protocol
- **Phase 16**: `max_debate_rounds` (int, default: 3) — max debate rounds per decision
- **Phase 17**: `enable_smart_revision` (bool, default: False) — auto-revise weak chapters after Layer 2
- **Phase 17**: `smart_revision_threshold` (float 1.0-5.0, default: 3.5) — score threshold for weak chapter detection
- **Phase 18**: `enable_quality_gate` (bool, default: False) — inline quality gate between layers
- **Phase 18**: `quality_gate_threshold` (float 1.0-5.0) — minimum score to pass gate
- **Phase 18**: `preset_profile` (str, "beginner" | "advanced" | "pro") — preset config bundle

## Character State Tracking (Phase 1)

Rolling context per chapter:
```
Chapter → [parallel] summarize + extract_character_states + extract_plot_events
                         ↓
            StoryContext (rolling: summaries, states, plot_events capped at 50)
                         ↓
            write_chapter(context=story_context) for next chapter
```

## Story Continuation (Phase 6)

- `generator.py`: `continue_story()`, `rebuild_context()`, `remove_chapters()`
- `orchestrator.py`: `load_from_checkpoint()`, `continue_story()`, `update_character()`, `enhance_chapters()`
- UI: chapter slider, character editor, delete/re-enhance buttons
- Checkpoint-based — context rebuilt from existing chapters

## CoT Self-Review (Phase 9, F1 → Phase 10)

- `services/self_review.py`: `SelfReviewService` with CoT+CAI prompt injection
- Identifies weak chapters below configurable quality threshold (~20-30% revision rate)
- Integrated into Layer 1 generator for auto-revision
- Uses cheaper model tier with temp=0.2 for consistency
- **Phase 10**: `enable_self_review` (bool, opt-in) + `self_review_threshold` (1.0-5.0) in config; applied to both `generate_full_story()` and `continue_story()`
- UI controls in settings_tab.py

## Story Branching (Phase 9, F2 → Phase 10)

- `services/story_brancher.py`: DAG-based branch management
- `ui/tabs/branching_tab.py`: Fork/merge UI visualization
- Multi-path story exploration; user-driven convergence (no auto-merge)
- **Phase 10**: `save_tree()`, `load_tree()`, `list_saved_trees()` static methods; JSON persistence to `data/branches/`
- Save/load buttons in branching_tab.py UI

## Wattpad/NovelHD Export (Phase 9, F3 → Phase 10)

- `services/wattpad_exporter.py`: Direct export to Wattpad chapter structure
- NovelHD metadata format with character/world transcription
- Integrated into export_tab.py with format selection checkbox
- **Phase 10**: ZIP bundle support, `character_appendix` in metadata, `reading_time_min` per chapter (words/200 minimum 1)
- Local export only (Wattpad API deprecated 2023)

## CI/CD Pipeline (GitHub Actions)

`.github/workflows/ci.yml`:
- Triggers: push / PR to main
- **Phase 20**: lint (flake8) + typecheck (mypy) + test (pytest, 1327 tests incl. 22 E2E) run **in parallel**
- `build-validate` job after test: `python -c "import app"` smoke check
- `staging-deploy` job: deploy to staging via `docker-compose.staging.yml` after build passes
- Context-aware escalation: failures escalate via agent feedback loop patterns

### config.py (MODIFIED Sprint 2)
- `save()` method: removed secrets from direct persistence (use SecretManager instead)
- `block_on_injection` field: feature flag for prompt injection blocking

## Development Status

| Phase | Status | Summary |
|-------|--------|---------|
| Phase 1 | COMPLETE | Character state tracking, rolling context |
| Phase 2 | COMPLETE | UI polish, progress bar, status badges, tab consolidation |
| Phase 3 | COMPLETE | One-click video export (SRT, CapCut, CSV, ZIP) |
| Phase 4 | COMPLETE | HTML story reader export, ZIP bundling |
| Phase 5 | COMPLETE | i18n (vi/en), 200+ locale strings |
| Phase 6 | COMPLETE | Story continuation, character editing, checkpoint workflow |
| Phase 7 | COMPLETE | TTS audio (edge-tts), image generation, credit/monetization, CI/CD |
| Phase 9 | COMPLETE | 31 team issues fixed; CoT self-review, story branching, Wattpad export |
| Phase 10 | COMPLETE | Self-review config polish, branch persistence, Wattpad enhancements; 813 tests |
| Phase 11 | COMPLETE | Security fixes, new agents, EPUB pipeline, analytics, web reader upgrades |
| Phase 13 | COMPLETE | RAG world-building (ChromaDB), agent dependency graph, XTTS v2 voice cloning; 973 tests |
| Phase 14 | COMPLETE | Character-consistent images (IP-Adapter + Seedream), visual profile store; 1025 tests |
| **Sprint 0** | COMPLETE | 11 bug fixes: SQLite concurrency, plot event pruning, word count helpers, JSON error preview, null safety; 1072 tests |
| Phase 15 | COMPLETE | Long-context LLM support (token counter, OpenAI SDK), emotion-aware voice rate/pitch; 1072 tests |
| Phase 16 | COMPLETE | Multi-agent debate protocol (3-round), debate response callbacks, debate decision consensus; 1102 tests |
| **Phase 16.5** | COMPLETE | LLM-powered debate (replaces rule-based), revised_score in DebateEntry, A/B threshold 0.10; 1108 tests |
| **Phase 17** | COMPLETE | Smart chapter revision (auto-detect weak chapters via quality scores, aggregate agent guidance, LLM revision with validation); 1116 tests |
| **Phase 18** | COMPLETE | Settings presets (Beginner/Advanced/Pro), adaptive prompts (12 genre + 4 score boosters), quality gate (inline between layers); +22 tests |
| **Phase 19** | COMPLETE | Onboarding wizard (4-step guided flow), knowledge graph (NetworkX + pure Python), E2E pipeline tests (22 tests); +22 tests |
| **Phase 20** | COMPLETE | Staging environment (docker-compose.staging.yml, parallel CI), progress tracker (structured events for gate/revision/scoring); +159 tests |
| **Sprint 1** | COMPLETE | App refactoring (79-line thin entry point, 1160-line extracted Gradio UI), security layer (Fernet encryption, prompt injection detection), bilingual emotion classifier, provider-aware LLM retry, SSE batch streaming, quality gate enabled by default; .env.example documentation |
| **Sprint 2** | COMPLETE | Layer 1 module split (generator → character_generator, chapter_writer, outline_builder), error hierarchy + FastAPI middleware, structured logging, knowledge graph method additions, prompt policy docs |

---

**Last Updated**: 2026-03-31 | **Doc Version**: 2.7 (Sprint 2: Layer 1 Module Split, Error Hierarchy, Structured Logging) | **Tests**: 1327+
