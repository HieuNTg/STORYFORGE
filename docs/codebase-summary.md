# Novel Auto Pipeline - Codebase Summary

## Overview

**Novel Auto** is a three-layer automated pipeline for creating dramatic, multimedia content from story ideas.

| Layer | Purpose | Input | Output |
|-------|---------|-------|--------|
| **Layer 1** | Story generation | Genre, idea, character specs | Full novel draft with rolling character/plot context |
| **Layer 2** | Drama enhancement | Story draft | Intensified narrative with agent feedback loops |
| **Layer 3** | Video production | Enhanced story | Storyboards, shots, video metadata |

## Project Structure

```
novel-auto/
├── app.py                          # Gradio web UI with web auth, template selector, quick start
├── config.py                       # ConfigManager (singleton), LLMConfig, PipelineConfig
├── models/
│   └── schemas.py                  # Pydantic models for all layers
├── services/
│   ├── llm_client.py               # LLM wrapper: routes "api" (OpenAI) or "web" (DeepSeek browser)
│   ├── llm_cache.py                # SQLite-based prompt result caching
│   ├── prompts.py                  # Centralized prompt templates
│   ├── browser_auth.py             # Chrome CDP + Playwright credential capture
│   ├── deepseek_web_client.py      # DeepSeek web API client with PoW challenge solver
│   ├── quality_scorer.py           # LLM-as-judge quality metrics (Phase 5)
│   └── __init__.py
├── pipeline/
│   ├── orchestrator.py             # Main workflow coordinator
│   ├── layer1_story/
│   │   └── generator.py            # StoryGenerator class - character, world, chapters
│   ├── layer2_enhance/
│   │   ├── simulator.py            # Drama simulation with agent loops
│   │   ├── analyzer.py             # Post-simulation analysis
│   │   ├── enhancer.py             # Narrative enhancement
│   │   └── _agent.py               # Agent registry & base class
│   ├── layer3_video/
│   │   └── storyboard.py           # Shot & scene generation
│   ├── agents/
│   │   ├── base_agent.py           # BaseAgent interface
│   │   ├── character_specialist.py # Character consistency checks
│   │   ├── continuity_checker.py   # Plot continuity validation
│   │   ├── dialogue_expert.py      # Dialogue quality
│   │   ├── drama_critic.py         # Drama intensity scoring
│   │   ├── editor_in_chief.py      # Final editorial review
│   │   └── agent_registry.py       # Agent discovery & management
│   └── __init__.py
├── data/
│   ├── config.json                 # LLM & pipeline configuration
│   ├── templates/
│   │   └── story_templates.json    # 13 story templates (zero-config onboarding)
│   ├── auth_profiles.json          # Cached browser auth credentials
│   └── cache.db                    # SQLite cache for LLM results
└── output/                         # Generated stories (TXT, Markdown, JSON)
```

## Core Models (schemas.py)

### Layer 1 - Story Generation

**Character**: Protagonist/antagonist/support with personality, background, motivation, relationships.

**WorldSetting**: Fictional universe context (era, locations, rules).

**ChapterOutline**: Chapter structure with summary, events, character involvement, emotional arc.

**Chapter**: Full written chapter (content, word count, summary).

**CharacterState** (Phase 1): Rolling snapshot of character state (mood, arc position, knowledge, relationship changes, last action). Updated per-chapter for coherence tracking.

**PlotEvent** (Phase 1): Important story events with chapter reference and character involvement list. Tracked across full story for consistency.

**StoryContext** (Phase 1): Rolling context window with recent chapter summaries (limited to `context_window_chapters`), character states, plot events. Passed to `write_chapter()` to maintain continuity.

**StoryDraft**: Complete story artifact with title, genre, characters, world, outlines, chapters, and Phase 1 character_states/plot_events for Layer 2 handoff.

### Layer 2 - Drama Enhancement

**DramaSimulation, AgentFeedback, SimulationResult**: Multi-agent feedback loops.

### Layer 3 - Video Production

**Shot, Scene, Storyboard**: Scene-level video metadata.

## Phase 1: Character State Tracking (Latest)

### Goal
Maintain rolling context across chapter generation to prevent character inconsistency and plot holes.

