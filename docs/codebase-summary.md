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
├── app.py                          # Flask API entry point
├── config.py                       # ConfigManager (singleton), LLMConfig, PipelineConfig
├── models/
│   └── schemas.py                  # Pydantic models for all layers
├── services/
│   ├── llm_client.py               # OpenAI-compatible LLM wrapper with retry/cache/fallback
│   ├── llm_cache.py                # SQLite-based prompt result caching
│   ├── prompts.py                  # Centralized prompt templates
│   ├── openclaw_manager.py         # OpenClaw backend switching
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
├── scripts/
│   └── setup-openclaw.sh           # OpenClaw deployment script
└── locales/                        # i18n resources
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
- **LLMClient**: Singleton OpenAI-compatible client
- Retry logic: MAX_RETRIES=3 with exponential backoff
- Cache: SQLite with TTL (configurable cache_ttl_days)
- Fallback: Auto-switch from OpenClaw → API if configured
- Methods:
  - `generate(system_prompt, user_prompt, temperature, max_tokens, json_mode)`
  - `generate_json(...)` — wraps generate() with JSON parsing & validation
  - `_get_client()` — lazy init, backend selection logic

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

### openclaw_manager.py
- Switches between OpenClaw (local) and OpenAI API backends
- Health checks & auto-fallback on failure

## Configuration (config.py)

### LLMConfig
- `api_key`, `base_url`, `model` (default: gpt-4o-mini)
- `temperature` (0.8 for generation, 0.3 for extraction)
- `max_tokens` (4096 default)
- `backend_type` ("api" or "openclaw")
- `auto_fallback`, `cache_enabled`, `cache_ttl_days`

### PipelineConfig
- `num_chapters`, `words_per_chapter`
- `genre`, `sub_genres`, `writing_style`
- `context_window_chapters` (Phase 1 feature)
- Layer 2: `num_simulation_rounds`, `num_agents`, `drama_intensity`
- Layer 3: `shots_per_chapter`, `video_style`
- `language` ("vi" for Vietnamese)

## API Endpoints (app.py - Flask)

Main endpoints:
- `POST /api/generate-story` — Trigger full pipeline or Layer 1 only
- `POST /api/layer2/enhance` — Drama simulation
- `POST /api/layer3/storyboard` — Video metadata generation
- `GET /api/status/<task_id>` — Progress tracking
- `GET /api/config` — Current configuration

## Execution Flow

1. **App startup**: Load config → Initialize LLMClient (singleton) → Cache init
2. **Generate story**: Orchestrator calls Layer 1 StoryGenerator.generate_full_story()
3. **Character tracking** (Phase 1): Each chapter → extract states/events → update rolling context
4. **Layer 2** (optional): Feed StoryDraft to drama simulator with character states
5. **Layer 3** (optional): Generate storyboards from enhanced story

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

## Development Status

**Phase 1 (COMPLETE)**: Character state tracking with rolling context
- CharacterState, PlotEvent, StoryContext models
- Parallel extraction in generate_full_story()
- Context window configuration

**Phase 5 (COMPLETE)**: Story quality metrics
- ChapterScore, StoryScore models
- QualityScorer service with parallel processing
- Integration at Layer 1 & Layer 2
- UI tab + toggle

**Phase 2-3-4**: In progress/planned

---

**Last Updated**: 2026-03-23 | **Doc Version**: 1.1
