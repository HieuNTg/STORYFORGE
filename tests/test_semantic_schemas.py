"""Unit tests for `models/semantic_schemas.py` (Sprint 2, P1)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from models.semantic_schemas import (
    OUTLINE_METRIC_WEIGHTS,
    SEMANTIC_VERIFICATION_VERSION,
    ChapterSemanticFindings,
    OutlineMetrics,
    SemanticPayoffMatch,
    StructuralFinding,
    StructuralFindingType,
)


# ---------------------------------------------------------------------------
# SemanticPayoffMatch
# ---------------------------------------------------------------------------


class TestSemanticPayoffMatch:
    def _valid_kwargs(self, **overrides) -> dict:
        base = dict(
            seed_id="seed-1",
            chapter_num=3,
            role="payoff",
            matched=True,
            confidence=0.71,
            threshold_used=0.62,
            matched_span="hắn rút kiếm trước cổng thành",
            method="embedding",
        )
        base.update(overrides)
        return base

    def test_valid_match(self) -> None:
        m = SemanticPayoffMatch(**self._valid_kwargs())
        assert m.matched is True
        assert m.confidence == pytest.approx(0.71)
        assert m.method == "embedding"

    def test_confidence_out_of_range_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SemanticPayoffMatch(**self._valid_kwargs(confidence=1.5))
        with pytest.raises(ValidationError):
            SemanticPayoffMatch(**self._valid_kwargs(confidence=-0.1))

    def test_threshold_out_of_range_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SemanticPayoffMatch(**self._valid_kwargs(threshold_used=2.0))

    def test_invalid_role_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SemanticPayoffMatch(**self._valid_kwargs(role="bogus"))

    def test_invalid_method_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SemanticPayoffMatch(**self._valid_kwargs(method="LLM"))

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            SemanticPayoffMatch(**self._valid_kwargs(extra="nope"))

    def test_frozen_immutable(self) -> None:
        m = SemanticPayoffMatch(**self._valid_kwargs())
        with pytest.raises(ValidationError):
            m.confidence = 0.5  # type: ignore[misc]

    def test_status_matched(self) -> None:
        m = SemanticPayoffMatch(**self._valid_kwargs(matched=True, confidence=0.8))
        assert m.status == "matched"

    def test_status_weak(self) -> None:
        # Below threshold but within 0.05 of it.
        m = SemanticPayoffMatch(
            **self._valid_kwargs(matched=False, confidence=0.59, threshold_used=0.62)
        )
        assert m.status == "weak"

    def test_status_missed(self) -> None:
        m = SemanticPayoffMatch(
            **self._valid_kwargs(matched=False, confidence=0.10, threshold_used=0.62)
        )
        assert m.status == "missed"

    def test_default_method_is_embedding(self) -> None:
        kwargs = self._valid_kwargs()
        kwargs.pop("method")
        m = SemanticPayoffMatch(**kwargs)
        assert m.method == "embedding"

    def test_keyword_fallback_method_accepted(self) -> None:
        m = SemanticPayoffMatch(**self._valid_kwargs(method="keyword_fallback"))
        assert m.method == "keyword_fallback"


# ---------------------------------------------------------------------------
# StructuralFinding
# ---------------------------------------------------------------------------


class TestStructuralFinding:
    def _valid(self, **overrides) -> dict:
        base = dict(
            finding_type=StructuralFindingType.MISSING_KEY_EVENT,
            chapter_num=5,
            severity=0.85,
            description="Missing duel scene",
            fix_hint="Insert duel before chapter close",
            detection_method="embedding",
            evidence=("sentence-1", "sentence-2"),
            confidence=0.9,
        )
        base.update(overrides)
        return base

    def test_valid(self) -> None:
        f = StructuralFinding(**self._valid())
        assert f.finding_type is StructuralFindingType.MISSING_KEY_EVENT
        assert f.evidence == ("sentence-1", "sentence-2")

    def test_severity_out_of_range_rejected(self) -> None:
        with pytest.raises(ValidationError):
            StructuralFinding(**self._valid(severity=1.5))

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            StructuralFinding(**self._valid(extra_field="x"))

    def test_frozen(self) -> None:
        f = StructuralFinding(**self._valid())
        with pytest.raises(ValidationError):
            f.severity = 0.1  # type: ignore[misc]

    def test_invalid_detection_method_rejected(self) -> None:
        with pytest.raises(ValidationError):
            StructuralFinding(**self._valid(detection_method="magic"))

    def test_default_evidence_empty(self) -> None:
        kwargs = self._valid()
        kwargs.pop("evidence")
        f = StructuralFinding(**kwargs)
        assert f.evidence == ()

    def test_to_legacy_issue_missing_key_event(self) -> None:
        f = StructuralFinding(
            **self._valid(finding_type=StructuralFindingType.MISSING_KEY_EVENT)
        )
        legacy = f.to_legacy_issue()
        assert legacy.issue_type.value == "missing_key_event"
        assert legacy.severity == pytest.approx(0.85)
        assert legacy.chapter_number == 5
        assert legacy.fix_hint == "Insert duel before chapter close"

    def test_to_legacy_issue_missing_character_maps_to_wrong_characters(self) -> None:
        """Schema renamed MISSING_CHARACTER but legacy enum uses WRONG_CHARACTERS."""
        f = StructuralFinding(
            **self._valid(finding_type=StructuralFindingType.MISSING_CHARACTER)
        )
        legacy = f.to_legacy_issue()
        assert legacy.issue_type.value == "wrong_characters"

    def test_to_legacy_issue_pacing_violation(self) -> None:
        f = StructuralFinding(
            **self._valid(finding_type=StructuralFindingType.PACING_VIOLATION)
        )
        legacy = f.to_legacy_issue()
        assert legacy.issue_type.value == "pacing_violation"

    def test_to_legacy_issue_missed_arc_waypoint(self) -> None:
        f = StructuralFinding(
            **self._valid(finding_type=StructuralFindingType.MISSED_ARC_WAYPOINT)
        )
        legacy = f.to_legacy_issue()
        assert legacy.issue_type.value == "missed_arc_waypoint"


# ---------------------------------------------------------------------------
# OutlineMetrics
# ---------------------------------------------------------------------------


class TestOutlineMetrics:
    def _valid(self, **overrides) -> dict:
        base = dict(
            conflict_web_density=0.5,
            arc_trajectory_variance=0.4,
            pacing_distribution_skew=0.7,
            beat_coverage_ratio=0.8,
            character_screen_time_gini=0.3,
            overall_score=0.6,
            num_chapters=20,
            num_characters=5,
            num_conflict_nodes=8,
            num_seeds=12,
            num_arc_waypoints=4,
        )
        base.update(overrides)
        return base

    def test_valid(self) -> None:
        m = OutlineMetrics(**self._valid())
        assert m.schema_version == SEMANTIC_VERIFICATION_VERSION
        assert m.overall_score == pytest.approx(0.6)

    def test_component_out_of_range_rejected(self) -> None:
        with pytest.raises(ValidationError):
            OutlineMetrics(**self._valid(beat_coverage_ratio=1.5))

    def test_negative_count_rejected(self) -> None:
        with pytest.raises(ValidationError):
            OutlineMetrics(**self._valid(num_chapters=-1))

    def test_extra_field_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            OutlineMetrics(**self._valid(novel_metric=0.5))

    def test_frozen(self) -> None:
        m = OutlineMetrics(**self._valid())
        with pytest.raises(ValidationError):
            m.overall_score = 0.1  # type: ignore[misc]

    def test_weights_sum_to_one(self) -> None:
        assert sum(OUTLINE_METRIC_WEIGHTS.values()) == pytest.approx(1.0)

    def test_weights_have_expected_keys(self) -> None:
        assert set(OUTLINE_METRIC_WEIGHTS.keys()) == {
            "conflict_web_density",
            "arc_trajectory_variance",
            "pacing_distribution_skew",
            "beat_coverage_ratio",
            "character_screen_time_balance",
        }


# ---------------------------------------------------------------------------
# ChapterSemanticFindings
# ---------------------------------------------------------------------------


class TestChapterSemanticFindings:
    def test_default_empty_lists(self) -> None:
        f = ChapterSemanticFindings(chapter_num=1, embedding_model="m")
        assert f.payoff_matches == []
        assert f.structural_findings == []
        assert f.schema_version == SEMANTIC_VERIFICATION_VERSION

    def test_extra_field_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            ChapterSemanticFindings(
                chapter_num=1, embedding_model="m", junk="x"
            )

    def test_holds_match_and_finding(self) -> None:
        match = SemanticPayoffMatch(
            seed_id="s1",
            chapter_num=1,
            role="seed",
            matched=False,
            confidence=0.3,
            threshold_used=0.55,
        )
        finding = StructuralFinding(
            finding_type=StructuralFindingType.PACING_VIOLATION,
            chapter_num=1,
            severity=0.8,
            description="d",
            fix_hint="h",
            detection_method="embedding",
            confidence=0.7,
        )
        agg = ChapterSemanticFindings(
            chapter_num=1,
            embedding_model="m",
            payoff_matches=[match],
            structural_findings=[finding],
        )
        assert agg.payoff_matches[0].seed_id == "s1"
        assert agg.structural_findings[0].chapter_num == 1