### Implementation

**3 Extraction Methods in StoryGenerator**:

1. `extract_character_states(content, characters)` → `list[CharacterState]`
   - Prompt: `EXTRACT_CHARACTER_STATE` (services/prompts.py)
   - Temp: 0.3 (low, for consistency)
   - Max tokens: 1000
   - Outputs: mood, arc_position, knowledge, relationship_changes, last_action per character

2. `extract_plot_events(content, chapter_number)` → `list[PlotEvent]`
   - Prompt: `EXTRACT_PLOT_EVENTS`
   - Temp: 0.3
   - Max tokens: 1000
   - Outputs: major story events tied to chapter + characters involved

3. `summarize_chapter(content)` → str
   - Brief summary for context window (max 500 tokens)

**generate_full_story() Loop** (parallel extraction):
```
for each chapter outline:
  - write_chapter(context=story_context)  # Uses rolling context
  - [parallel] summarize + extract_character_states + extract_plot_events
  - Update story_context:
    - recent_summaries (keep last N via context_window_chapters config)
    - character_states (merge by name, latest wins)
    - plot_events (cap to 50 for unbounded growth prevention)
  - Store summary in chapter.summary
- Store final character_states & plot_events in draft for Layer 2
```

### Config Changes

**PipelineConfig** (config.py):
- Added `context_window_chapters: int = 2` — how many recent chapter summaries to pass forward

### LLM Client Enhancement

**llm_client.py** `generate_json()`:
- Added `max_tokens` parameter for extraction calls (defaults to config value if not set)
- Enables token control for compact extraction (1000 tokens vs 4000+ for chapter writing)

### Data Flow
```
Chapter → extract_character_states → CharacterState ─┐
                                                      ├→ StoryContext (rolling)
Chapter → extract_plot_events → PlotEvent ───────────┤   ↓
                                                      └→ write_chapter() for next chapter
Chapter summary ────────────────────────────────────→ (context_window buffer)
```

## Services Overview

### llm_client.py
- **LLMClient**: Singleton with dual-backend routing
- **Backend routing**:
  - `backend_type = "api"` → OpenAI-compatible API (requires api_key)
  - `backend_type = "web"` → DeepSeek web browser auth (free, no API key)
- Retry logic: MAX_RETRIES=3 with exponential backoff
- Cache: SQLite with TTL (configurable cache_ttl_days)
- Methods:
  - `generate(system_prompt, user_prompt, temperature, max_tokens, json_mode)`
  - `generate_json(...)` — wraps generate() with JSON parsing & validation
  - `_is_web_backend()` — checks backend_type
  - `_get_web_client()` — lazy init DeepSeekWebClient

### prompts.py
- Centralized template library
- Key Phase 1 prompts:
  - `EXTRACT_CHARACTER_STATE` — analyzes chapter for character mood/arc/knowledge
  - `EXTRACT_PLOT_EVENTS` — identifies major story events
  - `WRITE_CHAPTER` — main chapter writing prompt (uses context)
  - `SUMMARIZE_CHAPTER` — brief chapter summary
  - Others: SUGGEST_TITLE, GENERATE_CHARACTERS, GENERATE_WORLD, GENERATE_OUTLINE

### llm_cache.py
- SQLite cache with TTL-based eviction
- Cache key: hash(prompt + config)
- Methods: `get()`, `set()`, `evict_expired()`

### browser_auth.py
- Chrome CDP launcher with Playwright interception
- Captures HTTP headers (cookies, bearer tokens) during login
- Stores credentials in `data/auth_profiles.json` (encrypted recommended for production)
- Key functions:
  - `_find_chrome_path()` — cross-platform Chrome detection
  - `launch_chrome()` — start Chrome with CDP on port 9222
  - `capture_credentials()` — intercept DeepSeek login flow
  - `get_session()` — retrieve cached credentials

### deepseek_web_client.py
- Makes HTTP requests to DeepSeek's internal web API
- Implements proof-of-work (PoW) challenge solver
- Handles SSE streaming responses
- Key functions:
  - `_solve_pow(challenge, salt, difficulty)` — SHA3/SHA256 hash solving
  - `create_chat(messages, model, stream=False)` — sends chat request
  - `get_models()` — lists available models (deepseek-chat, deepseek-reasoner)

