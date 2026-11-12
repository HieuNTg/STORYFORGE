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


# --- pool keys (llm.api_keys) must never be re-homed onto a new host -------


def _resolved_pairs():
    from services.llm.client import LLMClient

    c = object.__new__(LLMClient)
    c._rate_limited_keys = {}
    return {(e["api_key"], e["base_url"]) for e in c._resolve_api_keys(ConfigManager())}


@pytest.fixture
def client_with_pool(client_with_key):
    cfg = ConfigManager()
    cfg.llm.api_keys = ["sk-pool-bare", {"key": "sk-pool-dict"}]
    cfg.save()
    return client_with_key


def test_host_change_pins_pool_keys_to_old_host(client_with_pool):
    r = client_with_pool.put("/api/config", json={"base_url": "https://evil.example/v1"})
    assert r.status_code == 200, r.text
    assert r.json()["pool_keys_pinned"] == 2
    pairs = _resolved_pairs()
    old = "https://api.openai.com/v1"
    assert ("sk-pool-bare", old) in pairs and ("sk-pool-dict", old) in pairs
    assert not any(
        base == "https://evil.example/v1" and key.startswith("sk-")
        for key, base in pairs
    )


def test_same_origin_leaves_pool_untouched(client_with_pool):
    client_with_pool.put("/api/config", json={"base_url": "https://api.openai.com/v2"})
    assert ConfigManager().llm.api_keys == ["sk-pool-bare", {"key": "sk-pool-dict"}]


def test_add_profile_new_primary_pins_pool(client_with_pool):
    cfg = ConfigManager()
    cfg.llm.api_key = ""
    cfg.save()
    r = client_with_pool.post(
        "/api/config/profiles",
        json={
            "name": "n",
            "base_url": "https://openrouter.ai/api/v1",
            "api_key": "sk-or-new",
            "model": "m",
        },
    )
    assert r.status_code == 200, r.text
    pairs = _resolved_pairs()
    assert ("sk-pool-bare", "https://api.openai.com/v1") in pairs
    assert ("sk-pool-bare", "https://openrouter.ai/api/v1") not in pairs
    assert ("sk-pool-dict", "https://openrouter.ai/api/v1") not in pairs


# --- origin comparison: scheme and port count -------------------------------


@pytest.mark.parametrize(
    "old,new,survives",
    [
        ("http://localhost:11434/v1", "http://localhost:9999/v1", False),
        ("https://api.example.com/v1", "http://api.example.com/v1", False),
        ("https://api.example.com/v1", "https://api.example.com:443/v2", True),
        ("https://API.example.com./v1", "https://api.example.com/x", True),
        ("http://localhost:11434/v1", "http://localhost:11434/api", True),
    ],
)
def test_key_survives_origin(old, new, survives):
    from api.config_routes import _key_survives

    assert _key_survives(old, new) is survives


def test_port_change_clears_key(client):
    _with_csrf(client)
    cfg = ConfigManager()
    cfg.llm.api_key = "sk-old"
    cfg.llm.base_url = "http://localhost:11434/v1"
    cfg.save()
    r = client.put("/api/config", json={"base_url": "http://localhost:9999/v1"})
    assert r.status_code == 200, r.text
    assert r.json()["key_cleared"] is True and ConfigManager().llm.api_key == ""
