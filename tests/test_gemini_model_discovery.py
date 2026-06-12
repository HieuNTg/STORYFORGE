"""Unit tests for services/gemini_model_discovery.py (previously untested).

_CACHE_FILE is redirected to tmp_path so the real data/ cache is never
touched; the google-genai SDK is faked via sys.modules so _fetch_from_api
filtering runs without the dependency or network.
"""

from __future__ import annotations

import json
import sys
import time
import types
from unittest.mock import MagicMock, patch

import pytest

import services.gemini_model_discovery as gmd


@pytest.fixture(autouse=True)
def cache_file(tmp_path, monkeypatch):
    path = tmp_path / "gemini_cache" / "models.json"
    monkeypatch.setattr(gmd, "_CACHE_FILE", str(path))
    return path


class _FakeModel:
    def __init__(self, name, supported=None):
        self.name = name
        self.supported_actions = supported
        self.supported_generation_methods = None


def _install_fake_genai(monkeypatch, models=None, error=None):
    client = MagicMock()
    if error is not None:
        client.models.list.side_effect = error
    else:
        client.models.list.return_value = models or []
    fake_genai = types.ModuleType("google.genai")
    fake_genai.Client = MagicMock(return_value=client)
    fake_google = types.ModuleType("google")
    fake_google.genai = fake_genai
    monkeypatch.setitem(sys.modules, "google", fake_google)
    monkeypatch.setitem(sys.modules, "google.genai", fake_genai)


class TestKeyHash:
    def test_empty_key_is_nokey(self):
        assert gmd._key_hash("") == "nokey"

    def test_deterministic_and_key_specific(self):
        assert gmd._key_hash("key-a") == gmd._key_hash("key-a")
        assert gmd._key_hash("key-a") != gmd._key_hash("key-b")
        assert len(gmd._key_hash("key-a")) == 16


class TestCache:
    def test_save_then_load_roundtrip(self):
        gmd._save_cache("hash-1", ["gemini-2.5-flash"])
        assert gmd._load_cache("hash-1") == ["gemini-2.5-flash"]

    def test_missing_file_returns_none(self):
        assert gmd._load_cache("hash-1") is None

    def test_key_mismatch_invalidates(self):
        gmd._save_cache("hash-1", ["gemini-2.5-flash"])
        assert gmd._load_cache("hash-khác") is None

    def test_expired_cache_invalidates(self, cache_file):
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(
            json.dumps(
                {
                    "cached_at": time.time() - gmd._CACHE_TTL_SECONDS - 1,
                    "key_hash": "hash-1",
                    "models": ["gemini-2.5-flash"],
                }
            ),
            encoding="utf-8",
        )
        assert gmd._load_cache("hash-1") is None


class TestGetGeminiModels:
    def test_no_key_no_cache_returns_fallback_copy(self):
        models = gmd.get_gemini_models()
        assert models == gmd._FALLBACK_MODELS
        models.append("đột biến")
        assert "đột biến" not in gmd._FALLBACK_MODELS

    def test_cache_hit_skips_api(self):
        gmd._save_cache(gmd._key_hash("key-a"), ["gemini-cached"])
        with patch.object(gmd, "_fetch_from_api") as fetch:
            assert gmd.get_gemini_models("key-a") == ["gemini-cached"]
        fetch.assert_not_called()

    def test_api_success_orders_and_caches(self):
        with patch.object(
            gmd,
            "_fetch_from_api",
            return_value=["gemini-2.0-flash", "gemini-2.5-flash-lite"],
        ):
            assert gmd.get_gemini_models("key-a") == [
                "gemini-2.5-flash-lite",
                "gemini-2.0-flash",
            ]
        # second call must come from the per-key disk cache
        with patch.object(gmd, "_fetch_from_api") as fetch:
            assert gmd.get_gemini_models("key-a") == [
                "gemini-2.5-flash-lite",
                "gemini-2.0-flash",
            ]
        fetch.assert_not_called()

    def test_api_failure_falls_back(self):
        with patch.object(gmd, "_fetch_from_api", return_value=None):
            assert gmd.get_gemini_models("key-a") == gmd._FALLBACK_MODELS


class TestOrderModels:
    def test_stable_before_preview(self):
        ordered = gmd._order_models(
            ["gemini-2.5-flash-preview", "gemini-2.0-flash", "gemini-2.5-flash"]
        )
        assert ordered.index("gemini-2.5-flash") < ordered.index(
            "gemini-2.5-flash-preview"
        )
        assert ordered.index("gemini-2.0-flash") < ordered.index(
            "gemini-2.5-flash-preview"
        )

    def test_newer_version_first_within_tier(self):
        ordered = gmd._order_models(["gemini-2.0-flash", "gemini-2.5-flash"])
        assert ordered == ["gemini-2.5-flash", "gemini-2.0-flash"]

    def test_cheap_tier_first(self):
        ordered = gmd._order_models(
            ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.5-flash-lite"]
        )
        assert ordered == [
            "gemini-2.5-flash-lite",
            "gemini-2.5-flash",
            "gemini-2.5-pro",
        ]

    def test_gemini_family_before_gemma_and_dedupe(self):
        ordered = gmd._order_models(
            ["gemma-3-27b-it", "gemini-2.0-flash", "gemini-2.0-flash"]
        )
        assert ordered == ["gemini-2.0-flash", "gemma-3-27b-it"]

    def test_canonical_id_preferred_over_latest_revision(self):
        ordered = gmd._order_models(["gemini-2.5-flash-latest", "gemini-2.5-flash"])
        assert ordered == ["gemini-2.5-flash", "gemini-2.5-flash-latest"]


class TestFetchFromApi:
    def test_filters_non_text_and_foreign_models(self, monkeypatch):
        _install_fake_genai(
            monkeypatch,
            models=[
                _FakeModel("models/gemini-2.5-flash", ["generateContent"]),
                _FakeModel("models/gemini-embedding-001", ["generateContent"]),
                _FakeModel("models/gemini-2.5-flash-tts", ["generateContent"]),
                _FakeModel("models/gemini-2.0-pro", ["embedContent"]),
                _FakeModel("models/claude-x", ["generateContent"]),
                _FakeModel("gemma-3-27b-it", ["generateContent"]),
                _FakeModel(""),
            ],
        )
        assert gmd._fetch_from_api("key-a") == [
            "gemini-2.5-flash",
            "gemma-3-27b-it",
        ]

    def test_empty_result_returns_none(self, monkeypatch):
        _install_fake_genai(monkeypatch, models=[])
        assert gmd._fetch_from_api("key-a") is None

    def test_sdk_error_returns_none(self, monkeypatch):
        _install_fake_genai(monkeypatch, error=RuntimeError("mạng rớt"))
        assert gmd._fetch_from_api("key-a") is None
