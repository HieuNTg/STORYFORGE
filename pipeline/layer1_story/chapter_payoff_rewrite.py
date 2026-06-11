"""Post-write rewrite pass: missing foreshadowing payoffs (L1-E).

Extracted from batch_generator.py. Mutates chapter content in place and
re-verifies payoffs against the rewritten text. Non-fatal on failure.
"""

import logging
from typing import Callable

from models.schemas import Chapter, ChapterOutline, StoryContext

logger = logging.getLogger(__name__)


def _verify_and_rewrite_missing_payoffs(
    pipeline_config,
    llm,
    chapter: Chapter,
    outline: ChapterOutline,
    story_context: StoryContext,
    foreshadowing_plan: list | None,
    layer_model: str | None,
    progress_callback: Callable | None = None,
    draft=None,
) -> None:
    """L1-E: Targeted rewrite when post_processing flagged missing payoffs.

    Mutates chapter.content + story_context.foreshadowing_payoff_missing in place.
    Gated by pipeline_config.foreshadowing_payoff_rewrite_on_miss.
    """
    if not getattr(pipeline_config, "foreshadowing_payoff_rewrite_on_miss", False):
        return
    if not story_context.foreshadowing_payoff_missing:
        return

    try:
        from pipeline.layer1_story.chapter_self_critique import (
            rewrite_for_missing_payoffs,
        )
        from pipeline.layer1_story.foreshadowing_manager import get_payoffs_due
        from pipeline.semantic.foreshadowing_verifier import verify_payoffs
        from models.schemas import count_words

        missing = list(story_context.foreshadowing_payoff_missing)
        if progress_callback:
            progress_callback(
                f"Ch{outline.chapter_number}: viết lại để thực hiện {len(missing)} payoff..."
            )
        _idea = getattr(draft, "original_idea", "") or "" if draft is not None else ""
        _idea_sum = (
            getattr(draft, "idea_summary_for_chapters", "") or ""
            if draft is not None
            else ""
        )
        revised = rewrite_for_missing_payoffs(
            llm,
            chapter.content,
            missing,
            model=layer_model,
            idea=_idea,
            idea_summary=_idea_sum,
        )
        if not revised or revised == chapter.content:
            return

        chapter.content = revised
        chapter.word_count = count_words(revised)

        # Re-verify against rewritten content (embedding-based, no LLM call)
        due_after = get_payoffs_due(foreshadowing_plan or [], outline.chapter_number)
        if due_after:
            threshold = float(
                getattr(pipeline_config, "semantic_payoff_threshold", 0.55)
            )
            verify_payoffs(due_after, [chapter], threshold=threshold)
            still_missing = [p for p in due_after if not p.paid_off]
            story_context.foreshadowing_payoff_missing = [
                {
                    "hint": p.hint,
                    "confidence": p.planted_confidence or 0.0,
                    "payoff_chapter": p.payoff_chapter,
                    "plant_chapter": p.plant_chapter,
                }
                for p in still_missing
            ]
            if still_missing and progress_callback:
                progress_callback(
                    f"⚠️ Ch{outline.chapter_number}: {len(still_missing)} payoff "
                    f"vẫn chưa đạt ngưỡng sau rewrite"
                )
    except Exception as e:
        logger.warning(
            "Payoff rewrite failed for ch%d (non-fatal): %s",
            outline.chapter_number,
            e,
        )
