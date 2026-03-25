"""Tests for services/quality_gate.py"""

import pytest

from models.schemas import ChapterScore, StoryScore
from services.quality_gate import (
    DEFAULT_CHAPTER_THRESHOLD,
    DEFAULT_GATE_THRESHOLD,
    MAX_RETRIES,
    QualityGate,
    QualityGateResult,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def make_chapter_score(chapter_number: int, overall: float) -> ChapterScore:
    cs = ChapterScore(chapter_number=chapter_number)
    cs.overall = overall
    return cs


def make_story_score(chapter_overalls: list[float], overall: float) -> StoryScore:
    chapter_scores = [make_chapter_score(i + 1, s) for i, s in enumerate(chapter_overalls)]
    s = StoryScore(chapter_scores=chapter_scores)
    s.overall = overall
    return s


# ─── QualityGateResult ────────────────────────────────────────────────────────

class TestQualityGateResult:
    def test_attributes_set_correctly(self):
        r = QualityGateResult(
            passed=True, overall_score=3.5, weak_chapters=[],
            message="ok", should_retry=False
        )
        assert r.passed is True
        assert r.overall_score == 3.5
        assert r.weak_chapters == []
        assert r.message == "ok"
        assert r.should_retry is False

    def test_should_retry_defaults_false(self):
        r = QualityGateResult(passed=False, overall_score=1.0, weak_chapters=[], message="fail")
        assert r.should_retry is False


# ─── QualityGate.check ────────────────────────────────────────────────────────

class TestQualityGateCheck:
    def setup_method(self):
        self.gate = QualityGate(
            gate_threshold=2.5,
            chapter_threshold=2.0,
            max_retries=1,
        )

    # --- None / empty score ---

    def test_none_score_passes(self):
        result = self.gate.check(None)
        assert result.passed is True
        assert result.overall_score == 0.0
        assert "bỏ qua" in result.message

    def test_empty_chapter_scores_passes(self):
        score = StoryScore()  # no chapter_scores
        result = self.gate.check(score)
        assert result.passed is True

    # --- Passing scores ---

    def test_passing_overall_and_no_weak_chapters(self):
        score = make_story_score([3.0, 3.5, 4.0], overall=3.5)
        result = self.gate.check(score)
        assert result.passed is True
        assert "PASSED" in result.message
        assert result.weak_chapters == []
        assert result.should_retry is False

    def test_pass_exactly_at_threshold(self):
        score = make_story_score([2.5, 2.5], overall=2.5)
        result = self.gate.check(score)
        assert result.passed is True

    # --- Failing: overall below threshold, can retry ---

    def test_low_overall_triggers_retry(self):
        score = make_story_score([2.0, 2.0], overall=2.0)
        result = self.gate.check(score, retry_count=0)
        assert result.passed is False
        assert result.should_retry is True
        assert "RETRY" in result.message

    def test_weak_chapter_triggers_retry_even_if_overall_passes(self):
        # overall above threshold but one chapter below chapter_threshold
        score = make_story_score([1.5, 4.0, 4.0], overall=3.2)
        result = self.gate.check(score, retry_count=0)
        assert result.passed is False
        assert result.should_retry is True
        assert len(result.weak_chapters) == 1
        assert result.weak_chapters[0]["chapter"] == 1
        assert result.weak_chapters[0]["score"] == 1.5

    # --- Failing: retries exhausted ---

    def test_retries_exhausted_no_retry(self):
        score = make_story_score([1.0, 1.5], overall=1.2)
        result = self.gate.check(score, retry_count=1)
        assert result.passed is False
        assert result.should_retry is False
        assert "FAILED" in result.message

    def test_max_retries_zero_immediately_hard_fails(self):
        gate = QualityGate(gate_threshold=2.5, chapter_threshold=2.0, max_retries=0)
        score = make_story_score([2.0], overall=2.0)
        result = gate.check(score, retry_count=0)
        assert result.passed is False
        assert result.should_retry is False

    # --- Multiple weak chapters ---

    def test_multiple_weak_chapters_reported(self):
        score = make_story_score([1.0, 1.5, 3.0, 1.8], overall=1.8)
        result = self.gate.check(score, retry_count=0)
        assert result.passed is False
        assert len(result.weak_chapters) == 3  # chapters 1, 2, 4 below 2.0

    # --- Custom thresholds ---

    def test_custom_high_threshold(self):
        gate = QualityGate(gate_threshold=4.0, chapter_threshold=3.0, max_retries=1)
        score = make_story_score([3.5, 3.5], overall=3.5)
        result = gate.check(score)
        assert result.passed is False  # 3.5 < 4.0

    def test_custom_low_threshold(self):
        gate = QualityGate(gate_threshold=1.5, chapter_threshold=1.0, max_retries=1)
        score = make_story_score([1.5, 2.0], overall=1.8)
        result = gate.check(score)
        assert result.passed is True  # 1.8 >= 1.5 and no chapters below 1.0


# ─── Config integration ───────────────────────────────────────────────────────

class TestQualityGateConfig:
    def test_default_fields_exist(self):
        from config import ConfigManager
        # Reset singleton for isolated test
        ConfigManager._instance = None
        cfg = ConfigManager()
        assert hasattr(cfg.pipeline, "enable_quality_gate")
        assert cfg.pipeline.enable_quality_gate is False
        assert cfg.pipeline.quality_gate_threshold == 2.5
        assert cfg.pipeline.quality_gate_chapter_threshold == 2.0
        assert cfg.pipeline.quality_gate_max_retries == 1

    def test_validation_rejects_out_of_range_threshold(self):
        from config import ConfigManager
        ConfigManager._instance = None
        cfg = ConfigManager()
        cfg.pipeline.quality_gate_threshold = 0.5  # below 1.0
        errors = cfg.validate()
        assert any("quality_gate_threshold" in e for e in errors)

    def test_validation_accepts_valid_threshold(self):
        from config import ConfigManager
        ConfigManager._instance = None
        cfg = ConfigManager()
        cfg.pipeline.quality_gate_threshold = 3.0
        errors = cfg.validate()
        assert not any("quality_gate_threshold" in e for e in errors)

    def test_validation_rejects_high_threshold(self):
        from config import ConfigManager
        ConfigManager._instance = None
        cfg = ConfigManager()
        cfg.pipeline.quality_gate_threshold = 5.5  # above 5.0
        errors = cfg.validate()
        assert any("quality_gate_threshold" in e for e in errors)