## Configuration (config.py)

### LLMConfig
- `api_key`, `base_url`, `model` (default: gpt-4o-mini)
- `temperature` (0.8 for generation, 0.3 for extraction)
- `max_tokens` (4096 default)
- **Backend selection**:
  - `backend_type` ("api" or "web")
  - `web_auth_provider` ("deepseek-web" for free web auth)
- `cache_enabled`, `cache_ttl_days`, `max_parallel_workers`
- `cheap_model`, `cheap_base_url` (optional, for cost control)

### PipelineConfig
- `num_chapters`, `words_per_chapter`
- `genre`, `sub_genres`, `writing_style`
- `context_window_chapters` (Phase 1 feature)
- Layer 2: `num_simulation_rounds`, `num_agents`, `drama_intensity`
- Layer 3: `shots_per_chapter`, `video_style`
- `language` ("vi" for Vietnamese)

## UI & Entry Points (app.py - Gradio)

**Web Auth Tab**:
- "Tao Chrome CDP" button — launch Chrome with credential interception
- "Bat dau dang nhap" button — capture DeepSeek login flow
- "Xoa thong tin" button — clear cached credentials
- Status display — shows current auth provider + credentials state

**Pipeline Tab**:
- Genre dropdown → auto-populates templates for selected genre
- Template selector dropdown — 13 pre-configured story templates
- "Tao ngay" button — quick start with selected template
- Full form: custom title, idea, chapters, characters, words per chapter
- Layer selection: Layer 1 only, or full pipeline (1+2+3)
- Quality scoring toggle: "Cham diem tu dong"

**Output Tabs**:
- Pipeline output (story, enhanced narrative, storyboards)
- Quality metrics ("Chat Luong") with layer scores
- Export options: TXT, Markdown, JSON + ZIP download

## Execution Flow

**Phase 1: StoryForge (Web Auth + Zero-Config Onboarding)**
1. **App startup**: Load config → Check for cached web auth credentials
2. **Web Auth** (optional): User launches Chrome, logs into DeepSeek, credentials auto-captured
3. **Template selection**: User picks genre → dropdown populates 13 story templates
4. **Quick start**: "Tao ngay" button → pre-fill form from template + generate
5. **Generate story**: Orchestrator calls Layer 1 StoryGenerator.generate_full_story()
6. **LLM routing**: LLMClient checks backend_type → routes to API or DeepSeek web
7. **Character tracking** (Phase 1): Each chapter → extract states/events → update rolling context
8. **Quality scoring** (Phase 5): Score chapters (Layer 1 + Layer 2)
9. **Output**: Display story, quality metrics, export options

## Phase 5: Story Quality Metrics (NEW)

### Overview
LLM-as-judge quality scoring at Layer 1 & Layer 2. Scores story coherence, character consistency, drama, writing quality on 1-5 scale.

### New Models
- **ChapterScore**: Single chapter scores (4 dimensions + overall mean)
- **StoryScore**: Aggregate story scores (avg per dimension, weakest chapter, layer marker)
- Both added to `PipelineOutput.quality_scores[]`

### Quality Scorer Service
**services/quality_scorer.py** — `QualityScorer` class:
- `score_chapter(chapter: Chapter, context: str) -> ChapterScore`
  - Excerpts long chapters (head 2600 + tail 1400 chars to fit budget)
  - Uses "cheap" model tier, temp=0.2 for consistency
  - Clamps scores to 1-5 range
