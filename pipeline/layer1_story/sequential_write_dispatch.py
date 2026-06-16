"""Chapter-write dispatch for the sequential batch path.

Extracted verbatim from BatchChapterGenerator._run_batch_sequential. Picks
the write path for one chapter — a chapter already written per-beat, the
streaming writer, or the long-context writer — then attaches the contract
to the chapter and warns when the token budget is nearly spent.
"""

from __future__ import annotations

import logging

from models.schemas import Chapter
from services.token_counter import estimate_tokens

logger = logging.getLogger(__name__)


def write_sequential_chapter(
    batch_gen,
    *,
    outline,
    contract,
    contract_text: str,
    beat_chapter: Chapter | None,
    stream_callback,
    title: str,
    genre: str,
    style: str,
    characters: list,
    world,
    word_count: int,
    story_context,
    all_chapter_texts: list[str],
    bible_ctx,
    active_conflicts,
    seeds,
    payoffs,
    pacing,
    enhancement_context: str,
    arc_context,
    chapter_scenes: list[dict],
    idea: str = "",
    idea_summary: str = "",
) -> Chapter:
    """Write one sequential chapter via the appropriate path.

    Args:
        batch_gen: The BatchChapterGenerator instance (source of the story
            generator and token budget).
        outline: ChapterOutline being written.
        contract / contract_text: Chapter contract (or None) and its prompt
            text from build_contract_for_chapter.
        beat_chapter: Chapter already produced by per-beat writing, or None.
        stream_callback: Stream callback — selects the streaming writer.
        title / genre / style / characters / world / word_count: Story
            inputs forwarded to the writer.
        story_context / all_chapter_texts / bible_ctx: Accumulated context.
        active_conflicts / seeds / payoffs / pacing / arc_context: Outputs
            of assemble_chapter_write_context.
        enhancement_context: Fully assembled enhancement context.
        chapter_scenes: Scene decomposition output (may be empty).
        idea / idea_summary: Original idea passthrough.

    Returns:
        The written Chapter, with the contract attached when available.
    """
    negotiated_contract = contract.to_negotiated() if contract is not None else None
    if beat_chapter is not None:
        chapter = beat_chapter
    elif stream_callback:
        chapter = batch_gen.gen.write_chapter_stream(
            title,
            genre,
            style,
            characters,
            world,
            outline,
            word_count=word_count,
            context=story_context,
            stream_callback=stream_callback,
            open_threads=list(story_context.open_threads),
            active_conflicts=active_conflicts,
            foreshadowing_to_plant=seeds,
            foreshadowing_to_payoff=payoffs,
            pacing_type=pacing,
            enhancement_context=enhancement_context,
            current_arc_context=arc_context,
            chapter_contract=contract_text,
            scenes=chapter_scenes,
            negotiated_contract=negotiated_contract,
            idea=idea,
            idea_summary=idea_summary,
        )
    else:
        chapter = batch_gen.gen._write_chapter_with_long_context(
            title,
            genre,
            style,
            characters,
            world,
            outline,
            word_count,
            story_context,
            all_chapter_texts,
            bible_ctx,
            open_threads=list(story_context.open_threads),
            active_conflicts=active_conflicts,
            foreshadowing_to_plant=seeds,
            foreshadowing_to_payoff=payoffs,
            pacing_type=pacing,
            enhancement_context=enhancement_context,
            current_arc_context=arc_context,
            chapter_contract=contract_text,
            scenes=chapter_scenes,
            negotiated_contract=negotiated_contract,
            idea=idea,
            idea_summary=idea_summary,
        )

    if contract is not None:
        try:
            chapter.contract = contract
            # Sprint 1 P5: stash unified NegotiatedChapterContract on the
            # chapter as an in-memory attribute (DB column lands in P6).
            object.__setattr__(chapter, "negotiated_contract", contract.to_negotiated())
        except Exception as e:
            logger.debug("Attach contract to chapter failed: %s", e)

    chapter_tokens_used = estimate_tokens(chapter.content)
    usage_pct = (chapter_tokens_used / batch_gen.gen.token_budget_per_chapter) * 100
    if usage_pct >= 80:
        logger.warning(
            "Chapter %d at %d%% of token budget (%d/%d estimated tokens)",
            outline.chapter_number,
            int(usage_pct),
            chapter_tokens_used,
            batch_gen.gen.token_budget_per_chapter,
        )

    return chapter
