"""Per-chapter input assembly for the parallel/async/threaded write paths.

Extracted from batch_generator.py (_write_chapter_parallel). Resolves the
bible/tiered context (with sibling-outline injection), a frozen StoryContext
snapshot, the narrative context (conflicts, seeds, payoffs, pacing, arc),
and the per-chapter enhancement string (scene decomposition + scene beats
appended to the shared enhancement). Every resolution step is non-fatal —
failures log a warning and fall back to the empty defaults.
"""

import logging
from typing import NamedTuple

from models.schemas import ChapterOutline, StoryContext

logger = logging.getLogger(__name__)


class ParallelWriteInputs(NamedTuple):
    """Resolved inputs consumed by the parallel chapter-writer call."""

    bible_ctx: str
    frozen_ctx: StoryContext
    active_conflicts: list
    seeds: list
    payoffs: list
    pacing: str
    arc_context: str
    enhancement: str


def assemble_parallel_write_inputs(
    gen,
    config,
    llm,
    *,
    outline: ChapterOutline,
    frozen,
    draft,
    story_context: StoryContext,
    frozen_threads: list,
    sibling_summaries: str,
    shared_enhancement: str,
    characters: list,
    world,
    genre: str,
    macro_arcs,
    conflict_web,
    foreshadowing_plan,
) -> ParallelWriteInputs:
    """Assemble all per-chapter inputs for one parallel chapter write."""
    bible_ctx = ""
    if draft.story_bible:
        bible_ctx = gen.bible_manager.get_context_for_chapter(
            draft.story_bible,
            outline.chapter_number,
            recent_summaries=frozen.recent_summaries,
            character_states=frozen.character_states,
        )
    if sibling_summaries:
        bible_ctx = (
            f"{bible_ctx}\n\n[Sibling outlines in this batch]\n{sibling_summaries}"
            if bible_ctx
            else f"[Sibling outlines in this batch]\n{sibling_summaries}"
        )

    # Tiered context
    if getattr(config.pipeline, "enable_tiered_context", False):
        try:
            from pipeline.layer1_story.tiered_context_builder import (
                build_tiered_context,
            )

            tiered = build_tiered_context(
                chapter_num=outline.chapter_number,
                chapters=list(draft.chapters),
                outline=outline,
                open_threads=frozen_threads,
                story_bible=draft.story_bible,
                all_chapter_texts=list(frozen.chapter_texts),
                max_tokens=getattr(config.pipeline, "tiered_context_max_tokens", 3000),
                max_promotions=getattr(config.pipeline, "tiered_max_promotions", 5),
            )
            if tiered:
                bible_ctx = tiered
        except Exception as e:
            logger.warning(
                "Tiered context failed for ch%d: %s", outline.chapter_number, e
            )

    frozen_ctx = StoryContext(total_chapters=story_context.total_chapters)
    frozen_ctx.current_chapter = outline.chapter_number
    frozen_ctx.recent_summaries = list(frozen.recent_summaries)
    frozen_ctx.character_states = list(frozen.character_states)
    frozen_ctx.plot_events = list(frozen.plot_events)

    # Resolve narrative context
    active_conflicts, seeds, payoffs, pacing, current_arc = [], [], [], "", None
    try:
        from pipeline.layer1_story.macro_outline_builder import get_arc_for_chapter
        from pipeline.layer1_story.conflict_web_builder import get_active_conflicts
        from pipeline.layer1_story.foreshadowing_manager import (
            get_seeds_to_plant,
            get_payoffs_due,
        )
        from pipeline.layer1_story.pacing_controller import validate_pacing

        current_arc = get_arc_for_chapter(macro_arcs or [], outline.chapter_number)
        arc_num = current_arc.arc_number if current_arc else 1
        active_conflicts = get_active_conflicts(conflict_web or [], arc_num)
        seeds = get_seeds_to_plant(foreshadowing_plan or [], outline.chapter_number)
        payoffs = get_payoffs_due(foreshadowing_plan or [], outline.chapter_number)
        pacing = validate_pacing(getattr(outline, "pacing_type", "") or "")
    except Exception as e:
        logger.warning(
            "Narrative context failed for ch%d: %s", outline.chapter_number, e
        )

    arc_context = ""
    if current_arc:
        arc_context = (
            f"Arc {current_arc.arc_number}: {current_arc.name}\n"
            f"Xung đột trung tâm: {current_arc.central_conflict}\n"
            f"Nhân vật trọng tâm: {', '.join(current_arc.character_focus) if current_arc.character_focus else 'tất cả'}\n"
            f"Kết thúc arc: {current_arc.resolution}\n"
            f"Cung bậc cảm xúc: {current_arc.emotional_trajectory}"
        )

    per_chapter_enhancement = shared_enhancement
    if config.pipeline.enable_scene_decomposition:
        try:
            from pipeline.layer1_story.scene_decomposer import (
                decompose_chapter_scenes,
                format_scenes_for_prompt,
                should_decompose,
            )

            if should_decompose(outline.chapter_number, pacing):
                scenes = decompose_chapter_scenes(
                    llm,
                    outline,
                    characters,
                    world,
                    genre,
                    model=gen._layer_model,
                )
                st = format_scenes_for_prompt(scenes)
                if st:
                    per_chapter_enhancement = f"{shared_enhancement}\n\n{st}".strip()
        except Exception:
            pass

    # Scene beats
    from pipeline.layer1_story.scene_beat_generator import generate_scene_beats

    scene_beats = generate_scene_beats(
        llm,
        outline,
        characters,
        world,
        genre,
        model_tier=gen._layer_model or "cheap",
    )
    if scene_beats:
        per_chapter_enhancement += scene_beats

    return ParallelWriteInputs(
        bible_ctx=bible_ctx,
        frozen_ctx=frozen_ctx,
        active_conflicts=active_conflicts,
        seeds=seeds,
        payoffs=payoffs,
        pacing=pacing,
        arc_context=arc_context,
        enhancement=per_chapter_enhancement,
    )
