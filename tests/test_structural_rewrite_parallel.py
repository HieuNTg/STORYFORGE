"""Tests for P6 bounded-concurrency structural rewriter.

Covers: semaphore cap, per-chapter failure isolation, batch_size=1 degradation,
empty input, and pipeline_stats counters.
"""
import asyncio
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pipeline.orchestrator_layers import _run_structural_rewrites


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_self(chapter_batch_size=2):
    """Build a minimal orchestrator-like namespace accepted by _run_structural_rewrites."""
    cfg_pipeline = types.SimpleNamespace(chapter_batch_size=chapter_batch_size)
    cfg = types.SimpleNamespace(pipeline=cfg_pipeline)

    chapter_stub = MagicMock()
    chapter_stub.chapter_number = 0  # overridden per-call

    story_gen = MagicMock()
    # write_chapter is a sync callable; we wrap it with asyncio.to_thread inside the helper.
    # For testing we provide a fast synchronous stub.
    story_gen.write_chapter = MagicMock(return_value=chapter_stub)

    self_ns = types.SimpleNamespace(
        config=cfg,
        story_gen=story_gen,
    )
    return self_ns


def _make_draft(chapter_numbers):
    """Build a minimal draft with given chapter numbers."""
    chapters = []
    for n in chapter_numbers:
        ch = MagicMock()
        ch.chapter_number = n
        # No negotiated_contract by default
        del ch.negotiated_contract
        chapters.append(ch)

    draft = MagicMock()
    draft.title = "Test Story"
    draft.chapters = chapters
    draft.world = MagicMock()
    draft.characters = []
    return draft


def _make_issues(chapter_number):
    """Build a single-issue list for one chapter."""
    issue = MagicMock()
    issue.fix_hint = f"fix ch{chapter_number}"
    issue.description = f"desc ch{chapter_number}"
    return [issue]


# ---------------------------------------------------------------------------
# Test 1: concurrency cap with chapter_batch_size=2
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_semaphore_cap_at_batch_size():
    """5 chapters, batch_size=2 — concurrent count never exceeds 2."""
    chapter_numbers = [1, 2, 3, 4, 5]
    issues_by_chapter = {n: _make_issues(n) for n in chapter_numbers}
    draft = _make_draft(chapter_numbers)
    self_ns = _make_self(chapter_batch_size=2)
    outline_map = {}

    concurrent_count = 0
    max_concurrent = 0
    lock = asyncio.Lock()

    original_write = self_ns.story_gen.write_chapter

    def slow_write(**kwargs):
        # Can't use asyncio here (sync context), so just return
        ch = MagicMock()
        ch.chapter_number = kwargs.get("outline") and 0 or 0
        return original_write(**kwargs)

    # Patch asyncio.to_thread to track concurrency
    real_to_thread = asyncio.to_thread

    async def tracking_to_thread(fn, *args, **kwargs):
        nonlocal concurrent_count, max_concurrent
        async with lock:
            concurrent_count += 1
            if concurrent_count > max_concurrent:
                max_concurrent = concurrent_count
        try:
            return await real_to_thread(fn, *args, **kwargs)
        finally:
            async with lock:
                concurrent_count -= 1

    with patch("pipeline.orchestrator_layers.asyncio.to_thread", side_effect=tracking_to_thread):
        rewritten, failed = await _run_structural_rewrites(
            self_ns,
            issues_by_chapter=issues_by_chapter,
            draft=draft,
            genre="action",
            style="normal",
            word_count=1000,
            outline_map=outline_map,
            log_fn=lambda m: None,
        )

    assert max_concurrent <= 2, f"Max concurrent was {max_concurrent}, expected <= 2"
    assert len(rewritten) == 5
    assert len(failed) == 0


# ---------------------------------------------------------------------------
# Test 2: one chapter raises — siblings complete, failed list is correct
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_one_failure_does_not_cancel_siblings():
    """Chapter 3 raises; chapters 1,2,4,5 succeed; failed=(3, exc)."""
    chapter_numbers = [1, 2, 3, 4, 5]
    issues_by_chapter = {n: _make_issues(n) for n in chapter_numbers}
    draft = _make_draft(chapter_numbers)
    self_ns = _make_self(chapter_batch_size=5)
    outline_map = {}

    fail_exc = ValueError("ch3 boom")

    def write_chapter_fn(**kwargs):
        # outline is the ChapterOutline stub; we identify chapter by enhancement_context
        ctx = kwargs.get("enhancement_context", "")
        if "ch3" in ctx:
            raise fail_exc
        ch = MagicMock()
        return ch

    self_ns.story_gen.write_chapter = write_chapter_fn

    rewritten, failed = await _run_structural_rewrites(
        self_ns,
        issues_by_chapter=issues_by_chapter,
        draft=draft,
        genre="action",
        style="normal",
        word_count=1000,
        outline_map=outline_map,
        log_fn=lambda m: None,
    )

    assert len(rewritten) == 4, f"Expected 4 succeeded, got {len(rewritten)}"
    assert len(failed) == 1, f"Expected 1 failed, got {len(failed)}"
    assert failed[0][0] == 3
    assert isinstance(failed[0][1], ValueError)


