# System Architecture

## High-Level Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│ Novel Auto: Three-Layer Content Generation Pipeline              │
└─────────────────────────────────────────────────────────────────┘

Input: Genre + Story Idea + Config
  ↓
┌─────────────────────────────────────────────────────────────────┐
│ LAYER 1: Story Generation (StoryGenerator)                       │
│                                                                   │
│ 1. Generate characters, world, chapter outlines                   │
│ 2. Parallel chapter writing with rolling context                  │
│ 3. Character State Tracking (Phase 1):                            │
│    - Extract character mood, arc, knowledge per chapter           │
│    - Track plot events for continuity                             │
│    - Maintain sliding window of recent summaries                  │
│ Output: StoryDraft (chapters + character_states + plot_events)   │
└─────────────────────────────────────────────────────────────────┘
  ↓
┌─────────────────────────────────────────────────────────────────┐
│ QUALITY METRICS: Scoring Layer 1 (Phase 5)                       │
│                                                                   │
│ - QualityScorer: LLM-as-judge on 4 dimensions                     │
│   * coherence: Plot logic & flow                                  │
│   * character_consistency: Behavior matches personality            │
│   * drama: Tension & engagement                                   │
│   * writing_quality: Prose clarity & vividness                    │
│ - Parallel scoring (max 3 workers), sequential context            │
│ - Identifies weakest chapters, logs metrics                       │
│ Output: StoryScore with per-chapter breakdown + layer marker      │
└─────────────────────────────────────────────────────────────────┘
  ↓
┌─────────────────────────────────────────────────────────────────┐
│ LAYER 2: Drama Enhancement (via agents)                          │
│                                                                   │
│ - Multi-agent feedback loops (6 agents)                           │
│ - Character consistency checks                                    │
│ - Dialogue quality & continuity                                   │
│ - Drama intensity scoring                                         │
│ Output: Enhanced StoryDraft with feedback metadata                │
└─────────────────────────────────────────────────────────────────┘
  ↓
┌─────────────────────────────────────────────────────────────────┐
│ QUALITY METRICS: Scoring Layer 2 (Phase 5)                       │
│                                                                   │
│ - Same 4 dimensions as Layer 1, but on enhanced story             │
│ - Computes delta (improvement from Layer 1)                       │
│ - Logs overall + weakest chapter                                  │
│ Output: StoryScore with layer=2 marker, delta computation         │
└─────────────────────────────────────────────────────────────────┘
  ↓
┌─────────────────────────────────────────────────────────────────┐
│ LAYER 3: Video Storyboarding                                     │
│                                                                   │
│ - Scene-level breakdown (shots per chapter)                       │
│ - Camera directions & visual metadata                             │
│ Output: Storyboard + video production specs                       │
└─────────────────────────────────────────────────────────────────┘
  ↓
Final Output: Complete novel + enhanced narrative + quality scores + video specs
```

## Layer 1: Story Generation Architecture

### StoryGenerator Class Flow

```
generate_full_story(title, genre, idea, num_chapters, ...)
│
├─→ generate_characters() → list[Character]
│
├─→ generate_world() → WorldSetting
│
├─→ generate_outline() → (synopsis, list[ChapterOutline])
│
├─→ [MAIN LOOP] for each chapter:
│   │
│   ├─→ write_chapter(outline, context=story_context) → Chapter
│   │   └─ Prompt includes:
│   │      - Character descriptions & relationships
│   │      - World details
│   │      - Chapter outline
│   │      - ROLLING CONTEXT (Phase 1):
│   │        * Recent chapter summaries (rolling window)
│   │        * Current character states (mood, arc, knowledge)
│   │        * Recent plot events (capped to 50)
│   │
│   ├─→ [PARALLEL] Extract context (ThreadPoolExecutor, max_workers=3):
│   │   ├─→ summarize_chapter() → summary_f
│   │   ├─→ extract_character_states() → states_f (Phase 1)
│   │   └─→ extract_plot_events() → events_f (Phase 1)
│   │
│   └─→ Update story_context (rolling):
│       ├─ recent_summaries.append(summary)
│       │  └─ Keep only last context_window_chapters summaries
│       ├─ Merge character_states (by name, latest wins)
│       └─ Extend plot_events (cap at 50 to prevent unbounded growth)
│
└─→ Return StoryDraft with:
    - All chapters
    - character_states (final state per character)
    - plot_events (all tracked events)
