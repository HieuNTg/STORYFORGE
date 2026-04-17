"""Integration test for Context Health circuit breaker (Sprint 1 Task 1)."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from models.schemas import ExtractionHealth, StoryContext
from pipeline.layer1_story.batch_generator import BatchChapterGenerator


def _make_gen() -> BatchChapterGenerator:
    """Build a minimal BatchChapterGenerator for calling _check_context_health directly."""
    parent = MagicMock()
    parent.config.pipeline.parallel_chapters_enabled = True
    parent.config.pipeline.chapter_batch_size = 5
    parent.config.pipeline.context_window = 3
    return BatchChapterGenerator(parent)


def _fail_chapter(ctx: StoryContext, ch: int, n_fail: int = 3) -> None:
    for i in range(n_fail):
        ctx.extraction_health.append(
            ExtractionHealth(chapter_number=ch, extraction_type=f"t{i}", success=False, error="mock")
        )
    # add one success so chapter is visible in recent_chapters
    ctx.extraction_health.append(
        ExtractionHealth(chapter_number=ch, extraction_type="ok", success=True)
    )


def test_healthy_context_passes():
    gen = _make_gen()
    ctx = StoryContext()
    for ch in range(1, 6):
        for _ in range(5):
            ctx.extraction_health.append(
                ExtractionHealth(chapter_number=ch, extraction_type="x", success=True)
            )
    # Should not raise
    gen._check_context_health(ctx, batch_idx=0, _log=lambda m: None)


def test_two_bad_chapters_no_halt():
    gen = _make_gen()
    ctx = StoryContext()
    _fail_chapter(ctx, 1, n_fail=3)
    _fail_chapter(ctx, 2, n_fail=3)
    # Third chapter healthy
    for _ in range(5):
        ctx.extraction_health.append(
            ExtractionHealth(chapter_number=3, extraction_type="x", success=True)
        )
    # Two bad of three — should NOT halt
    gen._check_context_health(ctx, batch_idx=0, _log=lambda m: None)


def test_three_consecutive_bad_chapters_halts():
    gen = _make_gen()
    ctx = StoryContext()
    _fail_chapter(ctx, 1, n_fail=3)
    _fail_chapter(ctx, 2, n_fail=3)
    _fail_chapter(ctx, 3, n_fail=3)
    with pytest.raises(RuntimeError, match="Context corruption detected"):
        gen._check_context_health(ctx, batch_idx=0, _log=lambda m: None)


def test_single_failure_per_chapter_no_halt():
    """Even across many chapters, 1 fail/chapter shouldn't trip breaker."""
    gen = _make_gen()
    ctx = StoryContext()
    for ch in range(1, 6):
        ctx.extraction_health.append(
            ExtractionHealth(chapter_number=ch, extraction_type="x", success=False, error="e")
        )
        for _ in range(4):
            ctx.extraction_health.append(
                ExtractionHealth(chapter_number=ch, extraction_type="y", success=True)
            )
    gen._check_context_health(ctx, batch_idx=0, _log=lambda m: None)


def test_health_logs_warning_below_70_percent(caplog):
    gen = _make_gen()
    ctx = StoryContext()
    # 5 fail / 10 total = 50% → below 70% threshold
    for i in range(10):
        ctx.extraction_health.append(
            ExtractionHealth(
                chapter_number=i // 2 + 1,
                extraction_type="x",
                success=(i % 2 == 0),
            )
        )
    messages = []
    gen._check_context_health(ctx, batch_idx=2, _log=lambda m: messages.append(m))
    assert any("health=" in m for m in messages)
    assert any("⚠️" in m or "< 70%" in m for m in messages)
