"""Unit tests for services/llm/provider_status.py — rate limits + model discovery."""

import json
import time

import pytest

import services.llm.provider_status as ps
from services.llm.provider_status import (
    ProviderStatusManager,
    RateLimitStatus,
    get_provider_status_manager,
)


@pytest.fixture(autouse=True)
def _isolated_manager(monkeypatch, tmp_path):
    """Fresh singleton per test, cache dir redirected to tmp_path."""
    monkeypatch.setattr(ps, "_CACHE_DIR", str(tmp_path / "provider_status"))
    ProviderStatusManager._instance = None
    yield
    ProviderStatusManager._instance = None


class TestRateLimitStatus:
    def test_pcts_none_without_limits(self):
        status = RateLimitStatus()
        assert status.requests_pct is None
        assert status.tokens_pct is None
        assert status.min_pct is None

    def test_min_pct_is_most_constrained(self):
        status = RateLimitStatus(
            remaining_requests=50,
            limit_requests=100,
            remaining_tokens=10,
            limit_tokens=100,
        )
        assert status.requests_pct == pytest.approx(0.5)
        assert status.tokens_pct == pytest.approx(0.1)
        assert status.min_pct == pytest.approx(0.1)

    def test_staleness(self):
        assert RateLimitStatus(updated_at=0.0).is_stale
        assert not RateLimitStatus(updated_at=time.time()).is_stale

    def test_to_dict_includes_derived_fields(self):
        d = RateLimitStatus(remaining_requests=1, limit_requests=2).to_dict()
        assert d["requests_pct"] == pytest.approx(0.5)
        assert "is_stale" in d and "min_pct" in d


class TestHashKey:
    def test_short_key_passthrough(self):
        assert ProviderStatusManager._hash_key("short") == "short"

    def test_long_key_masked(self):
        masked = ProviderStatusManager._hash_key("sk-abcdefghijklmnop")
        assert masked == "sk-abcde...mnop"


class TestExtractRateLimits:
    def test_openai_headers_case_insensitive(self):
        mgr = ProviderStatusManager()
        status = mgr.extract_rate_limits(
            "openai",
            "sk-test-1234567890ab",
            {
                "X-RateLimit-Remaining-Requests": "90",
                "X-RateLimit-Limit-Requests": "100",
                "X-RateLimit-Remaining-Tokens": "5000",
                "X-RateLimit-Limit-Tokens": "10000",
                "X-RateLimit-Reset-Requests": "120",
            },
        )
        assert status.remaining_requests == 90
        assert status.limit_tokens == 10000
        assert status.reset_at == pytest.approx(120.0)
        assert mgr.get_rate_limit("openai", "sk-test-1234567890ab") is status

    def test_unknown_provider_returns_none(self):
        assert (
            ProviderStatusManager().extract_rate_limits("nope", "k", {"a": "1"}) is None
        )

    def test_no_meaningful_headers_not_stored(self):
        mgr = ProviderStatusManager()
        assert (
            mgr.extract_rate_limits("openai", "key-1234567890ab", {"other": "x"})
            is None
        )
        assert mgr.get_rate_limit("openai", "key-1234567890ab") is None

    def test_openrouter_millisecond_reset_converted(self):
        status = ProviderStatusManager().extract_rate_limits(
            "openrouter",
            "k",
            {"x-ratelimit-remaining": "5", "x-ratelimit-reset": "1700000000000"},
        )
        assert status.reset_at == pytest.approx(1700000000.0)

    def test_non_numeric_header_ignored(self):
        status = ProviderStatusManager().extract_rate_limits(
            "openai",
            "k",
            {
                "x-ratelimit-remaining-requests": "soon",
                "x-ratelimit-remaining-tokens": "7",
            },
        )
        assert status.remaining_requests is None
        assert status.remaining_tokens == 7


class TestQuotaLow:
    def test_no_data_is_not_low(self):
        assert ProviderStatusManager().is_quota_low("openai", "k") is False

    def test_fresh_below_threshold_is_low(self):
        mgr = ProviderStatusManager()
        mgr.extract_rate_limits(
            "openai",
            "k",
            {
                "x-ratelimit-remaining-requests": "1",
                "x-ratelimit-limit-requests": "100",
            },
        )
        assert mgr.is_quota_low("openai", "k", threshold=0.1) is True
        assert mgr.is_quota_low("openai", "k", threshold=0.001) is False

    def test_stale_data_is_not_low(self):
        mgr = ProviderStatusManager()
        status = mgr.extract_rate_limits(
            "openai",
            "k",
            {
                "x-ratelimit-remaining-requests": "1",
                "x-ratelimit-limit-requests": "100",
            },
        )
        status.updated_at = 0.0
        assert mgr.is_quota_low("openai", "k") is False


