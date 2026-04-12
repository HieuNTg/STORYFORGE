# Research: L2 Enhancer, Prompts & Services

## 1. `pipeline/layer2_enhance/enhancer.py` — StoryEnhancer

### Key Classes/Functions
- **`StoryEnhancer`** (L21) — main class, `LAYER = 2`
  - `__init__` (L26): creates `LLMClient`, resolves layer-2 model
  - `enhance_chapter` (L30-125): single chapter enhancement
  - `enhance_story` (L127-201): parallel enhancement of all chapters via `asyncio.gather` + `run_in_executor`
  - `_find_weak_chapters` (L203-227): uses `QUICK_DRAMA_CHECK` prompt, returns chapters with `drama_score < 0.6`
  - `enhance_with_feedback` (L229-313): orchestrates enhance → feedback loop → coherence validation

### Data Flow
- **In**: `StoryDraft` (chapters, characters, genre, foreshadowing_plan, conflict_web, macro_arcs), `SimulationResult` (events, drama_suggestions, updated_relationships)
- **Out**: `EnhancedStory` (chapters, drama_score 1-5, enhancement_notes, coherence_issues)

### Enhancement Pipeline
1. `enhance_story()` — parallel LLM calls per chapter using `ENHANCE_CHAPTER` prompt
2. `_find_weak_chapters()` — scores each chapter via `QUICK_DRAMA_CHECK`, threshold 0.6
3. Up to 2 re-enhance rounds on weak chapters using `REENHANCE_CHAPTER` prompt
4. `validate_coherence()` + `fix_coherence_issues()` for critical issues only

### Current Limitations
- **Chapter-level only**: no scene decomposition in L2; entire chapter content sent as blob (truncated to 6000 chars)
- **No dialogue subtext**: prompt asks for "đối thoại sắc bén" but no structured dialogue analysis or subtext injection
- **No thematic resonance**: `layer1_context` passes foreshadowing/conflict_web/macro_arcs as flat text, no thematic thread tracking
- **Weak feedback specificity**: `strong_points` hardcoded as placeholder string `"(sẽ được phân tích trong feedback round)"` on first pass (L103)
- **6000 char truncation**: long chapters lose tail content during enhancement
- **Drama score mapping**: raw 0-1 avg mapped to 1-5, no per-chapter scoring stored
- **No sensory/atmosphere enhancement**: no prompts for sensory details or atmosphere

---

## 2. `pipeline/layer2_enhance/coherence_validator.py`

### Key Functions
- **`validate_coherence`** (L16-67): LLM-based cross-chapter consistency check
  - Inputs: `EnhancedStory`, `StoryDraft` (for original characters/conflict_web)
  - Uses `COHERENCE_CHECK` prompt; returns `list[dict]` with `{type, chapter, description, severity}`
  - Checks: timeline, character behavior, plot threads, relationships
  - Uses `model_tier="cheap"`, temp=0.2
- **`fix_coherence_issues`** (L70-135): rewrites critical-severity chapters
  - Groups issues by chapter, uses `COHERENCE_FIX` prompt
  - Only fixes `severity == "critical"`, skips warnings

### Limitations
- **Summary-based**: uses `ch.summary or ch.content[:200]` — very lossy for multi-scene chapters
- **No scene-level coherence**: checks at chapter granularity only
- **No dialogue consistency**: doesn't track character voice/speech patterns
- **No thematic thread validation**: only checks timeline/character/plot_thread/relationship
- **Single-pass fix**: no verification after fix applied

---

## 3. `services/prompts/analysis_prompts.py` + `revision_prompts.py`

### Prompt Templates & Injected Variables

