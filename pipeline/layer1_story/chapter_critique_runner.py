"""Chapter self-critique pass (Enhancement 6) for the sequential batch path.

Extracted from batch_generator.py. Critiques the freshly written chapter,
rewrites weak sections, and optionally rolls back the rewrite if the
re-scored aggregate drops (L1-B). Mutates chapter.content/word_count in
place. Non-fatal: failures are logged and the current content is kept.
"""

import logging
from typing import Callable

from models.schemas import Chapter, ChapterOutline, StoryContext

logger = logging.getLogger(__name__)


def run_chapter_self_critique(
    pipeline_config,
    llm,
    *,
    chapter: Chapter,
    outline: ChapterOutline,
    characters: list,
    genre: str,
    pacing: str,
    macro_arcs,
    story_context: StoryContext,
    draft,
    layer_model: str | None,
    progress_callback: Callable | None = None,
) -> None:
    """Critique + selective rewrite of one chapter, with optional rollback.

    Gated by pipeline_config.enable_chapter_critique. should_critique decides
    eligibility (climax/twist chapters or every-N cadence).
    """
    if not pipeline_config.enable_chapter_critique:
        return
    try:
        from pipeline.layer1_story.chapter_self_critique import (
            critique_chapter,
            rewrite_weak_sections,
            should_critique,
            aggregate_critique_score,
        )

        every_n = int(
            getattr(pipeline_config, "chapter_critique_every_n_chapters", 0) or 0
        )
        if should_critique(
            outline.chapter_number,
            story_context.total_chapters,
            macro_arcs=macro_arcs,
            pacing_type=pacing,
            every_n_chapters=every_n,
        ):
            outline_text = f"{outline.title}: {outline.summary}"
            crit = critique_chapter(
                llm,
                chapter.content,
                outline_text,
                characters,
                genre,
                pacing,
                model=layer_model,
            )
            if crit:
                original_content = chapter.content
                score_before = aggregate_critique_score(crit)
                revised = rewrite_weak_sections(
                    llm,
                    chapter.content,
                    crit,
                    model=layer_model,
                    idea=getattr(draft, "original_idea", "") or "",
                    idea_summary=getattr(draft, "idea_summary_for_chapters", "") or "",
                )
                if revised != original_content:
                    from models.schemas import count_words

                    chapter.content = revised
                    chapter.word_count = count_words(revised)
                    # L1-B rollback: re-score revised; revert if aggregate drops.
                    if getattr(pipeline_config, "chapter_critique_rollback", False):
                        try:
                            crit_after = critique_chapter(
                                llm,
                                revised,
                                outline_text,
                                characters,
                                genre,
                                pacing,
                                model=layer_model,
                            )
                            score_after = (
                                aggregate_critique_score(crit_after)
                                if crit_after
                                else score_before
                            )
                            threshold = float(
                                getattr(
                                    pipeline_config,
                                    "chapter_critique_rollback_threshold",
                                    0.3,
                                )
                            )
                            if score_after + threshold < score_before:
                                chapter.content = original_content
                                chapter.word_count = count_words(original_content)
                                if progress_callback:
                                    progress_callback(
                                        f"⚠️ Ch{outline.chapter_number} rollback self-critique "
                                        f"({score_before:.2f} → {score_after:.2f})"
                                    )
                                logger.info(
                                    "Ch%d critique rollback: %.2f → %.2f",
                                    outline.chapter_number,
                                    score_before,
                                    score_after,
                                )
                            elif progress_callback:
                                progress_callback(
                                    f"Chương {outline.chapter_number} cải thiện "
                                    f"({score_before:.2f} → {score_after:.2f})"
                                )
                        except Exception as e:
                            logger.debug(
                                "Rollback rescore failed (keeping revised): %s",
                                e,
                            )
                    elif progress_callback:
                        progress_callback(
                            f"Chương {outline.chapter_number} đã cải thiện qua self-critique"
                        )
    except Exception as e:
        logger.warning(
            "Chapter self-critique failed for ch%d (non-fatal): %s",
            outline.chapter_number,
            e,
        )
