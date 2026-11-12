"""Saved keys and preset model lists are matched by full origin, not hostname.

``_stored_key_for`` used to hand a saved key to any URL on the same host, so
``http://`` (downgrade) or another port on that host received it. And
``_preset_models_for`` returned Ollama's list (localhost:11434) for LM Studio at
localhost:1234. Both now compare (scheme, host, port-or-default), the same rule
``_key_survives`` applies when base_url changes.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from api import config_routes


@pytest.fixture
def saved(monkeypatch):
    """A config with a primary key on https://llm.example.com and a fallback
    profile on a local server at localhost:11434."""
    cfg = SimpleNamespace(
        llm=SimpleNamespace(
            base_url="https://llm.example.com/v1",
            api_key="sk-primary",
            fallback_models=[
                {"base_url": "http://localhost:11434/v1", "api_key": "ollama-key"}
            ],
        )
    )
    monkeypatch.setattr(config_routes, "ConfigManager", lambda: cfg)
    return cfg


def test_stored_key_same_origin_is_returned(saved):
    assert config_routes._stored_key_for("https://llm.example.com/v1") == "sk-primary"
    # Explicit default port is the same origin.
    assert config_routes._stored_key_for("https://llm.example.com:443/other") == "sk-primary"
    assert config_routes._stored_key_for("http://localhost:11434/v1") == "ollama-key"


def test_stored_key_not_sent_over_http(saved):
    assert config_routes._stored_key_for("http://llm.example.com/v1") == ""


def test_stored_key_not_sent_to_another_port(saved):
    assert config_routes._stored_key_for("https://llm.example.com:8443/v1") == ""
    assert config_routes._stored_key_for("http://localhost:1234/v1") == ""


def test_ollama_presets_not_returned_for_lm_studio(monkeypatch):
    monkeypatch.delenv("STORYFORGE_IN_CONTAINER", raising=False)
    ollama = config_routes._preset_models_for("http://localhost:11434/v1")
    assert ollama, "precondition: the Ollama card has a curated list"
    assert config_routes._preset_models_for("http://localhost:1234/v1") == []


def test_preset_models_need_matching_scheme():
    assert config_routes._preset_models_for("https://api.openai.com/v1/")
    assert config_routes._preset_models_for("http://api.openai.com/v1/") == []