| Prompt | File | Variables Injected |
|---|---|---|
| `ANALYZE_STORY` | analysis L7 | title, genre, characters, synopsis |
| `AGENT_PERSONA` | analysis L32 | character_name, genre, personality, background, motivation, relationships, current_context, recent_posts |
| `EVALUATE_DRAMA` | analysis L61 | actions, relationships → returns events with drama_score, relationship_changes |
| `ENHANCE_CHAPTER` | analysis L94 | original_chapter, drama_events, suggestions, updated_relationships, genre_hints, strong_points, layer1_context, word_count, genre_style |
| `COHERENCE_CHECK` | analysis L129 | chapter_summaries, characters, relationships |
| `DRAMA_SUGGESTIONS` | analysis L165 | simulation_summary, story_summary |
| `QUICK_DRAMA_CHECK` | revision L17 | content → 5 criteria scores (0-1) + weak/strong points |
| `REENHANCE_CHAPTER` | revision L32 | chapter_content, weak_points, strong_points, genre_hints, word_count |
| `COHERENCE_FIX` | revision L122 | chapter_number, title, content, issues, fix_suggestion, word_count |
| `SMART_REVISE_CHAPTER` | revision L96 | chapter_number, title, content, issues, suggestions, genre, word_count |

### Prompt Gaps for Planned Enhancements
- **No scene-level prompts in L2**: `ENHANCE_CHAPTER` takes whole chapter, no scene structure
- **No dialogue subtext prompt**: no template analyzing/enriching dialogue layers
- **No thematic resonance prompt**: no template for tracking/weaving recurring motifs
- **No sensory/atmosphere prompt**: `ENHANCE_CHAPTER` mentions emotions but not sensory details
- **`QUICK_DRAMA_CHECK` criteria limited**: 5 criteria (conflict, dialogue, emotion, pacing, cliffhanger) — missing thematic resonance, subtext, atmosphere
- **`COHERENCE_CHECK` missing thematic validation**: only timeline/character/plot/relationship

---

## 4. `pipeline/layer1_story/scene_decomposer.py`

### Key Functions
- **`should_decompose`** (L66-74): always returns True (gated for future config)
- **`decompose_chapter_scenes`** (L77-138): LLM call → 3-5 scenes as `list[dict]`
  - Scene dict keys: `scene_number, location, pov_character, characters_present, goal, conflict, outcome, sensory_focus, emotional_beat`
  - Inputs: `ChapterOutline, list[Character], WorldSetting, genre`
  - Uses `generate_json`, clamps to max 5 scenes
- **`format_scenes_for_prompt`** (L141-169): converts scene list → text block for chapter-writing prompt injection

### Reuse Potential for L2
- Scene dict structure already has `sensory_focus` and `emotional_beat` — can extend for subtext/thematic fields
- `format_scenes_for_prompt` pattern reusable for L2 scene-level enhancement prompt injection
- `decompose_chapter_scenes` could be called on enhanced chapters to get scene boundaries before per-scene refinement
- Would need: `dialogue_subtext`, `thematic_motif`, `atmosphere` fields added to scene schema

---

## 5. Integration Map

```
StoryDraft + SimulationResult
        │
        ▼
  enhance_story() ──── ENHANCE_CHAPTER prompt ───► LLM (layer-2 model)
        │                                              │
        ▼                                              ▼
  _find_weak_chapters() ── QUICK_DRAMA_CHECK ──► LLM (cheap tier)
        │
        ▼ (up to 2 rounds)
  re-enhance weak ──── REENHANCE_CHAPTER ──────► LLM (layer-2 model)
        │
        ▼
  validate_coherence() ── COHERENCE_CHECK ─────► LLM (cheap tier)
        │
        ▼ (critical only)
  fix_coherence_issues() ── COHERENCE_FIX ─────► LLM (default model)
        │
        ▼
  EnhancedStory
```

## 6. Key Findings for Enhancement Work

1. **Scene decomposition gap**: L1 has scene decomposer but L2 enhances at chapter level only. Bridging this = biggest structural change.
2. **Prompt injection points**: `ENHANCE_CHAPTER` has `{genre_hints}` and `{layer1_context}` — natural extension points for thematic/subtext instructions.
3. **`QUICK_DRAMA_CHECK` extensible**: add criteria for subtext_depth, thematic_resonance, sensory_atmosphere to evaluation.
4. **`strong_points` placeholder**: first-pass enhancement always sends placeholder string — wasted opportunity for preserving good content.
5. **Coherence validator only checks 4 dimensions**: needs thematic thread continuity added.
6. **`format_scenes_for_prompt` reusable**: pattern for injecting structured scene data into prompts already proven in L1.
7. **All prompts Vietnamese**: new prompts must follow same language convention.
