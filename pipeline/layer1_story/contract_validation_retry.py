"""Post-write contract validation with retry for the sequential batch path.

Extracted from batch_generator.py (#2 improvement). After a chapter is
written and finalized, validates it against its negotiated contract; if the
compliance score falls below the retry threshold, rebuilds the contract with
failure feedback and rewrites the chapter, up to retry_max attempts. Mutates
chapters[-1]/all_chapter_texts[-1] in place when a rewrite happens. The whole
pass is non-fatal: any exception logs a warning and clears the failure list.
"""

import logging
from typing import Callable

from models.schemas import Chapter, ChapterOutline, StoryContext

logger = logging.getLogger(__name__)


def validate_and_retry_contract(
    gen,
    pipeline_config,
    llm,
    *,
    retry_max: int,
    retry_threshold: float,
    chapter: Chapter,
    outline: ChapterOutline,
    contract,
    contract_text: str,
    chapters: list[Chapter],
    all_chapter_texts: list[str],
    story_context: StoryContext,
    bible_ctx: str,
    active_conflicts: list,
    seeds: list,
    payoffs: list,
    pacing: str,
    enhancement_context: str,
    arc_context: str,
    chapter_scenes,
    stream_callback,
    title: str,
    genre: str,
    style: str,
    characters: list,
    world,
    word_count: int,
    macro_arcs,
    conflict_web,
    foreshadowing_plan,
    previous_failures: list,
    progress_callback: Callable | None = None,
    idea: str = "",
    idea_summary: str = "",
) -> list:
    """Validate one chapter against its contract, rewriting on low compliance.

    Gated by pipeline_config.enable_contract_validation and a non-None
    contract; when the gate is closed, previous_failures is returned
    unchanged so the caller's failure feedback carries to the next chapter.
    Returns the failure list from the final compliance check ([] on error).
    """
    if contract is None or not getattr(
        pipeline_config, "enable_contract_validation", False
    ):
        return previous_failures
    _contract_failures = previous_failures
    try:
        from pipeline.layer1_story.chapter_contract_builder import (
            validate_contract_compliance,
        )

        compliance = validate_contract_compliance(
            llm,
            chapter.content,
            contract,
            model=gen._layer_model,
        )
        _contract_failures = compliance.get("failures", [])
        score = compliance.get("compliance_score", 0.0)

        # Retry logic: if score below threshold, rewrite chapter
        retry_count = 0
        while score < retry_threshold and retry_count < retry_max:
            retry_count += 1
            if progress_callback:
                progress_callback(
                    f"⚠️ Ch{outline.chapter_number} compliance {score:.0%} < {retry_threshold:.0%}, retry {retry_count}/{retry_max}..."
                )
            logger.info(
                "Ch%d retry %d: compliance %.0f%% < %.0f%%, failures: %s",
                outline.chapter_number,
                retry_count,
                score * 100,
                retry_threshold * 100,
                _contract_failures,
            )

            # Rebuild contract with failure feedback
            try:
                from pipeline.layer1_story.chapter_contract_builder import (
                    build_contract,
                    format_contract_for_prompt,
                )

                contract = build_contract(
                    outline.chapter_number,
                    outline,
                    threads=list(story_context.open_threads),
                    macro_arcs=macro_arcs,
                    conflicts=conflict_web,
                    foreshadowing_plan=foreshadowing_plan,
                    characters=characters,
                    previous_failures=_contract_failures,
                )
                contract_text = format_contract_for_prompt(contract)
            except Exception as e:
                logger.warning(
                    "Contract rebuild failed for ch%d retry: %s",
                    outline.chapter_number,
                    e,
                )

            # Rewrite chapter with updated contract
            if stream_callback:
                chapter = gen.write_chapter_stream(
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
                    idea=idea,
                    idea_summary=idea_summary,
                )
            else:
                chapter = gen._write_chapter_with_long_context(
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
                    idea=idea,
                    idea_summary=idea_summary,
                )

            # Update in chapters list
            chapters[-1] = chapter
            all_chapter_texts[-1] = chapter.content

            # Re-validate
            compliance = validate_contract_compliance(
                llm,
                chapter.content,
                contract,
                model=gen._layer_model,
            )
            _contract_failures = compliance.get("failures", [])
            score = compliance.get("compliance_score", 0.0)

        if score < 0.7:
            logger.warning(
                "Ch%d final compliance %.0f%% — failures: %s",
                outline.chapter_number,
                score * 100,
                _contract_failures,
            )
        elif progress_callback:
            progress_callback(
                f"Chương {outline.chapter_number} hợp đồng: {score:.0%}"
                + (f" (sau {retry_count} retry)" if retry_count > 0 else "")
            )
    except Exception as e:
        logger.warning(
            "Contract validation failed for ch%d (non-fatal): %s",
            outline.chapter_number,
            e,
        )
        _contract_failures = []
    return _contract_failures