```

### Phase 1: Character State Tracking

**Problem Solved**: Without context, LLM tends to forget character progression, relationships, and major plot points across chapters.

**Solution**: Rolling context window with three extracted artifacts:

1. **CharacterState** (per chapter extraction)
   ```
   name: str
   mood: str                    # "hopeful", "desperate", etc.
   arc_position: str           # "rising", "crisis", "resolution"
   knowledge: list[str]        # What character knows
   relationship_changes: list  # How relationships evolved
   last_action: str            # Most recent action/decision
   ```

2. **PlotEvent** (per chapter extraction)
   ```
   chapter_number: int
   event: str                  # "Character X discovers Y"
   characters_involved: list   # ["X", "Y"]
   ```

3. **StoryContext** (rolling window passed to next chapter)
   ```
   recent_summaries: list[str]       # Last N chapters (N = context_window_chapters)
   character_states: list[CharacterState]  # Current state per character
   plot_events: list[PlotEvent]      # Last 50 important events
   total_chapters: int
   current_chapter: int
   ```

**Extraction Prompts** (services/prompts.py):
- `EXTRACT_CHARACTER_STATE`: Analyzes chapter content, outputs structured character state
- `EXTRACT_PLOT_EVENTS`: Identifies major story events from chapter

**LLM Parameters** (extraction vs writing):
- Writing: temp=0.8, max_tokens=4096 (creative)
- Extraction: temp=0.3, max_tokens=1000 (consistent, compact)

### Data Flow Diagram

```
Chapter Content
    ↓
    ├→ LLM: summarize_chapter() ──→ Text summary
    │
    ├→ LLM: extract_character_states() ──→ CharacterState[]
    │                                       ├─ mood
    │                                       ├─ arc_position
    │                                       ├─ knowledge
    │                                       ├─ relationship_changes
    │                                       └─ last_action
    │
    └→ LLM: extract_plot_events() ──→ PlotEvent[]
                                       ├─ chapter_number
                                       ├─ event
                                       └─ characters_involved

    All three outputs → StoryContext (rolling)
    ↓
    next chapter: write_chapter(context=story_context)
    └─ Receives all rolling context in prompt
```

## LLM Client Architecture

### Singleton Pattern with Fallback

```
LLMClient (singleton)
├─ _get_client() → OpenAI instance
│  ├─ Check backend_type (LLMConfig)
│  │  ├─ "openclaw" → localhost:3002 + health check
│  │  └─ "api" → OpenAI base_url + API key
│  └─ Cache client for reuse (thread-safe)
│
├─ generate(system_prompt, user_prompt, ...) → str
│  ├─ Check LLMCache for hit
│  ├─ Retry with exponential backoff (MAX_RETRIES=3)
│  ├─ On transient error → fallback to API if configured
│  └─ Return generated text
│
└─ generate_json(system_prompt, user_prompt, max_tokens) → dict
   ├─ Call generate() with json_mode=true
   ├─ Parse JSON response
   ├─ Validate against model schema (Pydantic)
   └─ Return parsed dict
```

### Retry & Fallback Logic

```
Call LLM
  ↓
[Attempt 1]
  ├─ Cache hit? Return cached result
  ├─ Call OpenClaw (if backend_type="openclaw")
  │  ├─ Success → Cache + return
  │  └─ Transient error + auto_fallback=true?
  │     └─ [Fall through to API]
  └─ Call OpenAI API
     ├─ Success → Cache + return
     └─ Transient error? → Retry with backoff

[Attempt 2, 3, ...] → Same as attempt 1

