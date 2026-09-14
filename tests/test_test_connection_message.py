"""Regression test: POST /api/config/test-connection must not report a
failure using the primary's SUCCESS text.

Observed on 2026-08-26: primary (local bridge) OK, one fallback (Google
Gemini) broken. The route returned `ok: false` with `message` copied from the
primary — literally "Kết nối thành công" — so the UI showed a red error toast
saying "connection successful", naming no provider.
"""

import pytest

from api import config_routes


class _FakeLLMClient:
    """Stands in for LLMClient: primary healthy, per-profile answers scripted."""

    per_provider: dict = {}

    @staticmethod
    def reset():
        pass

    def check_connection(self):
        return True, "Kết nối thành công"

    def check_provider(self, base_url, api_key, model):
        return type(self).per_provider[base_url]


@pytest.fixture
def _wire(monkeypatch, tmp_path):
    """Point the route at a fake LLM client and an in-memory config."""

    def _apply(profiles, per_provider):
        class _Llm:
            def __init__(self):
                self.fallback_models = profiles

        class _Cfg:
            def __init__(self):
                self.llm = _Llm()

            def save(self):
                pass

        import services.llm_client as llm_client_mod

        monkeypatch.setattr(_FakeLLMClient, "per_provider", per_provider)
        monkeypatch.setattr(llm_client_mod, "LLMClient", _FakeLLMClient)
        monkeypatch.setattr(config_routes, "ConfigManager", _Cfg)
        return _Cfg

    return _apply


def _profile(name, base_url):
    return {
        "name": name,
        "base_url": base_url,
        "api_key": "k",
        "model": "m",
        "enabled": True,
    }


class TestTestConnectionMessage:
    def test_failure_names_the_broken_provider(self, _wire):
        _wire(
            [_profile("Gemini Web", "http://localhost:8000/v1"),
             _profile("Google Gemini", "https://generativelanguage.googleapis.com/v1beta/openai/")],
            {
                "http://localhost:8000/v1": (True, "OK"),
                "https://generativelanguage.googleapis.com/v1beta/openai/": (
                    False,
                    "Lỗi kết nối: 404 model not found",
                ),
            },
        )
        out = config_routes.test_connection()
        assert out["ok"] is False
        assert "Google Gemini" in out["message"]
        assert "404 model not found" in out["message"]
        # The bug: the primary's success text leaking into a failure message.
        assert "Kết nối thành công" not in out["message"]

    def test_all_ok_keeps_the_success_message(self, _wire):
        _wire(
            [_profile("Gemini Web", "http://localhost:8000/v1")],
            {"http://localhost:8000/v1": (True, "OK")},
        )
        out = config_routes.test_connection()
        assert out["ok"] is True
        assert out["message"] == "All providers OK"

    def test_disabled_profiles_do_not_fail_the_run(self, _wire):
        disabled = _profile("CustomOrca", "https://api.orcarouter.ai/v1")
        disabled["enabled"] = False
        _wire(
            [_profile("Gemini Web", "http://localhost:8000/v1"), disabled],
            {"http://localhost:8000/v1": (True, "OK")},
        )
        out = config_routes.test_connection()
        assert out["ok"] is True
        assert [r["ok"] for r in out["profiles"]] == [True, True, None]
