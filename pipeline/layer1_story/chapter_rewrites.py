"""Post-write rewrite passes: consistency violations (L1-D) and pacing (L1-F).

Extracted from batch_generator.py. Each pass mutates chapter.content in place
and is non-fatal: failures are logged and the original content is kept.
"""

import logging
from typing import Callable

from models.schemas import Chapter, ChapterOutline, StoryContext

logger = logging.getLogger(__name__)


def _rewrite_for_consistency_violations(
    pipeline_config,
    llm,
    chapter: Chapter,
    outline: ChapterOutline,
    story_context: StoryContext,
    layer_model: str | None,
    progress_callback: Callable | None = None,
    draft=None,
) -> None:
    """L1-D: Rewrite chapter when consistency validators flagged violations above threshold.

    Reads name_warnings / arc_drift_warnings from story_context + location warnings
    stashed on story_context.world_rule_violations. Mutates chapter.content in place.
    """
    if not getattr(pipeline_config, "enable_consistency_rewrite", False):
        return

    name_threshold = int(
        getattr(pipeline_config, "consistency_name_warning_threshold", 3)
    )
    arc_threshold = int(getattr(pipeline_config, "consistency_arc_drift_threshold", 2))
    loc_threshold = int(
        getattr(pipeline_config, "consistency_location_warning_threshold", 2)
    )

    issues: list[str] = []
    name_warnings = list(story_context.name_warnings or [])
    arc_warnings = list(story_context.arc_drift_warnings or [])
    # Location warnings may live in world_rule_violations — filter by prefix
    loc_warnings = [
        w
        for w in (story_context.world_rule_violations or [])
        if w.startswith("[VỊ TRÍ]")
    ]

    trigger = (
        len(name_warnings) >= name_threshold
        or len(arc_warnings) >= arc_threshold
        or len(loc_warnings) >= loc_threshold
    )
    if not trigger:
        return

    issues.extend(name_warnings)
    issues.extend(arc_warnings)
    issues.extend(loc_warnings)

    try:
        from pipeline.layer1_story.chapter_self_critique import rewrite_for_consistency
        from models.schemas import count_words

        if progress_callback:
            progress_callback(
                f"Ch{outline.chapter_number}: viết lại để sửa {len(issues)} lỗi nhất quán..."
            )
        _idea = getattr(draft, "original_idea", "") or "" if draft is not None else ""
        _idea_sum = (
            getattr(draft, "idea_summary_for_chapters", "") or ""
            if draft is not None
            else ""
        )
        revised = rewrite_for_consistency(
            llm,
            chapter.content,
            issues,
            model=layer_model,
            idea=_idea,
            idea_summary=_idea_sum,
        )
        if not revised or revised == chapter.content:
            return
        chapter.content = revised
        chapter.word_count = count_words(revised)
        # Clear warnings — they were based on the now-discarded content.
        # Keep loc_warnings from world_rule_violations untouched (may include non-location rules)
        story_context.name_warnings = []
        story_context.arc_drift_warnings = []
        if loc_warnings:
            story_context.world_rule_violations = [
                w
                for w in story_context.world_rule_violations
                if not w.startswith("[VỊ TRÍ]")
            ]
        if progress_callback:
            progress_callback(f"Ch{outline.chapter_number}: đã viết lại (consistency)")
    except Exception as e:
        logger.warning(
            "Consistency rewrite failed for ch%d (non-fatal): %s",
            outline.chapter_number,
            e,
        )


def _enforce_pacing(
    pipeline_config,
    llm,
    chapter: Chapter,
    outline: ChapterOutline,
    layer_model: str | None,
    progress_callback: Callable | None = None,
    draft=None,
) -> None:
    """L1-F: Classify chapter pacing; if confident mismatch, rewrite.

    Mutates chapter.content/word_count in place. Non-fatal.
    """
    if not getattr(pipeline_config, "enable_pacing_enforcement", False):
        return
    target = (getattr(outline, "pacing_type", "") or "").strip().lower()
    if not target:
        return
    try:
        from pipeline.layer1_story.pacing_enforcer import (
            verify_pacing,
            rewrite_for_pacing,
        )
        from models.schemas import count_words

        verdict = verify_pacing(llm, chapter.content, target, model=layer_model)
        if not verdict or verdict.get("match", True):
            return
        conf_threshold = float(
            getattr(pipeline_config, "pacing_enforcement_confidence", 0.7)
        )
        if float(verdict.get("confidence", 0.0)) < conf_threshold:
            logger.debug(
                "Ch%d pacing mismatch under threshold (target=%s, detected=%s, conf=%.2f)",
                outline.chapter_number,
                target,
                verdict.get("detected"),
                verdict.get("confidence", 0.0),
            )
            return
        if not getattr(pipeline_config, "pacing_mismatch_rewrite", False):
            if progress_callback:
                progress_callback(
                    f"⚠️ Ch{outline.chapter_number} pacing lệch "
                    f"(muốn {target}, thực {verdict.get('detected')}) — không rewrite"
                )
            return
        if progress_callback:
            progress_callback(
                f"Ch{outline.chapter_number}: viết lại cho khớp nhịp '{target}'..."
            )
        _idea = getattr(draft, "original_idea", "") or "" if draft is not None else ""
        _idea_sum = (
            getattr(draft, "idea_summary_for_chapters", "") or ""
            if draft is not None
            else ""
        )
        revised = rewrite_for_pacing(
            llm,
            chapter.content,
            target,
            verdict.get("detected", ""),
            verdict.get("reason", ""),
            model=layer_model,
            idea=_idea,
            idea_summary=_idea_sum,
        )
        if revised and revised != chapter.content:
            chapter.content = revised
            chapter.word_count = count_words(revised)
            if progress_callback:
                progress_callback(f"Ch{outline.chapter_number}: đã viết lại (pacing)")
    except Exception as e:
        logger.warning(
            "Pacing enforcement failed for ch%d (non-fatal): %s",
            outline.chapter_number,
            e,
        )
