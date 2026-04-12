---
phase: 5
title: "Integration & Orchestrator Wiring"
status: completed
effort: 2h
depends_on: [1, 2, 3, 4]
---

# Phase 5: Integration & Orchestrator Wiring

## Context Links
- Plan: [plan.md](plan.md)
- Phases 1-4: all prior phases
- Orchestrator: `pipeline/orchestrator_layers.py` (lines 228-425)
- Quality scorer: `services/quality_scorer.py`
- Prompts init: `services/prompts/__init__.py`

## Overview
Wire all 7 enhancements into the orchestrator pipeline. Update quality scoring to include new dimensions (psychology depth, knowledge asymmetry, causal coherence, thematic alignment). Ensure graceful degradation.

## Key Insights
- Orchestrator L2 section (lines 228-425) calls: analyzer.analyze -> simulator.run_simulation -> enhancer.enhance_with_feedback
- Most wiring is already done in Phases 1-4 at the module level (simulator auto-uses psychology, knowledge, adaptive; enhancer auto-uses scenes, subtext, themes)
- This phase focuses on: passing new data through orchestrator, updating scoring, logging new metrics, end-to-end validation

## Requirements
1. Orchestrator passes new data (psychology profiles, theme profile) between L2 components
2. Quality scoring includes new dimensions
3. Analytics includes new L2 metrics (actual_rounds, knowledge_revelations, causal_chain_depth)
4. Progress callbacks report new enhancement stages
5. All new features degrade gracefully on failure

## Architecture

### Modified: `pipeline/orchestrator_layers.py` (lines 228-270)

```python
# After analyzer.analyze (line 235):
theme_profile = None
try:
    from pipeline.layer2_enhance.thematic_tracker import ThematicTracker
    tracker = ThematicTracker()
    theme_profile = await asyncio.to_thread(tracker.extract_theme, draft)
    _log(f"[L2] Theme: {theme_profile.central_theme}")
except Exception as e:
    logger.warning(f"Theme extraction failed (non-fatal): {e}")

# Pass theme_profile to enhancer:
enhanced = await asyncio.to_thread(
    self.enhancer.enhance_with_feedback,
    draft=draft, sim_result=sim_result,
    word_count=word_count,
    progress_callback=lambda m: _log(f"[L2] {m}"),
    theme_profile=theme_profile,  # NEW
)
```

### Modified: `services/quality_scorer.py`

Add optional scoring dimensions (non-breaking):
```python
# In score_chapter(), add to prompt:
# "6. thematic_alignment: Chương có củng cố chủ đề trung tâm không? (1-5)"
# "7. dialogue_depth: Đối thoại có chiều sâu (nói vs ý nghĩa) không? (1-5)"
```

### Modified: `pipeline/layer2_enhance/enhancer.py`

```python
# enhance_with_feedback and enhance_story: accept optional theme_profile parameter
def enhance_story(self, draft, sim_result, word_count=2000,
                  progress_callback=None, theme_profile=None):
    # Store theme_profile for use in enhance_chapter
    self._theme_profile = theme_profile
    ...

def enhance_chapter(self, chapter, sim_result, word_count=2000,
                    total_chapters=1, genre="", draft=None):
    # If self._theme_profile exists, generate thematic guidance
    ...
```

## Related Code Files
- `pipeline/orchestrator_layers.py` — L2 section (lines 228-425)
- `pipeline/layer2_enhance/enhancer.py` — enhance_story, enhance_chapter, enhance_with_feedback
- `services/quality_scorer.py` — score_chapter, score_story
- `services/story_analytics.py` — analyze_story
- `services/prompts/__init__.py` — prompt exports

## Implementation Steps

1. **Update `services/prompts/__init__.py`**:
   - Add import block for layer2_enhanced_prompts.py:
     ```python
     from services.prompts.layer2_enhanced_prompts import (
         EXTRACT_PSYCHOLOGY, KNOWLEDGE_AWARE_AGENT,
         DIALOGUE_SUBTEXT_GUIDANCE, EXTRACT_THEME,
         SCORE_CHAPTER_THEME, DECOMPOSE_CHAPTER_CONTENT,
     )
     ```
   - Add to `__all__` list

2. **Modify `enhancer.py` signatures**:
   - `enhance_story()`: add `theme_profile=None` parameter, store as `self._theme_profile`
   - `enhance_with_feedback()`: add `theme_profile=None`, pass through to `enhance_story()`
   - `enhance_chapter()`: if `self._theme_profile` exists, call thematic scoring and inject guidance into enhance prompt (add section before YEU CAU block)

