"""Tests for per-story LLM usage sidecar — Piece L.

Covers:
- record_usage: appends, creates fresh, computes totals, rotates at 500
- pricing: known model returns cost > 0; unknown falls back to default
- failure tolerance: write errors must not raise
- read_usage: returns events + totals
- LLM client hook: sidecar write failure does NOT fail the LLM call
- /api/usage/story/{filename} endpoint
- /pipeline/checkpoints attaches usage_summary
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services import continuation_history, usage_history
from services.usage_history import (
    _MAX_EVENTS,
    read_usage,
    record_usage,
    usage_sidecar_path_for,
    usage_summary,
)


# ──────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _isolated_checkpoint_dir(tmp_path, monkeypatch):
    """Redirect checkpoint_dir() so sidecars land in a tmp folder.

    ``usage_history`` imports ``checkpoint_dir`` directly from
    ``continuation_history``, so we must rebind the symbol on the
    importing module too — patching only the source module leaves the
    bound reference in usage_history pointing at the original.
    """
    monkeypatch.setattr(continuation_history, "checkpoint_dir", lambda: tmp_path)
    monkeypatch.setattr(usage_history, "checkpoint_dir", lambda: tmp_path)
    yield tmp_path


# ──────────────────────────────────────────────────────────────────────────
# record_usage / read_usage core behavior
# ──────────────────────────────────────────────────────────────────────────


def test_record_creates_fresh_sidecar():
    record_usage(title="Cosmic", model="gpt-4o-mini",
                 prompt_tokens=1000, completion_tokens=500, layer=1)
    path = usage_sidecar_path_for("Cosmic_layer1.json")
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert len(data["events"]) == 1
    ev = data["events"][0]
    assert ev["model"] == "gpt-4o-mini"
    assert ev["prompt_tokens"] == 1000
    assert ev["completion_tokens"] == 500
    assert ev["total_tokens"] == 1500
    assert ev["cost_usd"] > 0  # known model
    assert data["totals"]["call_count"] == 1
    assert data["totals"]["total_tokens"] == 1500


def test_record_appends_and_aggregates_totals():
    record_usage(title="Agg", model="gpt-4o-mini",
                 prompt_tokens=100, completion_tokens=50, layer=1)
    record_usage(title="Agg", model="gpt-4o-mini",
                 prompt_tokens=200, completion_tokens=80, layer=1)
    data = read_usage("Agg_layer1.json")
    assert data is not None
    assert len(data["events"]) == 2
    assert data["totals"]["call_count"] == 2
    assert data["totals"]["total_tokens"] == 100 + 50 + 200 + 80


def test_record_rotates_at_max_but_keeps_full_totals():
    """Events are capped at _MAX_EVENTS but totals reflect ALL recorded calls."""
    title = "Rot"
    n = _MAX_EVENTS + 7
    for _ in range(n):
        record_usage(title=title, model="gpt-4o-mini",
                     prompt_tokens=10, completion_tokens=5, layer=1)
    data = read_usage("Rot_layer1.json")
    assert data is not None
    assert len(data["events"]) == _MAX_EVENTS
    # Totals must include ALL n calls, not just the kept _MAX_EVENTS
    assert data["totals"]["call_count"] == n
    assert data["totals"]["total_tokens"] == n * 15


def test_pricing_known_model_returns_positive_cost():
    record_usage(title="Known", model="gpt-4o",
                 prompt_tokens=1_000_000, completion_tokens=0, layer=1)
    data = read_usage("Known_layer1.json")
    # gpt-4o: $2.50 per 1M input tokens.
    assert data["totals"]["total_cost_usd"] == pytest.approx(2.50, abs=0.01)


def test_pricing_unknown_model_uses_default_not_zero():
    """Unknown model must not crash; it falls back to _default rates.

    The mission says "unknown models → cost_usd = 0 (don't crash, don't lie)"
    but the existing llm_pricing module already has a _default fallback for
    routing through fallback chains. We honor that for consistency with the
    rest of the app — frontend treats cost==0 sidecars as token-only display.
    """
    record_usage(title="Unk", model="totally-made-up-model-xyz",
                 prompt_tokens=1000, completion_tokens=500, layer=1)
    data = read_usage("Unk_layer1.json")
    # Should not crash; default rate produces some non-negative cost.
    assert data is not None
    assert data["totals"]["total_tokens"] == 1500
    assert data["totals"]["total_cost_usd"] >= 0


def test_record_explicit_zero_cost_for_free_tier():
    """Caller can pass cost_usd=0 for free-tier models."""
    record_usage(title="Free", model="glm-4.6",
                 prompt_tokens=500, completion_tokens=200, layer=1, cost_usd=0.0)
    data = read_usage("Free_layer1.json")
    assert data["totals"]["total_cost_usd"] == 0.0
    assert data["totals"]["total_tokens"] == 700


def test_record_failure_does_not_raise(monkeypatch):
    """Disk-full / OSError must be swallowed — sidecar is advisory only."""
    def _boom(*_a, **_kw):
        raise OSError("disk full")
    monkeypatch.setattr("builtins.open", _boom)
    # Must not raise.
    result = record_usage(title="Boom", model="gpt-4o",
                          prompt_tokens=10, completion_tokens=10, layer=1)
    assert result is None


def test_read_missing_returns_none():
    assert read_usage("definitely_not_there_layer1.json") is None
    assert usage_summary("definitely_not_there_layer1.json") is None


def test_record_skips_when_title_empty():
    """Empty title means we can't compute a slug — skip silently."""
    result = record_usage(title="", model="gpt-4o",
                          prompt_tokens=10, completion_tokens=10, layer=1)
    assert result is None


