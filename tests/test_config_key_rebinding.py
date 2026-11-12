"""Changing the provider host must not carry the stored API key along."""

import pytest

from config.config import ConfigManager


def _with_csrf(client):
    client.get("/api/health")
    client.headers["x-csrf-token"] = client.cookies.get("csrf_token")
    return client


@pytest.fixture
def client_with_key(client):
    _with_csrf(client)
    cfg = ConfigManager()
    cfg.llm.api_key = "sk-old"
    cfg.llm.base_url = "https://api.openai.com/v1"
    cfg.llm.cheap_base_url = ""
    cfg.llm.fallback_models = []
    cfg.save()
    return client


@pytest.fixture
def client_with_profile(client):
    _with_csrf(client)
    cfg = ConfigManager()
    cfg.llm.fallback_models = [
        {
            "name": "p",
            "base_url": "https://api.openai.com/v1",
            "api_key": "sk-prof",
            "model": "m",
            "enabled": True,
        }
    ]
    cfg.save()
    return client


def test_changing_host_clears_key(client_with_key):
    r = client_with_key.put("/api/config", json={"base_url": "https://evil.example/v1"})
    assert r.status_code == 200, r.text
    assert r.json()["key_cleared"] is True
    assert ConfigManager().llm.api_key == ""


def test_same_host_keeps_key(client_with_key):
    r = client_with_key.put("/api/config", json={"base_url": "https://api.openai.com/v2"})
    assert r.status_code == 200, r.text
    assert r.json().get("key_cleared") is not True
    assert ConfigManager().llm.api_key == "sk-old"


def test_new_host_with_new_key_keeps_new_key(client_with_key):
    r = client_with_key.put(
        "/api/config",
        json={"base_url": "https://openrouter.ai/api/v1", "api_key": "sk-new"},
    )
    assert r.status_code == 200, r.text
    assert r.json().get("key_cleared") is not True
    assert ConfigManager().llm.api_key == "sk-new"


def test_cheap_host_change_clears_shared_key(client_with_key):
    r = client_with_key.put(
        "/api/config", json={"cheap_base_url": "https://evil.example/v1"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["key_cleared"] is True
    assert ConfigManager().llm.api_key == ""


def test_cheap_host_same_as_primary_keeps_key(client_with_key):
    r = client_with_key.put(
        "/api/config", json={"cheap_base_url": "https://api.openai.com/v1"}
    )
    assert r.status_code == 200, r.text
    assert ConfigManager().llm.api_key == "sk-old"


def test_profile_host_change_clears_profile_key(client_with_profile):
    r = client_with_profile.put(
        "/api/config/profiles/0",
        json={"name": "p", "base_url": "https://evil.example/v1", "model": "m"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["key_cleared"] is True
    assert ConfigManager().llm.fallback_models[0]["api_key"] == ""


def test_profile_same_host_keeps_key(client_with_profile):
    r = client_with_profile.put(
        "/api/config/profiles/0",
        json={"name": "p", "base_url": "https://api.openai.com/v2", "model": "m"},
    )
    assert r.status_code == 200, r.text
    assert ConfigManager().llm.fallback_models[0]["api_key"] == "sk-prof"


def test_profile_host_change_with_new_key_keeps_new_key(client_with_profile):
    r = client_with_profile.put(
        "/api/config/profiles/0",
        json={
            "name": "p",
            "base_url": "https://openrouter.ai/api/v1",
            "api_key": "sk-new",
            "model": "m",
        },
    )
    assert r.status_code == 200, r.text
    assert ConfigManager().llm.fallback_models[0]["api_key"] == "sk-new"
