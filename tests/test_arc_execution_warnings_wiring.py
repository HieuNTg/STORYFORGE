"""The arc-execution validator's output must actually reach the rewrite.

Two validators report a drifting character arc. ``arc_drift_warnings`` was read
by the consistency rewrite; ``arc_execution_warnings`` — raised when a chapter
never executes the arc stage its outline planned — was written to
``story_context`` and read by nothing, so that validator's work was discarded
every chapter except for one log line.

These tests pin the wiring: both lists trigger the rewrite, both are cleared
once the content they described has been replaced, and neither is silently
dropped again.
"""

from types import SimpleNamespace
from unittest.mock import patch

from pipeline.layer1_story.chapter_rewrites import (
    _rewrite_for_consistency_violations,
)


class _Chapter:
    def __init__(self, content="nội dung gốc"):
        self.content = content
        self.word_count = len(content.split())


def _context(**kw):
    base = {
        "name_warnings": [],
        "arc_drift_warnings": [],
        "arc_execution_warnings": [],
        "world_rule_violations": [],
    }
    base.update(kw)
    return SimpleNamespace(**base)


def _config(**kw):
    base = {
        "enable_consistency_rewrite": True,
        "consistency_name_warning_threshold": 3,
        "consistency_arc_drift_threshold": 2,
        "consistency_location_warning_threshold": 2,
    }
    base.update(kw)
    return SimpleNamespace(**base)


def _run(story_context, revised="nội dung đã sửa"):
    """Run the rewrite with the LLM stubbed; returns (chapter, issues_seen)."""
    chapter = _Chapter()
    seen: list[list[str]] = []

    def _fake_rewrite(llm, content, issues, **kwargs):
        seen.append(list(issues))
        return revised

    with patch(
        "pipeline.layer1_story.chapter_self_critique.rewrite_for_consistency",
        _fake_rewrite,
    ):
        _rewrite_for_consistency_violations(
            _config(),
            object(),  # llm — never called directly
            chapter,
            SimpleNamespace(chapter_number=4),
            story_context,
            None,
        )
    return chapter, (seen[0] if seen else None)


def test_arc_execution_warnings_alone_trigger_the_rewrite():
    """Two execution warnings meet the arc threshold on their own."""
    ctx = _context(
        arc_execution_warnings=["Kiên: giai đoạn 'ngờ vực' chưa thể hiện", "Lan: ..."]
    )
    chapter, issues = _run(ctx)
    assert issues is not None, "rewrite never ran"
    assert chapter.content == "nội dung đã sửa"
    assert "Kiên: giai đoạn 'ngờ vực' chưa thể hiện" in issues


def test_both_arc_lists_are_combined_against_the_threshold():
    """One warning from each list still adds up to the threshold of 2."""
    ctx = _context(
        arc_drift_warnings=["Kiên: cung bậc lệch"],
        arc_execution_warnings=["Lan: giai đoạn chưa thể hiện"],
    )
    _chapter, issues = _run(ctx)
    assert issues is not None, "combined warnings did not reach the threshold"
    assert set(issues) == {"Kiên: cung bậc lệch", "Lan: giai đoạn chưa thể hiện"}


def test_execution_warnings_are_cleared_after_a_successful_rewrite():
    """They described content that no longer exists — keeping them re-fires."""
    ctx = _context(
        arc_execution_warnings=["a", "b"], arc_drift_warnings=["c", "d"]
    )
    _run(ctx)
    assert ctx.arc_execution_warnings == []
    assert ctx.arc_drift_warnings == []


def test_warnings_survive_a_rewrite_that_changed_nothing():
    """No rewrite happened, so the warnings still describe the live content."""
    ctx = _context(arc_execution_warnings=["a", "b"])
    chapter, _issues = _run(ctx, revised="nội dung gốc")  # identical → rejected
    assert chapter.content == "nội dung gốc"
    assert ctx.arc_execution_warnings == ["a", "b"]


def test_one_execution_warning_is_below_the_threshold():
    ctx = _context(arc_execution_warnings=["chỉ một"])
    _chapter, issues = _run(ctx)
    assert issues is None
