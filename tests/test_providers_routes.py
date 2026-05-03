"""Tests for /api/providers/health — Piece M.

Covers FallbackManager.health_snapshot(), LLMClient.rate_limit_snapshot(),
and the GET /providers/health endpoint. Mocks global state so tests are
hermetic.
"""

from __future__ import annotations

import re
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.llm.model_fallback import (
    ModelFallbackManager,
    reset_fallback_manager,
)


# ──────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_state():
    """Reset fallback manager + LLMClient between tests so state doesn't leak."""
    reset_fallback_manager()
    from services.llm.client import LLMClient
    LLMClient.reset()
    yield
    reset_fallback_manager()
    LLMClient.reset()


def _build_test_app() -> FastAPI:
    app = FastAPI()
    from api.provider_status_routes import router
    app.include_router(router, prefix="/api")
    return app


# ──────────────────────────────────────────────────────────────────────────
# FallbackManager.health_snapshot
# ──────────────────────────────────────────────────────────────────────────


def test_health_snapshot_empty_when_no_calls():
    fm = ModelFallbackManager()
    snap = fm.health_snapshot()
    assert snap == []


def test_health_snapshot_reflects_failure_state():
    fm = ModelFallbackManager()
    # 3 consecutive failures with an error class
    fm.mark_unhealthy("gpt-4o", error_class="RateLimitError")
    fm.mark_unhealthy("gpt-4o", error_class="RateLimitError")
    fm.mark_unhealthy("gpt-4o", error_class="RateLimitError")

    snap = fm.health_snapshot()
    assert len(snap) == 1
    entry = snap[0]
    assert entry["model"] == "gpt-4o"
    assert entry["healthy"] is False
    assert entry["consecutive_failures"] == 3
    assert entry["last_error_class"] == "RateLimitError"
    assert entry["cooldown_remaining_s"] >= 0


def test_health_snapshot_resets_on_recovery():
    fm = ModelFallbackManager()
    fm.mark_unhealthy("claude-3", error_class="APIError")
    fm.mark_unhealthy("claude-3", error_class="APIError")
    fm.mark_healthy("claude-3")

    snap = fm.health_snapshot()
    entry = next(e for e in snap if e["model"] == "claude-3")
    assert entry["healthy"] is True
    assert entry["consecutive_failures"] == 0
    assert entry["last_error_class"] is None


def test_health_snapshot_includes_latency():
    fm = ModelFallbackManager()
    fm.record_latency("gemini-pro", 425.0)
    fm.record_latency("gemini-pro", 510.0)

    snap = fm.health_snapshot()
    entry = next(e for e in snap if e["model"] == "gemini-pro")
    assert entry["last_latency_ms"] == 510
    assert entry["avg_latency_ms"] is not None


# ──────────────────────────────────────────────────────────────────────────
# LLMClient.rate_limit_snapshot
# ──────────────────────────────────────────────────────────────────────────


def test_rate_limit_snapshot_redacts_keys():
    from services.llm.client import LLMClient
    client = LLMClient()
    fake_key = "sk-supersecretvalue1234567890"
    client._rate_limited_keys[fake_key] = time.time() + 60.0

    snap = client.rate_limit_snapshot()
    assert len(snap["rate_limited_keys"]) == 1
    entry = snap["rate_limited_keys"][0]
    # Actual key must not appear anywhere
    assert fake_key not in entry["key_id"]
    assert entry["key_id"].startswith("sk-sup")  # 6-char prefix preserved
    assert entry["key_id"].endswith("7890")      # 4-char suffix preserved
    assert entry["cooldown_remaining_s"] > 0


def test_rate_limit_snapshot_skips_expired():
    from services.llm.client import LLMClient
    client = LLMClient()
    client._rate_limited_keys["sk-already-expired-key-12345"] = time.time() - 10.0

    snap = client.rate_limit_snapshot()
    assert snap["rate_limited_keys"] == []


def test_rate_limit_snapshot_model_combo():
    from services.llm.client import LLMClient
    client = LLMClient()
    client._rate_limited_models["gpt-4o:sk-abcdef1234567890xyz"] = time.time() + 90.0

    snap = client.rate_limit_snapshot()
    assert len(snap["rate_limited_models"]) == 1
    rl = snap["rate_limited_models"][0]
    assert rl["model"] == "gpt-4o"
    assert rl["key_id"].startswith("sk-abc")
    assert rl["key_id"].endswith("0xyz")


# ──────────────────────────────────────────────────────────────────────────
# GET /api/providers/health endpoint
# ──────────────────────────────────────────────────────────────────────────


def test_health_endpoint_returns_200_empty():
    app = _build_test_app()
    client = TestClient(app)

    resp = client.get("/api/providers/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["providers"] == []
    assert body["rate_limited_keys"] == []
    assert body["rate_limited_models"] == []
    assert "snapshot_ts" in body


def test_health_endpoint_redacts_api_keys():
    """No actual key strings (sk-*, env-loaded values) should appear in JSON."""
    from services.llm.client import LLMClient
    from services.llm.model_fallback import get_fallback_manager

    fm = get_fallback_manager()
    fm.mark_unhealthy("gpt-4o", error_class="RateLimitError")

    cli = LLMClient()
    real_secret = "sk-DO-NOT-LEAK-abcdefghijklmnop"
    cli._rate_limited_keys[real_secret] = time.time() + 30.0
    cli._rate_limited_models[f"gpt-4o:{real_secret}"] = time.time() + 30.0

    app = _build_test_app()
    client = TestClient(app)
    resp = client.get("/api/providers/health")
    raw = resp.text

    # The raw key must NEVER appear anywhere in the response
    assert real_secret not in raw
    # Sanity check: no "sk-DO-NOT-LEAK" middle slug leaks either
    assert "DO-NOT-LEAK" not in raw
    # Generic sk- redaction sanity: full keys in this format shouldn't slip through
    assert not re.search(r"sk-[A-Za-z0-9-]{20,}", raw)


def test_health_endpoint_reflects_failures():
    from services.llm.model_fallback import get_fallback_manager

    fm = get_fallback_manager()
    fm.mark_unhealthy("gpt-4o", error_class="TimeoutError")
    fm.mark_unhealthy("gpt-4o", error_class="TimeoutError")
    fm.mark_unhealthy("gpt-4o", error_class="TimeoutError")

    app = _build_test_app()
    client = TestClient(app)
    resp = client.get("/api/providers/health")
    body = resp.json()

    gpt = next(p for p in body["providers"] if p["model"] == "gpt-4o")
    assert gpt["consecutive_failures"] == 3
    assert gpt["healthy"] is False
    assert gpt["last_error_class"] == "TimeoutError"