Non-transient error → Fail immediately
```

## Configuration Management

### ConfigManager (Singleton)

```
ConfigManager (singleton)
├─ Load from data/config.json on init
├─ LLMConfig:
│  ├─ API credentials (api_key, base_url, model)
│  ├─ Temperature & max_tokens defaults
│  ├─ Backend switching (backend_type, openclaw_port)
│  ├─ Cache settings (cache_enabled, cache_ttl_days)
│  └─ Fallback behavior (auto_fallback)
│
└─ PipelineConfig:
   ├─ Layer 1: num_chapters, words_per_chapter, genre, style
   ├─ Phase 1: context_window_chapters (default: 2)
   ├─ Layer 2: num_simulation_rounds, num_agents, drama_intensity
   └─ Layer 3: shots_per_chapter, video_style
```

## Agent Architecture (Layer 2)

### Agent Registry Pattern

```
BaseAgent (abstract interface)
├─ feedback(story_draft, context) → AgentFeedback
├─ name, expertise, confidence
└─ Subclasses:
   ├─ CharacterSpecialist (consistency checks)
   ├─ ContinuityChecker (plot holes)
   ├─ DialogueExpert (dialogue quality)
   ├─ DramaCritic (intensity scoring)
   ├─ EditorInChief (final review)
   └─ [more agents]

AgentRegistry
├─ discover() → list[BaseAgent]
├─ get_by_name(name) → BaseAgent
└─ register(agent) → void
```

## Quality Scoring Architecture (Phase 5)

### QualityScorer Flow

```
PipelineOrchestrator.run_full_pipeline()
│
├─ [After Layer 1: story generation complete]
│  ├─ enable_scoring=True?
│  │  └─ QualityScorer.score_story(draft.chapters, layer=1)
│  │     ├─ For each chapter:
│  │     │  └─ score_chapter(chapter, prev_context) → ChapterScore
│  │     │     ├─ Excerpt long chapters (head 2600 + tail 1400)
│  │     │     ├─ Call LLM: SCORE_CHAPTER prompt (temp=0.2, cheap tier)
│  │     │     ├─ Parse JSON response (4 scores)
│  │     │     └─ Clamp to 1-5 range, compute overall (mean)
│  │     │
│  │     └─ Parallel pool (ThreadPoolExecutor, max 3 workers)
│  │        └─ Aggregate to StoryScore:
│  │           ├─ avg_coherence, avg_character, avg_drama, avg_writing
│  │           ├─ overall = mean(4 averages)
│  │           ├─ weakest_chapter = min overall
│  │           └─ scoring_layer = 1 (marker)
│  │
│  └─ Append to output.quality_scores[]
│     └─ Log: "Layer 1: {score.overall:.1f}/5 | Weakest: {weakest_ch}"
│
├─ [After Layer 2: drama enhancement complete]
│  ├─ enable_scoring=True?
│  │  └─ QualityScorer.score_story(enhanced.chapters, layer=2)
│  │     └─ Same process as Layer 1
│  │
│  └─ Append to output.quality_scores[]
│     └─ Log with delta: "Layer 2: {score.overall:.1f}/5 | Delta: {+0.5}"
│
└─ Return PipelineOutput with quality_scores[]
   └─ UI displays via "Chat Luong" tab
```

### Scoring Dimensions

| Dimension | Scale | Definition |
|-----------|-------|-----------|
| **coherence** | 1-5 | Plot logic, narrative flow, internal consistency |
| **character_consistency** | 1-5 | Characters behave per established personality/arc |
| **drama** | 1-5 | Tension, emotional engagement, pacing, stakes |
| **writing_quality** | 1-5 | Prose clarity, vocabulary, imagery, dialogue naturalness |

Each dimension independently scored; **overall = mean(4 dimensions)**

### LLM-as-Judge Configuration

**Prompt**: `SCORE_CHAPTER` (services/prompts.py)
- Input: Chapter content (excerpted if > 4000 chars) + prev chapter context
- Output: JSON with 4 scores (1-5) + notes field
- Temperature: 0.2 (deterministic, low variance)
- Model tier: "cheap" (cost control)
- Max tokens: 500 (compact output)

**Excerpt Strategy** (long chapters):
```
if len(content) > 4000:
    head = content[:2600]
    tail = content[-1400:]
    excerpted = head + "\n...\n" + tail
