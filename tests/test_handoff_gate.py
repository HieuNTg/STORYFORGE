"""Unit tests for `pipeline.handoff_gate` (Sprint 1, Phase 3)."""

from __future__ import annotations

import logging

import pytest

from models.handoff_schemas import (
    L1Handoff,
    NegotiatedChapterContract,
    SignalHealth,
)
from pipeline.handoff_gate import (
    HandoffValidationError,
    _compute_drama_ceiling,
    enforce_handoff,
    reconcile_contract,
    validate_handoff,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _envelope(signal_statuses: dict[str, str], story_id: str = "ly-huyen-saga") -> L1Handoff:
    return L1Handoff(
        story_id=story_id,
        num_chapters=3,
        signal_health={
            name: SignalHealth(status=status)  # type: ignore[arg-type]
            for name, status in signal_statuses.items()
        },
    )


def _all_ok() -> L1Handoff:
    return _envelope(
        {
            "conflict_web": "ok",
            "foreshadowing_plan": "ok",
            "arc_waypoints": "ok",
            "threads": "ok",
            "voice_fingerprints": "ok",
        }
    )


# ---------------------------------------------------------------------------
# validate_handoff
# ---------------------------------------------------------------------------

def test_validate_handoff_clean_envelope_returns_ok():
    ok, blockers, warnings = validate_handoff(_all_ok())
    assert ok is True
    assert blockers == []
    assert warnings == []


def test_validate_handoff_separates_blockers_from_warnings():
    env = _envelope(
        {
            "conflict_web": "ok",
            "foreshadowing_plan": "empty",         # warning
            "arc_waypoints": "extraction_failed",  # blocker
            "threads": "malformed",                # blocker
            "voice_fingerprints": "ok",
        }
    )
    ok, blockers, warnings = validate_handoff(env)
    assert ok is False
    assert set(blockers) == {"arc_waypoints", "threads"}
    assert warnings == ["foreshadowing_plan"]


# ---------------------------------------------------------------------------
# enforce_handoff
# ---------------------------------------------------------------------------

def test_enforce_handoff_strict_raises_on_blockers():
    env = _envelope(
        {
            "conflict_web": "extraction_failed",
            "foreshadowing_plan": "ok",
            "arc_waypoints": "ok",
            "threads": "ok",
            "voice_fingerprints": "ok",
        }
    )
    with pytest.raises(HandoffValidationError) as exc_info:
        enforce_handoff(env, strict=True)
    err = exc_info.value
    assert "conflict_web" in err.blockers
    assert err.envelope is env


def test_enforce_handoff_lax_logs_warning_and_returns_envelope(caplog):
    env = _envelope(
        {
            "conflict_web": "extraction_failed",
            "foreshadowing_plan": "ok",
            "arc_waypoints": "empty",
            "threads": "ok",
            "voice_fingerprints": "ok",
        }
    )
    caplog.set_level(logging.WARNING, logger="storyforge.handoff_gate")
    out = enforce_handoff(env, strict=False)
    assert out is env
    assert any(
        "handoff_degraded" in rec.message and rec.levelname == "WARNING"
        for rec in caplog.records
    )


def test_enforce_handoff_clean_envelope_logs_info(caplog):
    caplog.set_level(logging.INFO, logger="storyforge.handoff_gate")
    out = enforce_handoff(_all_ok(), strict=True)
    assert out.story_id == "ly-huyen-saga"
    assert any("handoff_validated" in rec.message for rec in caplog.records)


def test_enforce_handoff_env_strict_truthy_raises(monkeypatch):
    monkeypatch.setenv("STORYFORGE_HANDOFF_STRICT", "1")
    env = _envelope(
        {
            "conflict_web": "malformed",
            "foreshadowing_plan": "ok",
            "arc_waypoints": "ok",
            "threads": "ok",
            "voice_fingerprints": "ok",
        }
    )
    with pytest.raises(HandoffValidationError):
        enforce_handoff(env)  # strict=None → reads env


def test_enforce_handoff_env_strict_off_warns(monkeypatch, caplog):
    monkeypatch.setenv("STORYFORGE_HANDOFF_STRICT", "0")
    env = _envelope(
        {
            "conflict_web": "malformed",
            "foreshadowing_plan": "ok",
            "arc_waypoints": "ok",
            "threads": "ok",
            "voice_fingerprints": "ok",
        }
    )
    caplog.set_level(logging.WARNING, logger="storyforge.handoff_gate")
    out = enforce_handoff(env)
    assert out is env
    assert any("handoff_degraded" in rec.message for rec in caplog.records)


# ---------------------------------------------------------------------------
# reconcile_contract
# ---------------------------------------------------------------------------

def _contract(**overrides) -> NegotiatedChapterContract:
    base = dict(chapter_num=1, pacing_type="setup", drama_target=0.3)
    base.update(overrides)
    return NegotiatedChapterContract(**base)


def test_reconcile_contract_clamps_cooldown_above_threshold():
    c = _contract(chapter_num=5, pacing_type="cooldown", drama_target=0.8)
    out = reconcile_contract(c)
    assert out is not c
    assert out.drama_target == pytest.approx(0.4)
    assert out.reconciled is True
    assert any("cooldown" in w for w in out.reconciliation_warnings)


def test_reconcile_contract_raises_climax_below_threshold():
    c = _contract(chapter_num=7, pacing_type="climax", drama_target=0.5)
    out = reconcile_contract(c)
    assert out.drama_target == pytest.approx(0.75)
    assert out.reconciled is True
    assert any("climax" in w for w in out.reconciliation_warnings)


def test_reconcile_contract_warns_payoffs_without_causal_refs():
    c = _contract(
        chapter_num=4,
        pacing_type="rising",
        drama_target=0.55,
        payoffs_required=["seed_1"],
        causal_refs=[],
    )
    out = reconcile_contract(c)
    assert out.drama_target == pytest.approx(0.55)
    assert out.reconciled is True
    assert any("payoffs_required" in w and "seed_1" in w for w in out.reconciliation_warnings)


def test_reconcile_contract_clean_inputs_no_warnings():
    c = _contract(chapter_num=2, pacing_type="setup", drama_target=0.3)
    out = reconcile_contract(c)
    assert out is not c
    assert out.reconciled is True
    assert out.reconciliation_warnings == []
    assert out.drama_target == pytest.approx(0.3)


def test_reconcile_contract_does_not_mutate_input():
    c = _contract(chapter_num=5, pacing_type="cooldown", drama_target=0.9)
    _ = reconcile_contract(c)
    assert c.drama_target == pytest.approx(0.9)
    assert c.reconciled is False
    assert c.reconciliation_warnings == []


def test_reconcile_contract_payoff_with_matching_causal_ref_no_warning():
    c = _contract(
        chapter_num=6,
        pacing_type="rising",
        drama_target=0.6,
        payoffs_required=["seed_1"],
        causal_refs=["seed_1", "evt_x"],
    )
    out = reconcile_contract(c)
    assert out.reconciliation_warnings == []


# ---------------------------------------------------------------------------
# Sprint 3 P1 — drama_ceiling derivation + reconciliation warning
# ---------------------------------------------------------------------------

def test_compute_drama_ceiling_boundary():
    assert _compute_drama_ceiling(0.5, 0.15) == pytest.approx(0.65)


def test_compute_drama_ceiling_saturates_at_one():
    assert _compute_drama_ceiling(0.95, 0.20) == pytest.approx(1.0)


def test_compute_drama_ceiling_zero_target_returns_zero_sentinel():
    assert _compute_drama_ceiling(0.0, 0.15) == 0.0


def test_reconcile_contract_fills_drama_ceiling_from_target_plus_tolerance():
    c = _contract(chapter_num=2, pacing_type="rising", drama_target=0.5, drama_tolerance=0.15)
    out = reconcile_contract(c)
    assert out.drama_ceiling == pytest.approx(0.65)
    assert "drama_ceiling_unset_no_target" not in out.reconciliation_warnings


def test_reconcile_contract_drama_ceiling_clamps_at_one():
    c = _contract(chapter_num=8, pacing_type="climax", drama_target=0.95, drama_tolerance=0.20)
    out = reconcile_contract(c)
    assert out.drama_ceiling == pytest.approx(1.0)


def test_reconcile_contract_warns_when_drama_target_zero_post_simulation():
    c = _contract(chapter_num=1, pacing_type="setup", drama_target=0.0, drama_tolerance=0.15)
    out = reconcile_contract(c)
    assert out.drama_ceiling == 0.0
    assert "drama_ceiling_unset_no_target" in out.reconciliation_warnings