# ---------------------------------------------------------------------------
# Test 3: chapter_batch_size=1 — effectively serial, helper still works
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_batch_size_1_is_serial():
    """batch_size=1 → concurrency never exceeds 1; all chapters complete."""
    chapter_numbers = [1, 2, 3]
    issues_by_chapter = {n: _make_issues(n) for n in chapter_numbers}
    draft = _make_draft(chapter_numbers)
    self_ns = _make_self(chapter_batch_size=1)
    outline_map = {}

    concurrent_count = 0
    max_concurrent = 0
    lock = asyncio.Lock()
    real_to_thread = asyncio.to_thread

    async def tracking_to_thread(fn, *args, **kwargs):
        nonlocal concurrent_count, max_concurrent
        async with lock:
            concurrent_count += 1
            if concurrent_count > max_concurrent:
                max_concurrent = concurrent_count
        try:
            return await real_to_thread(fn, *args, **kwargs)
        finally:
            async with lock:
                concurrent_count -= 1

    with patch("pipeline.orchestrator_layers.asyncio.to_thread", side_effect=tracking_to_thread):
        rewritten, failed = await _run_structural_rewrites(
            self_ns,
            issues_by_chapter=issues_by_chapter,
            draft=draft,
            genre="action",
            style="normal",
            word_count=1000,
            outline_map=outline_map,
            log_fn=lambda m: None,
        )

    assert max_concurrent <= 1, f"Max concurrent was {max_concurrent}, expected <= 1"
    assert len(rewritten) == 3
    assert len(failed) == 0


# ---------------------------------------------------------------------------
# Test 4: empty input returns ([], []) without calling writer
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_empty_input_returns_empty():
    """Empty issues_by_chapter → ([], []) and write_chapter never called."""
    draft = _make_draft([])
    self_ns = _make_self(chapter_batch_size=2)

    rewritten, failed = await _run_structural_rewrites(
        self_ns,
        issues_by_chapter={},
        draft=draft,
        genre="action",
        style="normal",
        word_count=1000,
        outline_map={},
        log_fn=lambda m: None,
    )

    assert rewritten == []
    assert failed == []
    self_ns.story_gen.write_chapter.assert_not_called()


# ---------------------------------------------------------------------------
# Test 5: pipeline_stats counters — attempted=5, succeeded=4, failed=1
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pipeline_stats_via_caller_logic():
    """Verify stat counting logic matches the orchestrator's accumulation pattern.

    We replicate the counter logic from run_full_pipeline to verify it gives
    attempted=5, succeeded=4, failed=1 for the one-failure scenario.
    """
    chapter_numbers = [1, 2, 3, 4, 5]
    issues_by_chapter = {n: _make_issues(n) for n in chapter_numbers}
    draft = _make_draft(chapter_numbers)
    self_ns = _make_self(chapter_batch_size=5)
    outline_map = {}

    fail_exc = ValueError("ch3 boom")

    def write_chapter_fn(**kwargs):
        ctx = kwargs.get("enhancement_context", "")
        if "ch3" in ctx:
            raise fail_exc
        return MagicMock()

    self_ns.story_gen.write_chapter = write_chapter_fn

    rewritten_pairs, failed_pairs = await _run_structural_rewrites(
        self_ns,
        issues_by_chapter=issues_by_chapter,
        draft=draft,
        genre="action",
        style="normal",
        word_count=1000,
        outline_map=outline_map,
        log_fn=lambda m: None,
    )

    # Replicate the counter accumulation from orchestrator
    _sr_attempted = len(issues_by_chapter)  # 5
    _sr_succeeded = len(rewritten_pairs)    # 4
    _sr_failed = len(failed_pairs)          # 1

    stats: dict = {}
    stats["structural_rewrites_attempted"] = stats.get("structural_rewrites_attempted", 0) + _sr_attempted
    stats["structural_rewrites_succeeded"] = stats.get("structural_rewrites_succeeded", 0) + _sr_succeeded
    stats["structural_rewrites_failed"] = stats.get("structural_rewrites_failed", 0) + _sr_failed

    assert stats["structural_rewrites_attempted"] == 5
    assert stats["structural_rewrites_succeeded"] == 4
    assert stats["structural_rewrites_failed"] == 1
