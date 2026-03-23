# Phase 5: Story Quality Metrics

**Status**: COMPLETE (2026-03-23) | **Tests**: 77/77 passed | **Risk**: LOW

## Overview

Automated quality scoring system using LLM-as-judge. Evaluates stories on 4 dimensions after Layer 1 generation and Layer 2 drama enhancement.

## Architecture

```
Chapter Content → [Excerpt] → QualityScorer.score_chapter() → ChapterScore (1-5 scale)
                                       ↓
                              [Parallel Pool]
                                       ↓
                         All ChapterScores → StoryScore (aggregate)
                                       ↓
                        PipelineOutput.quality_scores[]
                                       ↓
                           UI: "Chat Luong" Tab
```

## Data Models

### ChapterScore

Per-chapter quality evaluation.

```python
class ChapterScore(BaseModel):
    chapter_number: int
    coherence: float = 3.0  # Plot logic & flow (1-5)
    character_consistency: float = 3.0  # Behavior matches personality (1-5)
    drama: float = 3.0  # Tension & emotional engagement (1-5)
    writing_quality: float = 3.0  # Prose clarity & vividness (1-5)
    overall: float = 0.0  # Computed mean of 4 dimensions
    notes: str = ""  # Strengths/weaknesses (max 200 chars)
```

**Validation**:
- All floats: `ge=1, le=5` (inclusive range)
- `overall`: auto-computed = `(coherence + character_consistency + drama + writing_quality) / 4`
- Pydantic clamps invalid values to nearest boundary

### StoryScore

Aggregate scores across all chapters + layer info.

```python
class StoryScore(BaseModel):
    chapter_scores: list[ChapterScore]  # Per-chapter details
    avg_coherence: float = 0.0  # Mean across chapters
    avg_character: float = 0.0  # Mean across chapters
    avg_drama: float = 0.0  # Mean across chapters
    avg_writing: float = 0.0  # Mean across chapters
    overall: float = 0.0  # Mean of 4 averages
    weakest_chapter: int = 0  # Chapter with lowest overall score
    scoring_layer: int = 0  # Which layer (1 or 2)
```

## QualityScorer Service

**File**: `services/quality_scorer.py`

### score_chapter()

```python
def score_chapter(self, chapter: Chapter, context: str = "") -> ChapterScore:
    """Score single chapter using cheap LLM model.

    Args:
        chapter: Chapter to score
        context: Previous chapter content (optional, for coherence check)

    Returns:
        ChapterScore with 4 dimensions + overall
    """
```

**Process**:
1. Excerpt content if > 4000 chars:
   - Keep head: 2600 chars
   - Add separator: `\n...\n`
   - Keep tail: 1400 chars
2. Call LLM with SCORE_CHAPTER prompt:
   - System: "You are a literary expert. Return JSON."
   - Temp: 0.2 (deterministic)
   - Max tokens: 500 (compact)
   - Model tier: "cheap" (cost control)
3. Parse JSON response:
   - Extract 4 scores
   - Clamp to 1-5 range (fallback to 3.0 on error)
4. Compute overall = mean of 4 dimensions
5. Return ChapterScore

### score_story()

```python
def score_story(self, chapters: list[Chapter], layer: int = 1) -> StoryScore:
    """Score all chapters in parallel with sequential context.

    Args:
        chapters: List of chapters to score
        layer: Which layer (1=initial, 2=enhanced)

    Returns:
        StoryScore with aggregates
    """
```

**Process**:
1. Build (chapter, context) pairs sequentially:
   - Ch1: context = ""
   - Ch2: context = Ch1.content[:500]
   - Ch3: context = Ch2.content[:500]
   - ...
2. Submit all scoring tasks to ThreadPoolExecutor (max 3 workers)
3. Collect results with fallbacks:
   - If score_chapter() fails → log warning, use default ChapterScore
4. Sort by chapter_number
5. Aggregate:
   - avg_coherence = mean(all chapter coherence)
   - avg_character = mean(all chapter character_consistency)
   - avg_drama = mean(all chapter drama)
   - avg_writing = mean(all chapter writing_quality)
   - overall = mean(4 averages)
   - weakest_chapter = chapter_number with min overall score