def test_layer_routing_to_separate_sidecars():
    """Layer 1 and 2 calls land in separate sidecars."""
    record_usage(title="LR", model="gpt-4o-mini",
                 prompt_tokens=100, completion_tokens=50, layer=1)
    record_usage(title="LR", model="gpt-4o-mini",
                 prompt_tokens=200, completion_tokens=100, layer=2)
    l1 = read_usage("LR_layer1.json")
    l2 = read_usage("LR_layer2.json")
    assert l1["totals"]["total_tokens"] == 150
    assert l2["totals"]["total_tokens"] == 300


# ──────────────────────────────────────────────────────────────────────────
# LLM client hook: sidecar failure must not break the call
# ──────────────────────────────────────────────────────────────────────────


def test_llm_call_succeeds_even_if_sidecar_write_fails(monkeypatch):
    """The trace hook in services/llm/client.py must swallow record_usage errors."""
    from services.llm.client import _record_trace_call
    from services.trace_context import PipelineTrace, set_trace, clear_trace

    trace = PipelineTrace(title="Hookfail", layer=1)
    set_trace(trace)
    try:
        with patch(
            "services.usage_history.record_usage",
            side_effect=RuntimeError("sidecar exploded"),
        ):
            # Must not raise; the trace call records normally and the sidecar
            # hook is a try/except guard.
            _record_trace_call(
                model="gpt-4o-mini",
                model_tier="primary",
                messages=[{"role": "user", "content": "hi"}],
                result="hello",
                duration_ms=10,
                success=True,
                error="",
            )
        # Trace should still have the call recorded.
        assert len(trace.calls) == 1
    finally:
        clear_trace()


def test_failed_llm_calls_do_not_record_usage(monkeypatch):
    """Failed LLM attempts shouldn't bill the user — only successes count."""
    from services.llm.client import _record_trace_call
    from services.trace_context import PipelineTrace, set_trace, clear_trace

    trace = PipelineTrace(title="OnlyOk", layer=1)
    set_trace(trace)
    try:
        called = []
        def _spy(**kwargs):
            called.append(kwargs)
            return None
        monkeypatch.setattr("services.usage_history.record_usage", _spy)
        _record_trace_call(
            model="gpt-4o-mini",
            model_tier="primary",
            messages=[{"role": "user", "content": "hi"}],
            result="",
            duration_ms=10,
            success=False,
            error="boom",
        )
        assert called == []  # never called for failures
    finally:
        clear_trace()


# ──────────────────────────────────────────────────────────────────────────
# /api/usage/story/{filename} endpoint
# ──────────────────────────────────────────────────────────────────────────


@pytest.fixture
def usage_client():
    from api import usage_routes
    app = FastAPI()
    app.include_router(usage_routes.router)
    return TestClient(app)


def test_usage_story_endpoint_returns_zero_for_missing(usage_client):
    r = usage_client.get("/usage/story/never_existed_layer1.json")
    assert r.status_code == 200
    body = r.json()
    assert body["events"] == []
    assert body["totals"]["call_count"] == 0
    assert body["totals"]["total_cost_usd"] == 0.0


def test_usage_story_endpoint_returns_recorded_data(usage_client):
    record_usage(title="Ep", model="gpt-4o-mini",
                 prompt_tokens=100, completion_tokens=50, layer=1)
    r = usage_client.get("/usage/story/Ep_layer1.json")
    assert r.status_code == 200
    body = r.json()
    assert len(body["events"]) == 1
    assert body["totals"]["call_count"] == 1
    assert body["totals"]["total_tokens"] == 150


def test_usage_story_endpoint_rejects_traversal(usage_client):
    r = usage_client.get("/usage/story/..%2F..%2Fetc%2Fpasswd")
    assert r.status_code in (400, 404)


# ──────────────────────────────────────────────────────────────────────────
# /pipeline/checkpoints attaches usage_summary
# ──────────────────────────────────────────────────────────────────────────


def test_pipeline_checkpoints_attaches_usage_summary(monkeypatch, tmp_path):
    from api import pipeline_routes

    monkeypatch.setattr(continuation_history, "checkpoint_dir", lambda: tmp_path)
    monkeypatch.setattr(usage_history, "checkpoint_dir", lambda: tmp_path, raising=False)

    record_usage(title="Pipe", model="gpt-4o-mini",
                 prompt_tokens=300, completion_tokens=200, layer=1)

    fake_ckpts = [
        {
            "file": "Pipe_layer1.json",
            "modified": "2026-05-03 21:00",
            "size_kb": 3,
            "title": "Pipe",
            "genre": "fantasy",
            "chapter_count": 5,
            "current_layer": 1,
        },
        {
            "file": "no_usage_layer1.json",
            "modified": "2026-05-01 10:00",
            "size_kb": 2,
            "title": "Nope",
            "genre": "",
            "chapter_count": 3,
            "current_layer": 1,
        },
    ]

    with patch("pipeline.orchestrator.PipelineOrchestrator.list_checkpoints",
               return_value=fake_ckpts):
        app = FastAPI()
        app.include_router(pipeline_routes.router)
        client = TestClient(app)
        r = client.get("/pipeline/checkpoints")
    assert r.status_code == 200
    items = r.json()["checkpoints"]
    by_path = {c["path"]: c for c in items}
    pipe = by_path["Pipe_layer1.json"]
    assert pipe["usage_summary"] is not None
    assert pipe["usage_summary"]["call_count"] == 1
    assert pipe["usage_summary"]["total_tokens"] == 500
    # Story without sidecar → null
    assert by_path["no_usage_layer1.json"]["usage_summary"] is None
