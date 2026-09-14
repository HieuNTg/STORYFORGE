"""Regression tests for POST /api/config/provider/models.

Before this, only OpenRouter (and the retired Kyma card) asked a provider what
it could run; OpenAI/Anthropic/Gemini served a hardcoded list that went stale
the week a provider shipped a new model, and an unknown endpoint returned
nothing at all. The route now does live discovery for every provider, and
falls back to the provider card's curated list instead of an empty dropdown.
"""

import pytest

from api import config_routes


@pytest.fixture(autouse=True)
def _no_network_validation(monkeypatch):
    """The URL allowlist/SSRF check is covered by its own test module."""
    monkeypatch.setattr(config_routes, "validate_base_url", lambda url: None)
    monkeypatch.setattr(config_routes, "_stored_key_for", lambda url: "")


def _body(base_url: str, api_key: str = ""):
    return config_routes.ModelsRequest(base_url=base_url, api_key=api_key)


class TestLiveDiscovery:
    def test_openai_asks_the_endpoint(self, monkeypatch):
        monkeypatch.setattr(
            config_routes,
            "_fetch_openai_compatible_models",
            lambda url, key: [{"id": "gpt-9-turbo", "label": "GPT-9 Turbo"}],
        )
        out = config_routes.get_provider_models(_body("https://api.openai.com/v1", "sk-x"))
        assert out["provider"] == "openai"
        assert out["models"] == [{"id": "gpt-9-turbo", "label": "GPT-9 Turbo"}]

    def test_anthropic_asks_the_endpoint(self, monkeypatch):
        monkeypatch.setattr(
            config_routes,
            "_fetch_openai_compatible_models",
            lambda url, key: [{"id": "claude-next", "label": "Claude Next"}],
        )
        out = config_routes.get_provider_models(
            _body("https://api.anthropic.com/v1/", "sk-ant-x")
        )
        assert out["models"][0]["id"] == "claude-next"

    def test_custom_endpoint_asks_the_endpoint(self, monkeypatch):
        monkeypatch.setattr(
            config_routes,
            "_fetch_openai_compatible_models",
            lambda url, key: [{"id": "my-llama", "label": "my-llama"}],
        )
        out = config_routes.get_provider_models(_body("https://llm.example.com/v1"))
        assert out["provider"] == "custom"
        assert out["models"][0]["id"] == "my-llama"


class TestFallbacks:
    def test_unreachable_endpoint_falls_back_to_the_card(self, monkeypatch):
        def boom(url, key):
            raise OSError("connection refused")

        monkeypatch.setattr(config_routes, "_fetch_openai_compatible_models", boom)
        out = config_routes.get_provider_models(_body("https://api.openai.com/v1"))
        assert "connection refused" in out["error"]
        # Curated list from config/presets.py, not an empty dropdown.
        assert any(m["id"] == "gpt-5.4-mini" for m in out["models"])

    def test_empty_reply_falls_back_to_the_card(self, monkeypatch):
        monkeypatch.setattr(
            config_routes, "_fetch_openai_compatible_models", lambda url, key: []
        )
        out = config_routes.get_provider_models(
            _body("https://generativelanguage.googleapis.com/v1beta/openai/")
        )
        assert out["provider"] == "gemini"
        assert any(m["id"] == "gemini-3.5-flash" for m in out["models"])

    def test_unknown_host_has_no_card_to_fall_back_to(self, monkeypatch):
        def boom(url, key):
            raise OSError("nope")

        monkeypatch.setattr(config_routes, "_fetch_openai_compatible_models", boom)
        out = config_routes.get_provider_models(_body("https://who.example.com/v1"))
        assert out["models"] == []


class TestStoredKeyReuse:
    def test_saved_key_is_used_when_the_client_sends_none(self, monkeypatch):
        monkeypatch.setattr(config_routes, "_stored_key_for", lambda url: "saved-key")
        seen = {}

        def capture(url, key):
            seen["key"] = key
            return [{"id": "m", "label": "m"}]

        monkeypatch.setattr(config_routes, "_fetch_openai_compatible_models", capture)
        config_routes.get_provider_models(_body("https://api.openai.com/v1"))
        assert seen["key"] == "saved-key"

    def test_typed_key_wins_over_the_saved_one(self, monkeypatch):
        monkeypatch.setattr(config_routes, "_stored_key_for", lambda url: "saved-key")
        seen = {}

        def capture(url, key):
            seen["key"] = key
            return [{"id": "m", "label": "m"}]

        monkeypatch.setattr(config_routes, "_fetch_openai_compatible_models", capture)
        config_routes.get_provider_models(_body("https://api.openai.com/v1", "typed-key"))
        assert seen["key"] == "typed-key"


class TestPresetLookup:
    def test_matches_by_host_not_by_exact_url(self):
        # A user pointing the OpenAI card at .../v1/ (trailing slash, different
        # path) must still get that card's models back.
        models = config_routes._preset_models_for("https://api.openai.com/v1/")
        assert any(m["id"] == "gpt-5.4-mini" for m in models)

    def test_unknown_host_returns_nothing(self):
        assert config_routes._preset_models_for("https://nope.example.com/v1") == []