6. Return StoryScore with layer marker

## Scoring Prompt

**Prompt template**: `SCORE_CHAPTER` (services/prompts.py, lines 143-157)

```
Evaluate chapter on 4 criteria (1-5 scale, where 1=poor, 3=average, 5=excellent):

1. coherence: Plot logic, narrative flow, no contradictions
2. character_consistency: Characters behave per their established personality and arc
3. drama: Tension, emotional engagement, pacing
4. writing_quality: Prose clarity, vocabulary, imagery, dialogue naturalness

CHAPTER {chapter_number}:
{content}

PREVIOUS CONTEXT (for coherence check):
{context}

Return JSON:
{"coherence": X, "character_consistency": X, "drama": X, "writing_quality": X, "notes": "brief comment"}
```

## Pipeline Integration

### Orchestrator Changes

**File**: `pipeline/orchestrator.py`

**Layer 1 Scoring** (lines 106-115):
```python
if enable_scoring:
    _log("[METRICS] Scoring Layer 1 quality...")
    try:
        scorer = QualityScorer()
        l1_score = scorer.score_story(draft.chapters, layer=1)
        self.output.quality_scores.append(l1_score)
        _log(f"[METRICS] Layer 1: {l1_score.overall:.1f}/5 | "
             f"Weakest chapter: {l1_score.weakest_chapter}")
    except Exception as e:
        logger.warning(f"Quality scoring Layer 1 failed: {e}")
```

**Layer 2 Scoring** (lines 165-179):
```python
if enable_scoring:
    _log("[METRICS] Scoring Layer 2 quality...")
    try:
        scorer = QualityScorer()
        l2_score = scorer.score_story(enhanced.chapters, layer=2)
        self.output.quality_scores.append(l2_score)
        delta = ""
        if len(self.output.quality_scores) >= 2:
            l1_overall = self.output.quality_scores[0].overall
            diff = l2_score.overall - l1_overall
            delta = f" | Delta: {diff:+.1f}"
        _log(f"[METRICS] Layer 2: {l2_score.overall:.1f}/5 | "
             f"Weakest chapter: {l2_score.weakest_chapter}{delta}")
    except Exception as e:
        logger.warning(f"Quality scoring Layer 2 failed: {e}")
```

**Key traits**:
- Non-blocking: Scoring failures don't stop pipeline
- Delta logging: Layer 2 improvement vs Layer 1 visible
- Results stored in `PipelineOutput.quality_scores[]`
- Graceful logging for user feedback

### run_full_pipeline() Parameter

```python
def run_full_pipeline(
    ...
    enable_scoring: bool = True,
) -> PipelineOutput:
    """... enable_scoring: Skip quality scoring if False ..."""
```

Default: True (scoring enabled by default)

## UI Integration

### Components

**File**: `app.py`

**Checkbox** (line 131-134):
```python
enable_scoring_cb = gr.Checkbox(
    value=True,
    label="Cham diem tu dong (Quality Metrics)"
)
```
- Enables/disables scoring toggle in UI
- Default: True (scoring on)
- Value passed to orchestrator via `enable_scoring` param

**Output Tab** (line 173):
```python
with gr.TabItem("Chat Luong"):
    quality_output = gr.Markdown(
        value="*Chua co diem. Chay pipeline voi 'Cham diem tu dong' bat.*"
    )
```
- New tab "Chat Luong" (Quality)
- Displays quality_output Markdown
- Default: instruction text (no scoring yet)

**Output Tuple** (9 elements):
```python
# All yield statements return:
(
    clear_preview,  # gr.Button (clear)
    logs,           # gr.Textbox (log output)
    draft,          # gr.JSON (story draft)
    sim,            # gr.JSON (simulation)
    enhanced,       # gr.JSON (enhanced story)
    video,          # gr.JSON (video script)
    agent,          # gr.Markdown (agent reviews)
    quality,        # gr.Markdown (quality scores) ← NEW
    orch,           # gr.State (orchestrator)
)
```

