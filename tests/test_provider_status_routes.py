"""Route tests for api/provider_status_routes.py.

Covers the provider-status endpoints that test_providers_routes.py (health
only) leaves untested: /status, /status/{p}, /models/{p}, /refresh,
/quota-check, /fallbacks — plus the _get_api_keys_from_config helper.
The provider status manager is mocked so tests stay hermetic.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.provider_status_routes import _get_api_keys_from_config


def _client() -> TestClient:
    app = FastAPI()
    from api.provider_status_routes import router

    app.include_router(router, prefix="/api")
    return TestClient(app)


def _cfg(base_url: str, api_key: str = "sk-primary", fallbacks=None):
    return SimpleNamespace(
        llm=SimpleNamespace(
            base_url=base_url, api_key=api_key, fallback_models=fallbacks or []
        )
    )


def _patched(mgr, api_keys):
    """Patch the lazily imported manager and the config key helper."""
    return (
        patch(
            "services.llm.provider_status.get_provider_status_manager",
            return_value=mgr,
        ),
        patch(
            "api.provider_status_routes._get_api_keys_from_config",
            return_value=api_keys,
        ),
    )


class TestGetApiKeysFromConfig:
    def test_detects_openrouter_from_base_url(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_AI_API_KEY", raising=False)
        monkeypatch.delenv("ZAI_API_KEY", raising=False)
        with patch(
            "config.ConfigManager",
            return_value=_cfg("https://openrouter.ai/api/v1"),
        ):
            keys = _get_api_keys_from_config()
        assert keys == {"openrouter": "sk-primary"}

    def test_unknown_base_url_defaults_to_openai(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_AI_API_KEY", raising=False)
        monkeypatch.delenv("ZAI_API_KEY", raising=False)
        with patch(
            "config.ConfigManager",
            return_value=_cfg("https://api.openai.com/v1"),
        ):
            keys = _get_api_keys_from_config()
        assert keys == {"openai": "sk-primary"}

    def test_fallback_models_add_secondary_keys(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_AI_API_KEY", raising=False)
        monkeypatch.delenv("ZAI_API_KEY", raising=False)
        fallbacks = [
            {"base_url": "https://api.anthropic.com", "api_key": "sk-ant"},
            {"base_url": "https://api.anthropic.com", "api_key": "sk-ant-2"},
            {"base_url": "https://other.example.com", "api_key": ""},
            "not-a-dict",
        ]
        with patch(
            "config.ConfigManager",
            return_value=_cfg("https://api.openai.com/v1", fallbacks=fallbacks),
        ):
            keys = _get_api_keys_from_config()
        # setdefault keeps the first anthropic key; empty/non-dict entries skipped
        assert keys == {"openai": "sk-primary", "anthropic": "sk-ant"}

    def test_env_var_fills_missing_provider(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-env-ant")
        monkeypatch.delenv("GOOGLE_AI_API_KEY", raising=False)
        monkeypatch.delenv("ZAI_API_KEY", raising=False)
        with patch(
            "config.ConfigManager",
            return_value=_cfg("https://api.openai.com/v1"),
        ):
            keys = _get_api_keys_from_config()
        assert keys["anthropic"] == "sk-env-ant"

    def test_config_failure_returns_empty_dict(self):
        with patch("config.ConfigManager", side_effect=RuntimeError("boom")):
            assert _get_api_keys_from_config() == {}


class TestStatusRoutes:
    def test_get_all_provider_status(self):
        mgr = MagicMock()
        mgr.get_all_statuses.return_value = {"openai": {"ok": True}}
        p_mgr, p_keys = _patched(mgr, {"openai": "sk-1"})
        with p_mgr, p_keys:
            resp = _client().get("/api/providers/status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["providers"] == {"openai": {"ok": True}}
        assert body["configured_providers"] == ["openai"]

    def test_get_single_provider_status_uses_configured_key(self):
        mgr = MagicMock()
        mgr.get_provider_status.return_value = {"provider": "openai"}
        p_mgr, p_keys = _patched(mgr, {"openai": "sk-1"})
        with p_mgr, p_keys:
            resp = _client().get("/api/providers/status/openai")
        assert resp.status_code == 200
        mgr.get_provider_status.assert_called_once_with("openai", "sk-1")

    def test_get_provider_models_with_refresh(self):
        mgr = MagicMock()
        mgr.get_available_models.return_value = ["gpt-a", "gpt-b"]
        p_mgr, p_keys = _patched(mgr, {"openai": "sk-1"})
        with p_mgr, p_keys:
            resp = _client().get("/api/providers/models/openai?refresh=true")
        assert resp.status_code == 200
        body = resp.json()
        assert body == {"provider": "openai", "models": ["gpt-a", "gpt-b"], "count": 2}
        mgr.get_available_models.assert_called_once_with(
            "openai", "sk-1", force_refresh=True
        )

    def test_refresh_all_providers(self):
        mgr = MagicMock()
        mgr.refresh_all.return_value = {"openai": "ok"}
        p_mgr, p_keys = _patched(mgr, {"openai": "sk-1"})
        with p_mgr, p_keys:
            resp = _client().post("/api/providers/refresh")
        assert resp.status_code == 200
        assert resp.json() == {"status": "refreshed", "providers": {"openai": "ok"}}


class TestQuotaCheck:
    def test_low_quota_provider_flagged_for_switch(self):
        mgr = MagicMock()
        mgr.is_quota_low.side_effect = lambda ptype, *_: ptype == "openai"
        mgr.get_rate_limit.return_value = SimpleNamespace(
            min_pct=0.05, reset_at="2026-06-12T00:00:00Z"
        )
        p_mgr, p_keys = _patched(mgr, {"openai": "sk-1", "anthropic": "sk-2"})
        with p_mgr, p_keys:
            resp = _client().get("/api/providers/quota-check?threshold=0.2")
        body = resp.json()
        assert body["should_switch"] is True
        assert body["threshold"] == 0.2
        assert body["ok_providers"] == ["anthropic"]
        assert body["low_quota_providers"] == [
            {
                "provider": "openai",
                "quota_pct": 0.05,
                "reset_at": "2026-06-12T00:00:00Z",
            }
        ]

    def test_all_providers_ok(self):
        mgr = MagicMock()
        mgr.is_quota_low.return_value = False
        p_mgr, p_keys = _patched(mgr, {"openai": "sk-1"})
        with p_mgr, p_keys:
            body = _client().get("/api/providers/quota-check").json()
        assert body["should_switch"] is False
        assert body["low_quota_providers"] == []


class TestFallbacks:
    def test_fallbacks_for_all_configured_providers(self):
        mgr = MagicMock()
        mgr.get_usable_fallbacks.return_value = [{"model": "m1"}]
        p_mgr, p_keys = _patched(mgr, {"openai": "sk-1"})
        with p_mgr, p_keys:
            body = _client().get("/api/providers/fallbacks").json()
        assert body == {"fallbacks": {"openai": [{"model": "m1"}]}}

    def test_provider_filter_without_key_is_skipped(self):
        mgr = MagicMock()
        p_mgr, p_keys = _patched(mgr, {"openai": "sk-1"})
        with p_mgr, p_keys:
            body = _client().get("/api/providers/fallbacks?provider_type=kyma").json()
        assert body == {"fallbacks": {}}
        mgr.get_usable_fallbacks.assert_not_called()
