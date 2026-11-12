"""First run without an API key fails fast with a clear message.

Before, starting a story with no key configured ran into the provider and
ended in a generic error. The run and forge endpoints now answer 400
``{"error": {"code": "api_key_missing", "message": ...}}`` when no usable key
exists at all. A local endpoint (loopback, host.docker.internal, a private
LAN address) needs no key, and any key anywhere (primary, layer, pool,
fallback profile) counts as usable.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from config import ConfigManager

def has_usable_llm_key(llm):
    from services.llm.provider_config_keys import has_usable_llm_key as check

    return check(llm)


# conftest switches the guard off for route tests; these test the guard.
pytestmark = pytest.mark.llm_key_guard

MESSAGE = "Set an API key in Settings → API Keys"


@pytest.fixture
def no_key(monkeypatch):
    """The live config with every key empty and a remote primary endpoint."""
    llm = ConfigManager().llm
    for field in ("api_key", "layer1_api_key", "layer2_api_key"):
        monkeypatch.setattr(llm, field, "")
    for field in ("layer1_base_url", "layer2_base_url", "cheap_base_url"):
        monkeypatch.setattr(llm, field, "")
    monkeypatch.setattr(llm, "base_url", "https://api.openai.com/v1")
    monkeypatch.setattr(llm, "api_keys", [])
    monkeypatch.setattr(llm, "fallback_models", [])
    for env in ("ANTHROPIC_API_KEY", "GOOGLE_AI_API_KEY", "ZAI_API_KEY"):
        monkeypatch.delenv(env, raising=False)
    return llm


@pytest.fixture
def api(no_key):
    from app import create_app

    c = TestClient(create_app())
    c.get("/api/health")
    c.headers["x-csrf-token"] = c.cookies.get("csrf_token")
    return c


def _assert_key_missing(r):
    assert r.status_code == 400, r.text
    assert r.json() == {"error": {"code": "api_key_missing", "message": MESSAGE}}


# --- the rule ------------------------------------------------------------------


def test_no_key_and_remote_endpoint_is_unusable(no_key):
    assert has_usable_llm_key(no_key) is False


@pytest.mark.parametrize(
    "base_url",
    [
        "http://localhost:11434/v1",
        "http://127.0.0.1:1234/v1",
        "http://[::1]:8000/v1",
        "http://host.docker.internal:11434/v1",
        "http://192.168.1.20:11434/v1",
    ],
)
def test_local_endpoint_needs_no_key(no_key, monkeypatch, base_url):
    monkeypatch.setattr(no_key, "base_url", base_url)
    assert has_usable_llm_key(no_key) is True


def test_lookalike_local_name_is_remote(no_key, monkeypatch):
    monkeypatch.setattr(no_key, "base_url", "https://localhost.evil.example/v1")
    assert has_usable_llm_key(no_key) is False


@pytest.mark.parametrize(
    "field,value",
    [
        ("api_key", "sk-primary"),
        ("layer1_api_key", "sk-l1"),
        ("layer2_api_key", "sk-l2"),
        ("api_keys", ["sk-pool"]),
        ("api_keys", [{"key": "sk-pool", "base_url": "https://x.example/v1"}]),
        ("fallback_models", [{"model": "m", "base_url": "https://x.example/v1", "api_key": "sk-fb"}]),
        ("fallback_models", [{"model": "m", "base_url": "http://localhost:11434/v1"}]),
        ("layer1_base_url", "http://localhost:11434/v1"),
    ],
)
def test_any_key_or_local_profile_is_usable(no_key, monkeypatch, field, value):
    monkeypatch.setattr(no_key, field, value)
    assert has_usable_llm_key(no_key) is True


def test_env_provider_key_is_usable(no_key, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")
    assert has_usable_llm_key(no_key) is True


# --- the endpoints -------------------------------------------------------------


def test_pipeline_run_without_key_is_400(api):
    r = api.post("/api/pipeline/run", json={"idea": "A long enough story idea here"})
    _assert_key_missing(r)


def test_forge_sentence_without_key_is_400(api, monkeypatch):
    monkeypatch.setattr(ConfigManager().pipeline, "enable_sentence_forge", True)
    r = api.post("/api/forge/sentence", json={"sentenceIdea": "A girl finds a door in the sea."})
    _assert_key_missing(r)
    r = api.post(
        "/api/forge/sentence/stream", json={"sentenceIdea": "A girl finds a door in the sea."}
    )
    _assert_key_missing(r)


def test_pipeline_run_with_local_endpoint_passes_the_guard(api, no_key, monkeypatch):
    """A local endpoint is not stopped by the guard: the idea check answers."""
    monkeypatch.setattr(no_key, "base_url", "http://localhost:11434/v1")
    r = api.post("/api/pipeline/run", json={"idea": "short"})
    assert r.status_code == 200
    assert "too short" in r.text