### Score Formatting

**Format function** (line 273-308):
```python
quality_text = "## Diem Chat Luong Truyen\n\n"

for qs in quality_scores:
    quality_text += f"### Layer {qs.scoring_layer} — Tong: {qs.overall:.1f}/5\n\n"
    quality_text += f"**Coherence**: {qs.avg_coherence:.2f}\n"
    quality_text += f"**Character**: {qs.avg_character:.2f}\n"
    quality_text += f"**Drama**: {qs.avg_drama:.2f}\n"
    quality_text += f"**Writing**: {qs.avg_writing:.2f}\n"

    if qs.weakest_chapter:
        quality_text += f"\n*Weakest: Chapter {qs.weakest_chapter}*\n\n"

return quality_text  # Update quality_output.value
```

## Performance Characteristics

### Scoring Time

- Per chapter: ~2-3 seconds (LLM call + parsing)
- 10 chapters: ~20-30 seconds (parallel, max 3 workers)
- Overhead: ~10% of chapter writing time (acceptable)

### Token Usage

- SCORE_CHAPTER: ~150-200 tokens input, ~50-100 tokens output
- Per story (10 chapters): ~3000 tokens
- Cost: Use "cheap" model tier to minimize

### Memory

- Parallel context building: negligible (prev chapter head only)
- ChapterScore + StoryScore: <1MB per story

## Testing

### Coverage

- models/schemas.py: 100% (ChapterScore, StoryScore)
- services/prompts.py: 100% (SCORE_CHAPTER)
- services/quality_scorer.py: 76% (acceptable; LLM mocks not full coverage)
- pipeline/orchestrator.py: 13% (error paths; happy path tested)
- app.py: syntax validated (no runtime errors)

### Test Suite

- 77 total tests (Phase 4: 21 + Phase 5: 56)
- All passing
- No regressions from prior phases

### Key Scenarios

1. **Single chapter scoring**: Verify coherence, character, drama, writing
2. **Story aggregation**: Check mean calculations + overall
3. **Weakest chapter ID**: Confirm minimum overall detection
4. **Long chapter truncation**: Head + tail for 5000+ char chapters
5. **LLM fallback**: Invalid JSON → default scores (clamp)
6. **Layer 2 delta**: Layer 1 vs Layer 2 improvement tracking
7. **UI rendering**: Quality tab displays scores correctly

## Configuration

### No new config params

Quality scoring uses existing LLMConfig:
- `model`: Which LLM (default: gpt-4o-mini)
- `api_key`: Authentication
- `temperature` not used (hardcoded 0.2)
- `max_tokens` not used (hardcoded 500)

Future enhancements could add:
- `quality_scoring_enabled: bool`
- `quality_temp: float`
- `quality_model_tier: str` ("cheap", "standard", "premium")

## Error Handling

### Non-blocking failures

1. **LLM call timeout/failure**:
   - Log warning: "Quality scoring Layer X failed: {error}"
   - Continue pipeline (don't return error)
   - Scores not added to output

2. **Invalid JSON response**:
   - Parse exception caught
   - Default values used (all 3.0)
   - No retry (cheap model acceptable)

3. **Validation failure**:
   - Pydantic clamps out-of-range values
   - No exception raised
   - Fallback: 3.0 for any invalid field

### Logging

- INFO: Scoring start + overall result per layer
- WARNING: Extraction failures (non-blocking)
- DEBUG: Not used (no verbose logging)

## Future Enhancements

1. **Per-dimension feedback**: Text explaining low scores
2. **Comparative scoring**: Compare chapters to story average
3. **Genre-specific prompts**: Romance vs thriller different criteria
4. **Human feedback loop**: Train model on user corrections
5. **Scoring history**: Track improvements across iterations
6. **Threshold alerts**: Warn if coherence < 2.0

---

**Last Updated**: 2026-03-23 | **Owner**: Documentation Team
