"""Tests for TTSAudioGenerator pluggable provider pattern."""

import os
from unittest.mock import MagicMock, patch

import pytest

from services.tts_audio_generator import TTSAudioGenerator


# ── Provider dispatch ─────────────────────────────────────────────────────────

class TestProviderDispatch:
    def test_default_provider_is_edge_tts(self):
        gen = TTSAudioGenerator()
        assert gen.provider == "edge-tts"

    def test_provider_set_explicitly(self):
        gen = TTSAudioGenerator(provider="kling")
        assert gen.provider == "kling"

    def test_none_provider_set(self):
        gen = TTSAudioGenerator(provider="none")
        assert gen.provider == "none"

    def test_list_providers_returns_all(self):
        providers = TTSAudioGenerator.list_providers()
        assert "edge-tts" in providers
        assert "kling" in providers
        assert "none" in providers

    def test_list_providers_returns_copy(self):
        p1 = TTSAudioGenerator.list_providers()
        p1.append("fake")
        p2 = TTSAudioGenerator.list_providers()
        assert "fake" not in p2


# ── none provider ─────────────────────────────────────────────────────────────

class TestNoneProvider:
    def test_generate_audio_returns_none(self, tmp_path):
        gen = TTSAudioGenerator(provider="none")
        result = gen.generate_audio("Hello", str(tmp_path / "out.mp3"))
        assert result is None

    def test_generate_chapter_audio_returns_none(self, tmp_path):
        gen = TTSAudioGenerator(provider="none")
        result = gen.generate_chapter_audio("Hello", chapter_num=1, output_dir=str(tmp_path))
        assert result is None

    def test_generate_full_audiobook_returns_empty_list(self, tmp_path):
        gen = TTSAudioGenerator(provider="none")

        class FakeCh:
            chapter_number = 1
            content = "text"

        result = gen.generate_full_audiobook([FakeCh()], output_dir=str(tmp_path))
        assert result == []

    def test_generate_full_audiobook_parallel_returns_empty_list(self, tmp_path):
        gen = TTSAudioGenerator(provider="none")

        class FakeCh:
            chapter_number = 1
            content = "text"

        result = gen.generate_full_audiobook_parallel([FakeCh()], output_dir=str(tmp_path))
        assert result == []


# ── edge-tts provider ─────────────────────────────────────────────────────────

class TestEdgeTTSProvider:
    def test_generate_audio_calls_edge_tts(self, tmp_path):
        output_path = str(tmp_path / "test.mp3")

        async def fake_async(text, path):
            return path

        gen = TTSAudioGenerator(provider="edge-tts")
        with patch.object(gen, "_generate_async", side_effect=fake_async):
            result = gen.generate_audio("Xin chào", output_path)

        assert result == output_path

    def test_generate_audio_raises_on_failure(self, tmp_path):
        output_path = str(tmp_path / "fail.mp3")

        async def fail_async(text, path):
            raise RuntimeError("network error")

        gen = TTSAudioGenerator(provider="edge-tts")
        with patch.object(gen, "_generate_async", side_effect=fail_async):
            with pytest.raises(RuntimeError, match="network error"):
                gen.generate_audio("text", output_path)


# ── Kling provider ────────────────────────────────────────────────────────────

class TestKlingProvider:
    def test_no_api_key_returns_none(self, tmp_path):
        gen = TTSAudioGenerator(provider="kling", api_key="", api_url="http://example.com")
        result = gen.generate_audio("Hello", str(tmp_path / "out.mp3"))
        assert result is None

    def test_kling_binary_response(self, tmp_path):
        output_path = str(tmp_path / "kling.mp3")
        gen = TTSAudioGenerator(
            provider="kling", api_key="test-key", api_url="http://kling.example.com"
        )

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.headers = {"Content-Type": "audio/mpeg"}
        mock_resp.content = b"FAKE_AUDIO_BYTES"

        with patch("requests.post", return_value=mock_resp) as mock_post:
            result = gen._generate_kling("Hello world", output_path)

        assert result == output_path
        assert os.path.exists(output_path)
        with open(output_path, "rb") as f:
            assert f.read() == b"FAKE_AUDIO_BYTES"

        call_args = mock_post.call_args
        assert call_args[0][0] == "http://kling.example.com/tts/generate"
        assert call_args[1]["headers"]["Authorization"] == "Bearer test-key"

    def test_kling_json_base64_response(self, tmp_path):
        import base64

        output_path = str(tmp_path / "kling_b64.mp3")
        audio_bytes = b"FAKE_MP3_DATA"
        encoded = base64.b64encode(audio_bytes).decode()

        gen = TTSAudioGenerator(
            provider="kling", api_key="test-key", api_url="http://kling.example.com"
        )

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.headers = {"Content-Type": "application/json"}
        mock_resp.json.return_value = {"audio": encoded}

        with patch("requests.post", return_value=mock_resp):
            result = gen._generate_kling("Hello", output_path)

        assert result == output_path
        with open(output_path, "rb") as f:
            assert f.read() == audio_bytes

    def test_kling_json_data_fallback_key(self, tmp_path):
        import base64

        output_path = str(tmp_path / "kling_data.mp3")
        audio_bytes = b"DATA_AUDIO"
        encoded = base64.b64encode(audio_bytes).decode()

        gen = TTSAudioGenerator(
            provider="kling", api_key="test-key", api_url="http://kling.example.com"
        )

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.headers = {"Content-Type": "application/json"}
        mock_resp.json.return_value = {"data": encoded}

        with patch("requests.post", return_value=mock_resp):
            result = gen._generate_kling("Hello", output_path)

        assert result == output_path

    def test_kling_http_error_returns_none(self, tmp_path):
        output_path = str(tmp_path / "err.mp3")
        gen = TTSAudioGenerator(
            provider="kling", api_key="test-key", api_url="http://kling.example.com"
        )

        import requests as req_lib

        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = req_lib.HTTPError("500 Server Error")

        with patch("requests.post", return_value=mock_resp):
            result = gen._generate_kling("Hello", output_path)

        assert result is None

    def test_generate_audio_dispatches_to_kling(self, tmp_path):
        output_path = str(tmp_path / "dispatch.mp3")
        gen = TTSAudioGenerator(
            provider="kling", api_key="test-key", api_url="http://kling.example.com"
        )

        with patch.object(gen, "_generate_kling", return_value=output_path) as mock_kling:
            result = gen.generate_audio("text", output_path)

        mock_kling.assert_called_once_with("text", output_path)
        assert result == output_path


# ── Config loading ────────────────────────────────────────────────────────────

class TestConfigLoading:
    def test_tts_provider_from_env(self, monkeypatch):
        monkeypatch.setenv("STORYFORGE_TTS_PROVIDER", "kling")
        # Reset singleton so env var is picked up
        from config import ConfigManager
        ConfigManager._instance = None
        gen = TTSAudioGenerator()
        assert gen.provider == "kling"
        # Restore singleton for other tests
        ConfigManager._instance = None

    def test_kling_api_key_from_env(self, monkeypatch):
        monkeypatch.setenv("KLING_TTS_API_KEY", "my-kling-key")
        from config import ConfigManager
        ConfigManager._instance = None
        gen = TTSAudioGenerator(provider="kling")
        assert gen.api_key == "my-kling-key"
        ConfigManager._instance = None

    def test_provider_param_overrides_config(self, monkeypatch):
        monkeypatch.setenv("STORYFORGE_TTS_PROVIDER", "kling")
        from config import ConfigManager
        ConfigManager._instance = None
        gen = TTSAudioGenerator(provider="none")
        assert gen.provider == "none"
        ConfigManager._instance = None