class TestParseModelsResponse:
    def test_openai_filters_chat_models(self):
        mgr = ProviderStatusManager()
        data = {"data": [{"id": "gpt-4o"}, {"id": "whisper-1"}, {"id": "o1-mini"}]}
        assert mgr._parse_models_response("openai", data) == ["gpt-4o", "o1-mini"]

    def test_google_strips_models_prefix(self):
        mgr = ProviderStatusManager()
        data = {
            "models": [
                {"name": "models/gemini-1.5-pro"},
                {"name": "bare"},
                {"name": ""},
            ]
        }
        assert mgr._parse_models_response("google", data) == ["gemini-1.5-pro", "bare"]

    def test_openrouter_and_zai_use_data_ids(self):
        mgr = ProviderStatusManager()
        data = {"data": [{"id": "a/b"}, {"id": ""}]}
        assert mgr._parse_models_response("openrouter", data) == ["a/b"]
        assert mgr._parse_models_response("zai", data) == ["a/b"]


class TestModelDiscovery:
    def test_anthropic_fetch_returns_hardcoded_without_network(self):
        models = ProviderStatusManager()._fetch_models("anthropic", "key")
        assert models == ps._HARDCODED_MODELS["anthropic"]

    def test_fetch_network_failure_returns_empty(self, monkeypatch):
        def boom(*a, **kw):
            raise OSError("no network")

        monkeypatch.setattr(ps.urllib.request, "urlopen", boom)
        assert ProviderStatusManager()._fetch_models("openai", "key") == []

    def test_get_available_models_caches_and_persists(self, monkeypatch):
        mgr = ProviderStatusManager()
        monkeypatch.setattr(mgr, "_fetch_models", lambda p, k: ["m1", "m2"])
        assert mgr.get_available_models("openai", "key") == ["m1", "m2"]
        # Second call hits the in-memory cache, not _fetch_models
        monkeypatch.setattr(mgr, "_fetch_models", lambda p, k: ["changed"])
        assert mgr.get_available_models("openai", "key") == ["m1", "m2"]
        cached = json.loads(open(mgr._cache_file("openai"), encoding="utf-8").read())
        assert cached["models"] == ["m1", "m2"]

    def test_fallback_to_hardcoded_when_fetch_empty(self, monkeypatch):
        mgr = ProviderStatusManager()
        monkeypatch.setattr(mgr, "_fetch_models", lambda p, k: [])
        assert mgr.get_available_models("zai", "key") == ps._HARDCODED_MODELS["zai"]
        assert mgr.get_available_models("unknown-prov", "key") == []

    def test_load_cached_data_from_disk(self, monkeypatch, tmp_path):
        cache_dir = tmp_path / "preloaded"
        cache_dir.mkdir()
        (cache_dir / "openai.json").write_text(
            json.dumps({"models": ["disk-model"], "updated_at": time.time()}),
            encoding="utf-8",
        )
        monkeypatch.setattr(ps, "_CACHE_DIR", str(cache_dir))
        ProviderStatusManager._instance = None
        assert ProviderStatusManager().get_available_models("openai", "k") == [
            "disk-model"
        ]


class TestCanUseModel:
    def test_no_model_list_assumes_available(self, monkeypatch):
        mgr = ProviderStatusManager()
        monkeypatch.setattr(mgr, "get_available_models", lambda *a, **kw: [])
        assert mgr.can_use_model("openai", "k", "gpt-4o") == (True, "no_model_list")

    def test_exact_partial_and_missing(self, monkeypatch):
        mgr = ProviderStatusManager()
        monkeypatch.setattr(
            mgr, "get_available_models", lambda *a, **kw: ["gpt-4-turbo"]
        )
        assert mgr.can_use_model("openai", "k", "gpt-4-turbo") == (True, "available")
        assert mgr.can_use_model("openai", "k", "gpt-4") == (
            True,
            "partial_match:gpt-4-turbo",
        )
        assert mgr.can_use_model("openai", "k", "claude-3") == (False, "not_found")


class TestCombinedStatus:
    def test_get_provider_status_without_key(self):
        status = ProviderStatusManager().get_provider_status("openai")
        assert status["provider"] == "openai"
        assert status["models"] == []
        assert status["quota_low"] is None

    def test_get_all_statuses_covers_known_providers(self, monkeypatch):
        mgr = ProviderStatusManager()
        monkeypatch.setattr(mgr, "_fetch_models", lambda p, k: [])
        statuses = mgr.get_all_statuses({"openai": "k1"})
        assert set(ps._MODEL_ENDPOINTS) <= set(statuses)

    def test_get_usable_fallbacks_excludes(self, monkeypatch):
        mgr = ProviderStatusManager()
        monkeypatch.setattr(mgr, "get_available_models", lambda *a, **kw: ["m1", "m2"])
        result = mgr.get_usable_fallbacks("openai", "k", exclude_models={"m1"})
        assert [r["model"] for r in result] == ["m2"]

    def test_refresh_all_forces_fetch(self, monkeypatch):
        mgr = ProviderStatusManager()
        monkeypatch.setattr(mgr, "_fetch_models", lambda p, k: ["fresh"])
        result = mgr.refresh_all()
        assert all(v["models_count"] == 1 for v in result.values())

    def test_get_provider_status_manager_is_singleton(self):
        assert get_provider_status_manager() is get_provider_status_manager()
