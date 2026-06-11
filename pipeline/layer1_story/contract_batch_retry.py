"""Batch-level contract validation with retry for the threaded write path.

Extracted from batch_generator.py (_run_batch_threaded, #2 improvement).
After all chapters in a threaded batch are written, validates each against
its contract; below-threshold chapters get the contract rebuilt with failure
feedback and are rewritten via batch_gen._write_chapter_parallel with
override_contract, up to retry_max attempts each. Non-fatal per chapter:
an exception logs a warning and keeps the current chapter.
"""

import logging

from models.schemas import Chapter, ChapterOutline, StoryContext

logger = logging.getLogger(__name__)


def validate_and_retry_threaded(
    batch_gen,
    *,
    chapters: list[Chapter],
    contracts: dict,
    batch: list[ChapterOutline],
    frozen,
    draft,
    story_context: StoryContext,
    frozen_threads: list,
    sibling_summaries: str,
    shared_enhancement: str,
    title: str,
    genre: str,
    style: str,
    characters: list,
    world,
    word_count: int,
    macro_arcs,
    conflict_web,
    foreshadowing_plan,
    progress_callback,
    idea: str = "",
    idea_summary: str = "",
) -> list[Chapter]:
    """Validate a threaded batch's chapters against their contracts.

    Gated by a non-empty contracts dict and pipeline.enable_contract_validation;
    when the gate is closed, chapters is returned unchanged.
    """
    if not contracts or not getattr(
        batch_gen.config.pipeline, "enable_contract_validation", False
    ):
        return chapters

    from pipeline.layer1_story.chapter_contract_builder import (
        validate_contract_compliance,
    )

    outline_map = {o.chapter_number: o for o in batch}
    chapter_map = {c.chapter_number: c for c in chapters}

    for ch_num, contract in contracts.items():
        chapter = chapter_map[ch_num]
        outline = outline_map[ch_num]
        try:
            compliance = validate_contract_compliance(
                batch_gen.llm,
                chapter.content,
                contract,
                model=batch_gen.gen._layer_model,
            )
            score = compliance.get("compliance_score", 0.0)
            failures = compliance.get("failures", [])

            retry_count = 0
            while (
                score < batch_gen.retry_threshold and retry_count < batch_gen.retry_max
            ):
                retry_count += 1
                if progress_callback:
                    progress_callback(
                        f"⚠️ Ch{ch_num} compliance {score:.0%}, retry {retry_count}/{batch_gen.retry_max}..."
                    )

                from pipeline.layer1_story.chapter_contract_builder import (
                    build_contract,
                )

                new_contract = build_contract(
                    ch_num,
                    outline,
                    threads=frozen_threads,
                    macro_arcs=macro_arcs,
                    conflicts=conflict_web,
                    foreshadowing_plan=foreshadowing_plan,
                    characters=characters,
                    previous_failures=failures,
                )

                new_chapter, _ = batch_gen._write_chapter_parallel(
                    outline,
                    frozen,
                    draft,
                    story_context,
                    frozen_threads,
                    sibling_summaries,
                    shared_enhancement,
                    title,
                    genre,
                    style,
                    characters,
                    world,
                    word_count,
                    macro_arcs,
                    conflict_web,
                    foreshadowing_plan,
                    progress_callback,
                    None,
                    idea,
                    idea_summary,
                    override_contract=new_contract,
                )
                chapter_map[ch_num] = new_chapter

                compliance = validate_contract_compliance(
                    batch_gen.llm,
                    new_chapter.content,
                    new_contract,
                    model=batch_gen.gen._layer_model,
                )
                score = compliance.get("compliance_score", 0.0)
                failures = compliance.get("failures", [])

            if progress_callback:
                status = f"Ch{ch_num} compliance: {score:.0%}"
                if retry_count > 0:
                    status += f" (sau {retry_count} retry)"
                progress_callback(status)
        except Exception as e:
            logger.warning("Contract validation failed for ch%d: %s", ch_num, e)

    return list(chapter_map.values())