```
Preserves beginning (setup) and ending (consequences) while cutting middle.

## Export & Download Architecture (Phase 4)

### Export Methods

**export_output(output_dir, formats)** → `list[str]`
- Generates files in specified formats
- Returns list of file paths (empty if no output generated)
- Formats: TXT, Markdown, JSON
- Files timestamped: `{timestamp}_{type}.{ext}`

| Format | Files Generated | Content |
|--------|-----------------|---------|
| TXT | `draft.txt`, `enhanced.txt` | Story chapters (plain text) |
| JSON | `video_script.json`, `simulation.json` | Structured data |
| Markdown | `story.md` | Story with metadata (genre, drama_score) |

**export_zip(output_dir, formats)** → `str`
- Bundles all exported files into single ZIP
- Returns ZIP file path (empty string if no files)
- Archive name: `{timestamp}_novel_auto.zip`
- Preserves basenames (removes path prefixes)

**_export_markdown(output_dir, timestamp)** → `Optional[str]`
- Private method: writes Markdown with metadata
- Prefers enhanced_story, fallback to story_draft
- Returns file path or None if no story available
- Includes: Title, Genre, Drama Score, Chapters

### UI Integration (app.py)

**Export widgets** (Pipeline tab):
```python
export_formats = gr.CheckboxGroup(
    choices=["TXT", "Markdown", "JSON"],
    value=["TXT", "Markdown", "JSON"]
)
export_btn = gr.Button("Xuat file")          # Individual files
zip_btn = gr.Button("Download All (ZIP)")    # Bundle
export_files_output = gr.File(               # gr.File widget
    label="File xuat", file_count="multiple"
)
```

**Event handlers**:
- `export_btn.click()` → `export_files()` → returns `list[str]` paths
- `zip_btn.click()` → `export_zip_handler()` → returns `[zip_path]`
- Both update `export_files_output` (gr.File displays downloads)

### File Output Location
- Default: `output/` directory
- Timestamped: `YYYYMMDD_HHMMSS_{type}.{ext}`
- ZIP: `YYYYMMDD_HHMMSS_novel_auto.zip`

## Error Handling Strategy

### LLM Client
- **Transient errors** (429, 5xx, timeout): Retry with backoff
- **Non-transient** (invalid auth, 400): Fail fast
- **Cache hit**: No LLM call needed

### Extraction Methods
- Parse error in CharacterState/PlotEvent → Log + skip entry
- LLM call fails → Fallback to empty list, log warning
- No rollback; continue with next chapter

### Export Methods
- No files generated → return empty list/string
- File write error → Log error, skip file
- ZIP creation error → Log error, return empty string
- UI handles None/empty gracefully (no download shown)

### Schema Validation
- Pydantic models auto-validate on instantiation
- Invalid data → validation error logged, entry skipped
- Type coercion attempted (int to str, etc.)

## Token Efficiency

### Chapter Writing (Layer 1)
- `words_per_chapter`: ~2000 words (context)
- `max_tokens`: 4096 (output)
- Total: ~6000 tokens per chapter

### Context Extraction (Phase 1)
- Summary: 500 tokens max
- Character states: 1000 tokens max
- Plot events: 1000 tokens max
- Total: ~2500 tokens per chapter

### Quality Scoring (Phase 5)
- Per chapter: ~150-200 tokens input (excerpted content + context)
- Per chapter: ~50-100 tokens output (4 scores + notes)
- 10 chapters: ~3000 tokens total
- Model: "cheap" tier (lower cost than writing)
- Parallelization: max 3 workers (ThreadPoolExecutor)

**Rolling context budget**:
- Keep only last `context_window_chapters` summaries
- Cap plot_events to 50 (prevents unbounded growth)
- Character states replaced per chapter (no accumulation)

---

**Architectural Principle**: Modular layers with clear handoffs. Each layer can be run independently or as part of full pipeline.

**Last Updated**: 2026-03-23 (Phase 5: Quality Metrics)
**Version**: 1.2
