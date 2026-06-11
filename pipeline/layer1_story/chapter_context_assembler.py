"""Per-chapter write-context assembly for the sequential batch path.

Extracted from batch_generator.py. Resolves everything the chapter writer
needs before prompting: the bible/tiered context string, active conflicts,
foreshadowing seeds/payoffs, validated pacing, and the arc context block.
Every resolution step is non-fatal — failures log a warning and fall back
to the empty defaults.
"""

import logging
from typing import NamedTuple

from models.schemas import ChapterOutline, StoryContext

logger = logging.getLogger(__name__)


class ChapterWriteContext(NamedTuple):
    """Resolved per-chapter context consumed by the chapter-writer calls."""

    bible_ctx: str
    active_conflicts: list
    seeds: list
    payoffs: list
    pacing: str
    arc_context: str


def assemble_chapter_write_context(
    config,
    *,
    bible_manager,
    draft,
    outline: ChapterOutline,
    batch: list[ChapterOutline],
    story_context: StoryContext,
    all_chapter_texts: list[str],
    macro_arcs,
    conflict_web,
    foreshadowing_plan,
) -> ChapterWriteContext:
    """Resolve bible/tiered context + narrative context for one chapter."""
    bible_ctx = ""
    if draft.story_bible:
        bible_ctx = bible_manager.get_context_for_chapter(
            draft.story_bible,
            outline.chapter_number,
            recent_summaries=list(story_context.recent_summaries),
            character_states=list(story_context.character_states),
        )

    # Tiered context: replaces flat bible_ctx with priority-based 4-tier system
    if getattr(config.pipeline, "enable_tiered_context", False):
        try:
            from pipeline.layer1_story.tiered_context_builder import (
                build_tiered_context,
                build_compressed_context,
                should_use_compressed_context,
            )

            # Emotional bridge: pass prev_chapter if enabled
            prev_ch = None
            if getattr(config.pipeline, "enable_emotional_bridge", False):
                prev_ch = draft.chapters[-1] if draft.chapters else None

            # Use compressed context for long stories (20+ chapters)
            total_chs = len(draft.chapters) + len(
                [o for o in batch if o.chapter_number > len(draft.chapters)]
            )
            if should_use_compressed_context(total_chs, threshold=20):
                tiered = build_compressed_context(
                    chapter_num=outline.chapter_number,
                    chapters=draft.chapters,
                    outline=outline,
                    macro_arcs=macro_arcs,
                    open_threads=list(story_context.open_threads),
                    story_bible=draft.story_bible,
                    all_chapter_texts=all_chapter_texts,
                    max_tokens=getattr(
                        config.pipeline, "tiered_context_max_tokens", 4000
                    ),
                    prev_chapter=prev_ch,
                )
            else:
                tiered = build_tiered_context(
                    chapter_num=outline.chapter_number,
                    chapters=draft.chapters,
                    outline=outline,
                    open_threads=list(story_context.open_threads),
                    story_bible=draft.story_bible,
                    all_chapter_texts=all_chapter_texts,
                    max_tokens=getattr(
                        config.pipeline, "tiered_context_max_tokens", 3000
                    ),
                    max_promotions=getattr(config.pipeline, "tiered_max_promotions", 5),
                    prev_chapter=prev_ch,
                )
            if tiered:
                bible_ctx = tiered
        except Exception as e:
            logger.warning(
                "Tiered context failed for ch%d (using bible fallback): %s",
                outline.chapter_number,
                e,
            )

    # Resolve per-chapter narrative context
    active_conflicts = []
    seeds = []
    payoffs = []
    pacing = ""
    current_arc = None
    try:
        from pipeline.layer1_story.macro_outline_builder import (
            get_arc_for_chapter,
        )
        from pipeline.layer1_story.conflict_web_builder import (
            get_active_conflicts,
        )
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
            "Narrative context resolution failed for ch%d: %s",
            outline.chapter_number,
            e,
        )

    # Build arc context string for chapter writing prompt (Fix #11)
    arc_context = ""
    if current_arc:
        arc_context = (
            f"Arc {current_arc.arc_number}: {current_arc.name}\n"
            f"Xung đột trung tâm: {current_arc.central_conflict}\n"
            f"Nhân vật trọng tâm: {', '.join(current_arc.character_focus) if current_arc.character_focus else 'tất cả'}\n"
            f"Kết thúc arc: {current_arc.resolution}\n"
            f"Cung bậc cảm xúc: {current_arc.emotional_trajectory}"
        )

    return ChapterWriteContext(
        bible_ctx=bible_ctx,
        active_conflicts=active_conflicts,
        seeds=seeds,
        payoffs=payoffs,
        pacing=pacing,
        arc_context=arc_context,
    )
