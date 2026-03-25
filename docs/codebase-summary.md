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
├── app.py                          # Gradio web UI — delegates to ui/tabs/ modules
├── config.py                       # ConfigManager (singleton), LLMConfig, PipelineConfig
├── models/
│   └── schemas.py                  # Pydantic models for all layers + quality scoring
├── services/
│   ├── llm_client.py               # LLM wrapper: routes "api" (OpenAI) or "web" (DeepSeek)
│   ├── llm_cache.py                # SQLite-based prompt result caching
│   ├── prompts.py                  # Centralized prompt templates (localize_prompt wrapper)
│   ├── browser_auth.py             # Chrome CDP + Playwright credential capture
│   ├── deepseek_web_client.py      # DeepSeek web API client with PoW challenge solver
│   ├── quality_scorer.py           # LLM-as-judge quality metrics (4 dimensions, 1-5 scale)
│   ├── video_exporter.py           # SRT, voiceover, image prompts, CapCut JSON, CSV, ZIP
│   ├── html_exporter.py            # Self-contained HTML reader (dark/light mode, chapter nav)
│   ├── tts_audio_generator.py      # Multi-provider TTS (edge-tts, kling, xtts), Vietnamese voices
│   ├── image_generator.py          # DALL-E / SD API image generation per storyboard panel
│   ├── credit_manager.py           # Credit/monetization system with bcrypt-hashed accounts
│   ├── self_review.py              # CoT+CAI self-review for chapter quality assessment
│   ├── story_brancher.py           # Interactive story branching with DAG management
│   ├── wattpad_exporter.py         # Wattpad/NovelHD export service
│   ├── rag_knowledge_base.py       # RAG with ChromaDB + sentence-transformers (500-char chunks)
│   └── i18n.py                     # Thread-safe i18n singleton (vi/en JSON locales)
├── pipeline/
│   ├── orchestrator.py             # Main workflow coordinator
│   ├── layer1_story/
│   │   └── generator.py            # StoryGenerator — characters, world, chapters, continuation
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
├── locales/
│   ├── vi.json                     # Vietnamese locale strings (200+)
│   └── en.json                     # English locale strings (200+)
├── .github/
│   └── workflows/
│       └── ci.yml                  # GitHub Actions CI/CD pipeline
├── data/
│   ├── config.json                 # LLM & pipeline configuration
│   ├── templates/
│   │   └── story_templates.json    # 13 story templates (zero-config onboarding)
│   ├── auth_profiles.json          # Cached browser auth credentials
│   └── cache.db                    # SQLite cache for LLM results
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

### image_generator.py
- Pluggable provider interface: DALL-E or Stable Diffusion API
- Generates images per storyboard panel from `export_image_prompts()`
- Provider selection via `STORYFORGE_IMAGE_PROVIDER` env var (`none` disables)
- API key/URL injected from environment (`IMAGE_API_KEY`, `IMAGE_API_URL`)

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

### i18n.py
- Thread-safe singleton; JSON locale lookup with fallback chain: requested → `vi` → raw key
- 200+ strings per locale
- `_t(key)` shorthand used throughout app.py (167+ call sites)

### prompts.py
- `localize_prompt(template, lang)` wrapper for all generation prompts
- Key prompts: WRITE_CHAPTER, EXTRACT_CHARACTER_STATE, EXTRACT_PLOT_EVENTS, SUMMARIZE_CHAPTER,
  SCORE_CHAPTER, SUGGEST_TITLE, GENERATE_CHARACTERS, GENERATE_WORLD, GENERATE_OUTLINE,
  CONTINUE_OUTLINE
- **Phase 13**: RAG_CONTEXT_SECTION — injected into world-building & chapter prompts when RAG enabled

### rag_knowledge_base.py (Phase 13)
- RAGKnowledgeBase service using ChromaDB + sentence-transformers
- Methods: `add_file()`, `add_documents()`, `query()`, `clear()`, `count()`
- Chunking: 500-char chunks with 50-char overlap; sentence-boundary aware
- File support: .txt, .md, .pdf (10 MB max, graceful degradation if libs not installed)
- Integration: `generator.py` `generate_world()` & `_build_chapter_prompt()` inject RAG context when enabled
- Dependencies: chromadb>=0.4.0, sentence-transformers>=2.2.0

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
- Jobs: lint (flake8), typecheck (mypy), test (pytest), build validation
- Context-aware escalation: failures escalate via agent feedback loop patterns

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

---

**Last Updated**: 2026-03-25 | **Doc Version**: 2.0 (Phase 13: RAG World-Building, Agent DAG, XTTS Voice Cloning)
