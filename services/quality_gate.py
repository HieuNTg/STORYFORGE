"""Quality gate — inline scoring between pipeline layers.

Blocks pipeline progression if quality scores are below configurable thresholds.
Can auto-retry the layer or halt with user feedback.
"""

import logging
import os
from typing import Optional

from models.schemas import StoryScore

logger = logging.getLogger(__name__)

# Default gate thresholds (1-5 scale)
DEFAULT_GATE_THRESHOLD = 2.5  # Minimum overall score to proceed
DEFAULT_CHAPTER_THRESHOLD = 2.0  # Minimum per-chapter score (fail if ANY chapter below)
MAX_RETRIES = 1  # Max auto-retries before hard stop


class QualityGateResult:
    """Result of a quality gate check."""

    __slots__ = ("passed", "overall_score", "weak_chapters", "message", "should_retry")

    def __init__(self, passed: bool, overall_score: float, weak_chapters: list,
                 message: str, should_retry: bool = False):
        self.passed = passed
        self.overall_score = overall_score
        self.weak_chapters = weak_chapters
        self.message = message
        self.should_retry = should_retry


class QualityGate:
    """Inline quality gate between pipeline layers.

    Evaluates layer output quality and decides whether to proceed, retry, or halt.
    """

    def __init__(
        self,
        gate_threshold: float = DEFAULT_GATE_THRESHOLD,
        chapter_threshold: float = DEFAULT_CHAPTER_THRESHOLD,
        max_retries: int = MAX_RETRIES,
    ):
        self.gate_threshold = gate_threshold
        self.chapter_threshold = chapter_threshold
        self.max_retries = max_retries
        # Circuit breaker: limit total retries across all chapters to prevent cost explosion.
        # Configurable via STORYFORGE_MAX_TOTAL_RETRIES; defaults to max_retries * 3.
        self._max_total_retries: int = int(
            os.environ.get("STORYFORGE_MAX_TOTAL_RETRIES", max_retries * 3)
        )
        self._total_retries: int = 0
        self._best_score: Optional[StoryScore] = None
        self._best_overall: float = -1.0

    def check(self, score: Optional[StoryScore], retry_count: int = 0) -> QualityGateResult:
        """Check if quality score passes the gate.

        Args:
            score: StoryScore from QualityScorer
            retry_count: How many times this layer has been retried

        Returns:
            QualityGateResult with pass/fail decision
        """
        if not score or not score.chapter_scores:
            return QualityGateResult(
                passed=True, overall_score=0.0, weak_chapters=[],
                message="Không có điểm chất lượng — bỏ qua quality gate."
            )

        overall = score.overall

        # Track best score seen for circuit breaker fallback
        if overall > self._best_overall:
            self._best_overall = overall
            self._best_score = score

        # Find chapters below chapter threshold
        weak_chapters = []
        for cs in score.chapter_scores:
            if cs.overall < self.chapter_threshold:
                weak_chapters.append({
                    "chapter": cs.chapter_number,
                    "score": cs.overall,
                    "notes": cs.notes,
                })

        # PASS: overall above threshold and no critically weak chapters
        if overall >= self.gate_threshold and not weak_chapters:
            return QualityGateResult(
                passed=True, overall_score=overall, weak_chapters=[],
                message=f"Quality gate PASSED: {overall:.1f}/5.0 (threshold: {self.gate_threshold})"
            )

        # Circuit breaker: stop retrying if total retries across all chapters is too high
        if self._total_retries >= self._max_total_retries:
            logger.warning(
                "Quality gate circuit breaker triggered after %d total retries. "
                "Proceeding with best available chapters.",
                self._total_retries,
            )
            best_overall = self._best_overall if self._best_overall >= 0 else overall
            return QualityGateResult(
                passed=True, overall_score=best_overall, weak_chapters=weak_chapters,
                message=(
                    f"Quality gate circuit breaker triggered after {self._total_retries} total retries. "
                    f"Proceeding with best available chapters (score: {best_overall:.1f}/5.0)."
                ),
                should_retry=False,
            )

        # Can retry?
        if retry_count < self.max_retries:
            self._total_retries += 1
            weak_info = f", {len(weak_chapters)} chương yếu" if weak_chapters else ""
            return QualityGateResult(
                passed=False, overall_score=overall, weak_chapters=weak_chapters,
                message=f"Quality gate RETRY: {overall:.1f}/5.0 < {self.gate_threshold}{weak_info}. Thử lại lần {retry_count + 1}.",
                should_retry=True,
            )

        # Hard stop — retries exhausted
        return QualityGateResult(
            passed=False, overall_score=overall, weak_chapters=weak_chapters,
            message=f"Quality gate FAILED: {overall:.1f}/5.0 < {self.gate_threshold}. Đã thử {retry_count} lần. Tiếp tục với kết quả hiện tại.",
            should_retry=False,
        )
