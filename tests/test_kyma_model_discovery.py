"""Unit tests for services/kyma_model_discovery.py (previously untested).

_CACHE_FILE is redirected to tmp_path so the real data/ cache is never
touched; urllib is mocked so no network calls happen.
"""

from __future__ import annotations

import json
import time
import urllib.request
from unittest.mock import MagicMock, patch

import pytest

import services.kyma_model_discovery as kmd


@pytest.fixture(autouse=True)
def cache_file(tmp_path, monkeypatch):
    path = tmp_path / "kyma_cache" / "models.json"
    monkeypatch.setattr(kmd, "_CACHE_FILE", str(path))
    return path


def _model(mid, ctx=32000, **extra):
    return {"id": mid, "context_window": ctx, **extra}


class TestMeetsRequirements:
    def test_accepts_context_window(self):
        assert kmd._meets_requirements(_model("deepseek-v3")) is True

    def test_accepts_context_length_alias(self):
        assert (
            kmd._meets_requirements({"id": "deepseek-v3", "context_length": 32000})
            is True
        )

    def test_rejects_small_context(self):
        assert kmd._meets_requirements(_model("deepseek-v3", ctx=4096)) is False

    def test_rejects_coder_models(self):
        assert kmd._meets_requirements(_model("qwen-coder-32b")) is False


class TestGetKymaModels:
    def test_cache_hit_skips_api(self):
        kmd._save_cache([_model("deepseek-v3")])
        with patch.object(kmd, "_fetch_from_api") as fetch:
            assert kmd.get_kyma_models() == ["deepseek-v3"]
        fetch.assert_not_called()

    def test_fetch_success_filters_and_caches(self, cache_file):
        raw = [
            _model("deepseek-v3"),
            _model("qwen-coder-32b"),  # excluded pattern
            _model("tiny-model", ctx=2048),  # context too small
            {"context_window": 32000},  # missing id
        ]
        with patch.object(kmd, "_fetch_from_api", return_value=raw):
            assert kmd.get_kyma_models("key-a") == ["deepseek-v3"]
        on_disk = json.loads(cache_file.read_text(encoding="utf-8"))
        assert [m["id"] for m in on_disk["models"]] == ["deepseek-v3"]

    def test_force_refresh_bypasses_cache(self):
        kmd._save_cache([_model("cũ-trong-cache")])
        with patch.object(
            kmd, "_fetch_from_api", return_value=[_model("mới-từ-api")]
        ) as fetch:
            assert kmd.get_kyma_models("key-a", force_refresh=True) == ["mới-từ-api"]
        fetch.assert_called_once_with("key-a")

    def test_stale_cache_used_when_api_down(self, cache_file):
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(
            json.dumps(
                {
                    "cached_at": time.time() - kmd._CACHE_TTL_SECONDS - 1,
                    "models": [_model("deepseek-v3")],
                }
            ),
            encoding="utf-8",
        )
        with patch.object(kmd, "_fetch_from_api", return_value=None):
            assert kmd.get_kyma_models() == ["deepseek-v3"]

    def test_fallback_when_no_cache_and_api_down(self):
        with patch.object(kmd, "_fetch_from_api", return_value=None):
            models = kmd.get_kyma_models()
        assert models == kmd._FALLBACK_MODELS
        models.append("đột biến")
        assert "đột biến" not in kmd._FALLBACK_MODELS

    def test_refresh_cache_forces_fetch(self):
        kmd._save_cache([_model("cũ-trong-cache")])
        with patch.object(kmd, "_fetch_from_api", return_value=[_model("mới-từ-api")]):
            assert kmd.refresh_cache("key-a") == ["mới-từ-api"]


class TestFetchFromApi:
    def test_parses_data_and_sends_auth_header(self, monkeypatch):
        resp = MagicMock()
        resp.read.return_value = json.dumps({"data": [_model("deepseek-v3")]}).encode(
            "utf-8"
        )
        cm = MagicMock()
        cm.__enter__ = MagicMock(return_value=resp)
        cm.__exit__ = MagicMock(return_value=False)
        urlopen = MagicMock(return_value=cm)
        monkeypatch.setattr(urllib.request, "urlopen", urlopen)

        assert kmd._fetch_from_api("key-a") == [_model("deepseek-v3")]
        req = urlopen.call_args.args[0]
        assert req.get_header("Authorization") == "Bearer key-a"

    def test_network_error_returns_none(self, monkeypatch):
        monkeypatch.setattr(
            urllib.request,
            "urlopen",
            MagicMock(side_effect=OSError("mạng rớt")),
        )
        assert kmd._fetch_from_api("key-a") is None
