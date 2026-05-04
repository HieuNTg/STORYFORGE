"""Integration smoke for handoff gate wiring in `pipeline.orchestrator_layers`.

The orchestrator is heavy (LLM clients, plugin manager, etc.) so we don't run
the full pipeline. We import the module, exercise the gate hand-off branch
directly with a stubbed envelope dict, and verify both lax and strict paths.
"""

from __future__ import annotations

import logging

import pytest

from models.handoff_schemas import L1Handoff, SignalHealth
from pipeline.handoff_gate import HandoffValidationError, enforce_handoff


def _envelope_dict(broken_signal: str | None = None) -> dict:
    statuses = {
        "conflict_web": "ok",
        "foreshadowing_plan": "ok",
        "arc_waypoints": "ok",
        "threads": "ok",
        "voice_fingerprints": "ok",
    }
    if broken_signal:
        statuses[broken_signal] = "extraction_failed"
    env = L1Handoff(
        story_id="Lý Huyền saga",
        num_chapters=2,
        signal_health={
            name: SignalHealth(status=status)  # type: ignore[arg-type]
            for name, status in statuses.items()
        },
    )
    return env.model_dump()


def test_orchestrator_module_imports_cleanly():
    """Smoke: gate wiring doesn't break orchestrator import."""
    import pipeline.orchestrator_layers as ol

    assert hasattr(ol, "run_full_pipeline")


def test_gate_default_mode_returns_envelope_with_warnings(monkeypatch, caplog):
    """In lax mode, an `extraction_failed` signal warns but does not raise."""
    monkeypatch.setenv("STORYFORGE_HANDOFF_STRICT", "0")
    raw = _envelope_dict(broken_signal="conflict_web")
    rehydrated = L1Handoff.model_validate(raw)

    caplog.set_level(logging.WARNING, logger="storyforge.handoff_gate")
    out = enforce_handoff(rehydrated)

    assert out is rehydrated
    health_payload = {
        sig: h.model_dump() for sig, h in out.signal_health.items()
    }
    assert health_payload["conflict_web"]["status"] == "extraction_failed"
    assert any("handoff_degraded" in rec.message for rec in caplog.records)


def test_gate_strict_mode_raises_via_env(monkeypatch):
    monkeypatch.setenv("STORYFORGE_HANDOFF_STRICT", "1")
    raw = _envelope_dict(broken_signal="voice_fingerprints")
    rehydrated = L1Handoff.model_validate(raw)
    with pytest.raises(HandoffValidationError) as exc_info:
        enforce_handoff(rehydrated)
    assert "voice_fingerprints" in exc_info.value.blockers


def test_pipeline_output_carries_handoff_health():
    """`PipelineOutput.handoff_health` accepts the dict the orchestrator builds."""
    from models.schemas import PipelineOutput

    raw = _envelope_dict(broken_signal="threads")
    env = L1Handoff.model_validate(raw)
    health = {sig: h.model_dump() for sig, h in env.signal_health.items()}

    output = PipelineOutput(handoff_health=health)
    assert output.handoff_health["threads"]["status"] == "extraction_failed"
    assert output.handoff_health["conflict_web"]["status"] == "ok"