- `score_story(chapters: list[Chapter], layer: int) -> StoryScore`
  - Parallel scoring with ThreadPoolExecutor (max 3 workers)
  - Sequential context building (each chapter sees prev chapter's content)
  - Aggregates to overall 4-metric story score
  - Identifies weakest chapter

### Scoring Prompt
**SCORE_CHAPTER** (services/prompts.py, lines 143-157):
```
Evaluate chapter on 4 criteria (1-5 scale):
1. coherence: Plot logic & flow
2. character_consistency: Behavior matches personality
3. drama: Tension & engagement
4. writing_quality: Prose clarity & vividness
```

### Pipeline Integration
**orchestrator.py**:
- `enable_scoring: bool = True` parameter (new)
- Layer 1 scoring (after story draft, lines 106-115)
  - Logs: overall score, weakest chapter
- Layer 2 scoring (after enhancement, lines 165-179)
  - Logs: score + delta from Layer 1

### UI Changes
**app.py**:
- "Chat Luong" tab (line 173): New quality output tab
- `quality_output` Markdown (line 174-176): Display scoring results
- `enable_scoring_cb` checkbox (line 131-134): Toggle scoring on/off
- 9-element tuple outputs (added quality field)

---

## Phase 2: UI Polish & Progress UX

### Goal
Enhance user experience with visual progress tracking, status indicators, layer detection, and responsive UI consolidation.

### Implementation

**Progress Bar** (`_progress_html()` in app.py):
- 3-segment HTML progress bar showing Layer 1 → Layer 2 → Layer 3
- States: idle (gray), active (blue with pulse), done (green)
- Real-time layer detection from log messages
- Animated status transitions

**Status Badges**:
- `status-idle`: San sang (Ready)
- `status-running`: Running with pulse animation
- `status-done`: Completed
- `status-error`: Error state
- HTML-based, CSS-driven styling

**Layer Detection** (`_detect_layer()` in app.py):
- Parses progress log messages to detect current layer
- Vietnamese diacritics support via `_strip_diacritics()` (NFD normalization)
- Recognizes keywords: Layer 1/TAO TRUYEN/CHUONG, Layer 2/MO PHONG/ENHANCE, Layer 3/STORYBOARD/VIDEO
- Used for progress bar updates

**Output Tabs Consolidation** (6 → 4 tabs):
- Tab 1: "Truyen" — Layer 1 draft + Layer 2 enhanced narrative (split sections)
- Tab 2: "Mo Phong" — Simulation results
- Tab 3: "Video" — Storyboard & script
- Tab 4: "Danh Gia" — Agent reviews + quality scores
- Removed separate tabs for draft/enhanced to reduce clutter

**Log Accordion**:
- "Chi tiet tien trinh" accordion (collapsed by default)
- Full progress log accessible without clutter

**Mobile Responsive CSS**:
- Progress segment font reduction (@media max-width: 768px)
- Flexbox adjustments for mobile layout
- Touch-friendly badge sizing

**XSS-Safe HTML Rendering**:
- `_html.escape()` used for progress step text
- All user input HTML-escaped before display

**Resume Pipeline Stream Support**:
- `resume_from_checkpoint()` now accepts `progress_callback` parameter
- Mirrors `run_pipeline()` stream signature
- DRY principle: both methods support live progress updates

### New Functions/Methods
- `_progress_html(layer: int, step: str) -> str` — Generate progress bar HTML
- `_detect_layer(msg: str) -> int` — Extract layer number from log message
- `_strip_diacritics(text: str) -> str` — Remove Vietnamese diacritics for matching
- `resume_from_checkpoint(..., progress_callback=None, ...)` — Added callback support

### Testing
- **tests/test_phase2_ui.py**: 60+ tests covering:
  - Progress HTML generation (all layer states)
  - Layer detection from Vietnamese log messages
  - _format_output() tuple structure (11-element)
  - CSS classes and responsive behavior
  - Status badge states
  - Output tab consolidation

---

## Development Status

**Phase 1 (COMPLETE)**: Character state tracking with rolling context
- CharacterState, PlotEvent, StoryContext models
- Parallel extraction in generate_full_story()
- Context window configuration

**Phase 2 (COMPLETE)**: UI Polish & Progress UX
- Progress bar (3-segment HTML)
- Status badges (4 states)
- Layer detection with Vietnamese diacritics
- Output tabs consolidation (6 → 4)
- Mobile responsive CSS
- XSS-safe rendering
- Resume pipeline streaming
- 60+ comprehensive tests

**Phase 5 (COMPLETE)**: Story quality metrics
- ChapterScore, StoryScore models
- QualityScorer service with parallel processing
- Integration at Layer 1 & Layer 2
- UI tab + toggle

**Phase 3-4**: In progress/planned

---

**Last Updated**: 2026-03-23 | **Doc Version**: 1.2
