"""Per-chapter enhancement-context assembly for the sequential batch path.

Extracted from batch_generator.py. Builds the base enhancement context
(theme, voice, scenes, show-don't-tell) then appends the optional injection
blocks: mandatory threads, causal dependencies, emotional memories,
foreshadowing status, and payoff enforcement. Every injection is non-fatal —
a failure logs at debug level and the context built so far is kept.
"""

import logging
from typing import Callable

from models.schemas import ChapterOutline, StoryContext

logger = logging.getLogger(__name__)


def build_chapter_enhancement_context(
    config,
    llm,
    *,
    genre: str,
    pacing: str,
    premise,
    voice_profiles,
    outline: ChapterOutline,
    characters: list,
    world,
    story_context: StoryContext,
    foreshadowing_plan: list | None,
    layer_model: str | None,
    progress_callback: Callable | None = None,
) -> str:
    """Assemble the full enhancement context string for one chapter."""
    from pipeline.layer1_story.enhancement_context_builder import (
        build_enhancement_context,
    )

    enhancement_context = build_enhancement_context(
        config,
        llm,
        genre,
        pacing,
        premise=premise,
        voice_profiles=voice_profiles,
        outline=outline,
        characters=characters,
        world=world,
        layer_model=layer_model,
    )

    # Thread enforcement: inject mandatory threads as hard requirement
    if getattr(config.pipeline, "enable_thread_enforcement", False):
        try:
            from pipeline.layer1_story.plot_thread_tracker import (
                format_mandatory_threads,
            )

            mandatory = format_mandatory_threads(
                list(story_context.open_threads),
                outline.chapter_number,
                gap_threshold=8,
            )
            if mandatory:
                enhancement_context = (
                    f"{enhancement_context}\n\n{mandatory}"
                    if enhancement_context
                    else mandatory
                )
        except Exception as e:
            logger.debug("Thread enforcement failed (non-fatal): %s", e)

    # Causal dependencies injection
    if getattr(config.pipeline, "enable_l1_causal_graph", False):
        try:
            from pipeline.layer1_story.l1_causal_graph import (
                format_causal_dependencies_for_prompt,
            )

            causal_graph = getattr(story_context, "causal_graph", None)
            if causal_graph:
                required = causal_graph.query_required_references(
                    outline.chapter_number, min_age=2
                )
                causal_block = format_causal_dependencies_for_prompt(required)
                if causal_block:
                    enhancement_context = (
                        f"{enhancement_context}\n\n{causal_block}"
                        if enhancement_context
                        else causal_block
                    )
        except Exception as e:
            logger.debug("Causal dependencies injection failed (non-fatal): %s", e)

    # Emotional memory injection
    if getattr(config.pipeline, "enable_emotional_memory", False):
        try:
            from pipeline.layer1_story.character_memory_bank import (
                format_memories_for_prompt,
            )

            banks = getattr(story_context, "emotional_memory_banks", None) or {}
            if banks:
                memories_block = format_memories_for_prompt(banks, last_n=3)
                if memories_block and memories_block != "Không có ký ức cảm xúc.":
                    enhancement_context = f"{enhancement_context}\n\n## KÝ ỨC CẢM XÚC NHÂN VẬT:\n{memories_block}"
        except Exception as e:
            logger.debug("Emotional memory injection failed (non-fatal): %s", e)

    # Bug #5: Inject foreshadowing status summary
    if foreshadowing_plan:
        try:
            from pipeline.layer1_story.foreshadowing_manager import (
                get_foreshadowing_status,
            )

            foreshadowing_status = get_foreshadowing_status(
                foreshadowing_plan, outline.chapter_number
            )
            if foreshadowing_status:
                enhancement_context = (
                    f"{enhancement_context}\n\n{foreshadowing_status}"
                    if enhancement_context
                    else foreshadowing_status
                )
        except Exception as e:
            logger.debug("Foreshadowing status injection failed (non-fatal): %s", e)

    # Foreshadowing payoff enforcement (Phase 6)
    if foreshadowing_plan and getattr(
        config.pipeline, "enable_foreshadowing_enforcement", True
    ):
        try:
            from pipeline.layer1_story.foreshadowing_manager import (
                get_overdue_payoffs,
                get_approaching_payoffs,
                format_payoff_enforcement_prompt,
            )

            overdue = get_overdue_payoffs(
                foreshadowing_plan, outline.chapter_number, grace_chapters=2
            )
            approaching = get_approaching_payoffs(
                foreshadowing_plan, outline.chapter_number, lookahead=3
            )
            if overdue or approaching:
                payoff_block = format_payoff_enforcement_prompt(
                    overdue,
                    approaching,
                    outline.chapter_number,
                )
                if payoff_block:
                    enhancement_context = (
                        f"{enhancement_context}\n\n{payoff_block}"
                        if enhancement_context
                        else payoff_block
                    )
                    if overdue and progress_callback:
                        progress_callback(
                            f"⚠️ {len(overdue)} foreshadowing quá hạn cần payoff"
                        )
        except Exception as e:
            logger.debug("Foreshadowing payoff enforcement failed (non-fatal): %s", e)

    return enhancement_context