3. **Modify `orchestrator_layers.py`** (lines 234-263):
   - After `analysis = await asyncio.to_thread(self.analyzer.analyze, draft)` (line 235):
     ```python
     # Extract theme for L2 enhancement (non-fatal)
     theme_profile = None
     try:
         from pipeline.layer2_enhance.thematic_tracker import ThematicTracker
         thematic = ThematicTracker()
         theme_profile = await asyncio.to_thread(thematic.extract_theme, draft)
         _log(f"[L2] Chủ đề: {theme_profile.central_theme}")
     except Exception as e:
         logger.warning(f"Theme extraction failed: {e}")
     ```
   - Pass `theme_profile=theme_profile` to `self.enhancer.enhance_with_feedback()` (line 258)
   - After simulation result (line 255), log new metrics:
     ```python
     if hasattr(sim_result, 'actual_rounds') and sim_result.actual_rounds:
         _log(f"[L2] Adaptive: {sim_result.actual_rounds} rounds (requested {num_sim_rounds})")
     if hasattr(sim_result, 'knowledge_state') and sim_result.knowledge_state:
         total_secrets = sum(len(v) for v in sim_result.knowledge_state.values())
         _log(f"[L2] Knowledge: {total_secrets} facts tracked across {len(sim_result.knowledge_state)} characters")
     ```

4. **Update analytics** in orchestrator (lines 354-362):
   - After existing analytics, add L2-specific metrics:
     ```python
     if sim_result:
         analytics["layer2"]["actual_rounds"] = getattr(sim_result, "actual_rounds", 0)
         analytics["layer2"]["causal_chains"] = len(getattr(sim_result, "causal_chains", []))
     if theme_profile:
         analytics["layer2"]["theme"] = theme_profile.central_theme
     ```

5. **Update quality scoring prompt** (if `services/quality_scorer.py` uses a prompt):
   - Add optional dimensions to chapter scoring: `thematic_alignment` and `dialogue_depth`
   - These are additive — existing 4 dimensions unchanged, new ones only used when data available
   - Add to `ChapterScore` schema in `models/schemas.py`:
     ```python
     thematic_alignment: float = Field(default=0.0, ge=0, le=5, description="Theme reinforcement score")
     dialogue_depth: float = Field(default=0.0, ge=0, le=5, description="Dialogue subtext depth score")
     ```

6. **End-to-end validation checklist** (manual):
   - Run pipeline with a short story (2-3 chapters)
   - Verify: psychology extracted for each character in logs
   - Verify: knowledge filtering visible in agent posts (some posts filtered)
   - Verify: adaptive rounds logged (may differ from requested)
   - Verify: scene-level enhancement logged for at least one chapter
   - Verify: thematic guidance appears in enhancement logs
   - Verify: pipeline completes even if all new modules fail (graceful degradation)

7. **Update `pipeline/layer2_enhance/__init__.py`** (if it exists):
   - Export new module classes for convenience

## Todo
- [ ] Update prompts/__init__.py with new imports
- [ ] Add theme_profile parameter to enhancer.enhance_story and enhance_with_feedback
- [ ] Wire thematic guidance into enhance_chapter prompt
- [ ] Add theme extraction call in orchestrator_layers.py
- [ ] Pass theme_profile to enhancer in orchestrator
- [ ] Log new L2 metrics (adaptive rounds, knowledge, causal chains, theme)
- [ ] Add analytics fields for new L2 data
- [ ] Add thematic_alignment, dialogue_depth to ChapterScore schema
- [ ] Update quality scoring prompt with new optional dimensions
- [ ] Manual end-to-end validation

## Success Criteria
- Full pipeline runs with all 7 enhancements active
- Progress logs show: psychology extraction, knowledge tracking, adaptive rounds, scene-level enhancement, thematic guidance
- Quality scores include new dimensions when available
- Pipeline completes successfully even when individual enhancements fail
- No regression in existing pipeline behavior

## Risk Assessment
- **Breaking changes**: Mitigated by optional parameters with defaults, try-except wrappers
- **Orchestrator complexity**: Adding ~30 lines to orchestrator. Mitigated: all in try-except blocks
- **Quality scoring backward compatibility**: New dimensions default to 0, existing scoring unchanged

## Security Considerations
- No new external APIs or credentials
- No changes to user-facing endpoints
- All new data stays within pipeline

## Next Steps
After Phase 5, all 7 enhancements are live. Monitor logs for failures, tune thresholds based on real story output quality.
