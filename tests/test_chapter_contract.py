"""Sprint 1 Task 3 — NegotiatedChapterContract, validator, retry flow unit tests."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from models.handoff_schemas import NegotiatedChapterContract
from models.schemas import SimulationEvent, SimulationResult
from pipeline.layer2_enhance.chapter_contract import (
    ContractValidation,
    aggregate_contract_stats,
    build_chapter_contracts,
    build_retry_hint,
    validate_chapter_against_contract,
)


class TestBuildChapterContracts:
    def test_empty_sim_result(self):
        sr = SimulationResult()
        contracts = build_chapter_contracts(sr, [1, 2, 3])
        assert set(contracts) == {1, 2, 3}
        # All fall back to baseline 0.6 when no tension_map/events
        for c in contracts.values():
            assert c.drama_target == 0.6
            assert c.escalation_events == []

    def test_drama_target_from_events(self):
        # Sprint 1 P5: tags use the strict `ch_<N>` form recognised by
        # extract_chapter_num. Substring-matching the loose Vietnamese
        # `"chương 2"` form is intentionally not supported (P2 fix).
        sr = SimulationResult(
            events=[
                SimulationEvent(
                    round_number=1, event_type="xung_đột",
                    characters_involved=["A"], description="Big fight",
                    drama_score=0.9, suggested_insertion="ch_2",
                ),
                SimulationEvent(
                    round_number=1, event_type="tiết_lộ",
                    characters_involved=["B"], description="Secret reveal",
                    drama_score=0.7, suggested_insertion="ch_2",
                ),
            ],
        )
        contracts = build_chapter_contracts(sr, [1, 2])
        assert contracts[2].drama_target == pytest.approx(0.8, abs=0.01)
        assert "Big fight" in contracts[2].escalation_events
        assert "Secret reveal" in contracts[2].escalation_events

    def test_tension_map_sets_baseline(self):
        sr = SimulationResult(tension_map={"A|B": 0.8, "C|D": 0.9})
        contracts = build_chapter_contracts(sr, [1])
        assert contracts[1].drama_target == pytest.approx(0.85, abs=0.01)

    def test_drama_suggestions_distributed(self):
        sr = SimulationResult(drama_suggestions=["s1", "s2", "s3"])
        contracts = build_chapter_contracts(sr, [1, 2, 3, 4])
        assert contracts[1].required_subtext == ["s1"]
        assert contracts[2].required_subtext == ["s2"]
        assert contracts[4].required_subtext == ["s1"]  # wraps


class TestValidator:
    def _llm(self, response: dict):
        llm = MagicMock()
        llm.generate_json.return_value = response
        return llm

    def _contract(self, chapter_num: int = 1, drama_target: float = 0.7, **kwargs) -> NegotiatedChapterContract:
        return NegotiatedChapterContract(chapter_num=chapter_num, pacing_type="rising", drama_target=drama_target, **kwargs)

    def test_passes_when_contract_met(self):
        llm = self._llm({
            "drama_actual": 0.75,
            "missing_escalations": [],
            "missing_subtext": [],
            "missing_causal_refs": [],
            "violated_patterns": [],
            "reason": "ok",
        })
        c = self._contract(1, 0.7, escalation_events=["fight"])
        v = validate_chapter_against_contract(llm, "content", c)
        assert v.passed is True
        assert v.compliance_score >= 0.95
        assert abs(v.drama_delta - 0.05) < 1e-6

    def test_fails_on_missing_escalation(self):
        llm = self._llm({
            "drama_actual": 0.7,
            "missing_escalations": ["confrontation"],
            "missing_subtext": [],
            "missing_causal_refs": [],
            "violated_patterns": [],
            "reason": "missing",
        })
        c = self._contract(1, 0.7, escalation_events=["confrontation"])
        v = validate_chapter_against_contract(llm, "content", c)
        assert v.passed is False
        assert "confrontation" in v.missing_escalations

    def test_fails_on_drama_outside_tolerance(self):
        llm = self._llm({
            "drama_actual": 0.3,  # target 0.8, delta -0.5 > tolerance 0.15
            "missing_escalations": [],
            "missing_subtext": [],
            "missing_causal_refs": [],
            "violated_patterns": [],
            "reason": "weak",
        })
        c = self._contract(1, 0.8)
        v = validate_chapter_against_contract(llm, "content", c)
        assert v.passed is False
        assert v.drama_delta < 0

    def test_llm_failure_marks_failed_gracefully(self):
        llm = MagicMock()
        llm.generate_json.side_effect = RuntimeError("LLM down")
        c = self._contract(5)
        v = validate_chapter_against_contract(llm, "content", c)
        assert v.passed is False
        assert "validation_llm_error" in v.reason
        assert v.chapter_number == 5

    def test_malformed_llm_response(self):
        # Returns string instead of dict — should degrade gracefully
        llm = self._llm("not a dict")
        c = self._contract(1, 0.6)
        v = validate_chapter_against_contract(llm, "x", c)
        assert v.drama_actual == 0.0
        assert v.passed is False


class TestRetryHint:
    def test_low_drama_hint(self):
        v = ContractValidation(chapter_number=1, drama_actual=0.3, drama_delta=-0.3)
        hint = build_retry_hint(v)
        assert "tăng" in hint.lower() or "Cần" in hint

    def test_high_drama_hint(self):
        v = ContractValidation(chapter_number=1, drama_actual=0.95, drama_delta=0.3)
        hint = build_retry_hint(v)
        assert "giảm" in hint.lower() or "melodrama" in hint.lower()

    def test_missing_escalations_listed(self):
        v = ContractValidation(
            chapter_number=1, missing_escalations=["fight", "reveal"],
        )
        assert "fight" in build_retry_hint(v)

    def test_violations_emphasized(self):
        v = ContractValidation(
            chapter_number=1, violated_patterns=["hero dies"],
        )
        assert "LOẠI BỎ" in build_retry_hint(v)


class TestAggregateStats:
    def test_empty(self):
        assert aggregate_contract_stats([]) == {"total_chapters": 0}

    def test_counts(self):
        validations = [
            ContractValidation(chapter_number=1, passed=True, compliance_score=1.0),
            ContractValidation(chapter_number=2, passed=True, retry_attempted=True, compliance_score=0.8),
            ContractValidation(chapter_number=3, passed=False, compliance_score=0.4),
        ]
        s = aggregate_contract_stats(validations)
        assert s["total_chapters"] == 3
        assert s["passed_first_try"] == 1
        assert s["passed_after_retry"] == 1
        assert s["failed_after_retry"] == 1
        assert s["avg_compliance"] == pytest.approx(0.733, abs=0.01)
