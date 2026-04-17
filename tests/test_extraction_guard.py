"""Unit tests for Context Health Monitor (Sprint 1 Task 1)."""
from __future__ import annotations

import pytest

from models.schemas import ExtractionHealth, StoryContext
from pipeline.layer1_story.extraction_guard import tracked_extraction


def test_records_success():
    ctx = StoryContext()
    with tracked_extraction(ctx, 1, "summary"):
        pass
    assert len(ctx.extraction_health) == 1
    rec = ctx.extraction_health[0]
    assert rec.success is True
    assert rec.extraction_type == "summary"
    assert rec.chapter_number == 1
    assert rec.error == ""


def test_records_failure_and_swallows_by_default():
    ctx = StoryContext()
    # Should NOT raise — swallow=True is the default
    with tracked_extraction(ctx, 2, "plot_events"):
        raise ValueError("llm timeout")
    rec = ctx.extraction_health[0]
    assert rec.success is False
    assert "llm timeout" in rec.error
    assert rec.chapter_number == 2


def test_reraises_when_swallow_false():
    ctx = StoryContext()
    with pytest.raises(ValueError):
        with tracked_extraction(ctx, 3, "summary", swallow=False):
            raise ValueError("boom")
    assert ctx.extraction_health[-1].success is False


def test_records_duration_ms():
    ctx = StoryContext()
    with tracked_extraction(ctx, 1, "summary"):
        import time
        time.sleep(0.01)
    assert ctx.extraction_health[0].duration_ms >= 10


def test_health_cap_bounds_memory():
    ctx = StoryContext()
    for i in range(250):
        with tracked_extraction(ctx, i, "summary"):
            pass
    # extraction_guard._HEALTH_CAP = 200
    assert len(ctx.extraction_health) == 200
    # Oldest entries dropped
    assert ctx.extraction_health[0].chapter_number == 50


class TestHealthScore:
    def test_empty_history_is_perfect(self):
        assert StoryContext().compute_health_score() == 1.0

    def test_all_success_is_perfect(self):
        ctx = StoryContext()
        for _ in range(10):
            ctx.extraction_health.append(
                ExtractionHealth(chapter_number=1, extraction_type="x", success=True)
            )
        assert ctx.compute_health_score() == 1.0

    def test_mixed_ratio(self):
        ctx = StoryContext()
        for i in range(10):
            ctx.extraction_health.append(
                ExtractionHealth(chapter_number=1, extraction_type="x", success=(i < 7))
            )
        assert ctx.compute_health_score() == 0.7

    def test_all_failure_is_zero(self):
        ctx = StoryContext()
        for _ in range(6):
            ctx.extraction_health.append(
                ExtractionHealth(chapter_number=1, extraction_type="x", success=False)
            )
        assert ctx.compute_health_score() == 0.0


class TestFailedExtractionsInChapter:
    def test_filters_by_chapter_and_failure(self):
        ctx = StoryContext()
        ctx.extraction_health.extend([
            ExtractionHealth(chapter_number=1, extraction_type="a", success=False),
            ExtractionHealth(chapter_number=1, extraction_type="b", success=True),
            ExtractionHealth(chapter_number=1, extraction_type="c", success=False),
            ExtractionHealth(chapter_number=2, extraction_type="a", success=False),
        ])
        assert len(ctx.failed_extractions_in_last_chapter(1)) == 2
        assert len(ctx.failed_extractions_in_last_chapter(2)) == 1
        assert len(ctx.failed_extractions_in_last_chapter(99)) == 0
