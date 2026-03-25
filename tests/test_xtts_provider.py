"""Tests for XTTS v2 voice cloning provider in TTSAudioGenerator."""

import os
import tempfile
import time
from unittest.mock import MagicMock, patch, mock_open

import pytest

from services.tts_audio_generator import TTSAudioGenerator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FakeChar:
    """Minimal stand-in for a Character object."""
    def __init__(self, name, gender="female"):
        self.name = name
        self.gender = gender


def _make_wav_bytes() -> bytes:
    """Return a minimal valid WAV header (44 bytes)."""
    import struct
    # RIFF header for empty PCM WAV
    data_size = 0
    chunk_size = 36 + data_size
    return (
        b"RIFF"
        + struct.pack("<I", chunk_size)
        + b"WAVE"
        + b"fmt "
        + struct.pack("<IHHIIHH", 16, 1, 1, 22050, 44100, 2, 16)
        + b"data"
        + struct.pack("<I", data_size)
    )


# ---------------------------------------------------------------------------
# 1. PROVIDERS list includes "xtts"
# ---------------------------------------------------------------------------

def test_providers_includes_xtts():
    assert "xtts" in TTSAudioGenerator.PROVIDERS


# ---------------------------------------------------------------------------
# 2. _generate_xtts — Coqui local server success
# ---------------------------------------------------------------------------

def test_generate_xtts_coqui_success(tmp_path):
    wav_bytes = _make_wav_bytes()
    ref = tmp_path / "ref.wav"
    ref.write_bytes(wav_bytes)
    out = str(tmp_path / "out.mp3")

    mock_resp = MagicMock()
    mock_resp.content = wav_bytes
    mock_resp.raise_for_status = MagicMock()

    gen = TTSAudioGenerator.__new__(TTSAudioGenerator)
    gen.xtts_api_url = "http://localhost:8020"
    gen.xtts_reference_audio = str(ref)
    gen.character_voice_map = {}
    gen.provider = "xtts"

    with patch("requests.post", return_value=mock_resp) as mock_post:
        result = gen._generate_xtts("Hello world", out)

    assert result == out
    assert os.path.exists(out)
    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args
    assert "/tts_to_audio/" in call_kwargs[0][0]


# ---------------------------------------------------------------------------
# 3. _generate_xtts — no API URL returns None
# ---------------------------------------------------------------------------

def test_generate_xtts_no_url_returns_none(tmp_path):
    ref = tmp_path / "ref.wav"
    ref.write_bytes(_make_wav_bytes())
    out = str(tmp_path / "out.mp3")

    gen = TTSAudioGenerator.__new__(TTSAudioGenerator)
    gen.xtts_api_url = ""
    gen.xtts_reference_audio = str(ref)
    gen.character_voice_map = {}
    gen.provider = "xtts"

    result = gen._generate_xtts("Hello", out)
    assert result is None


# ---------------------------------------------------------------------------
# 4. _generate_xtts — missing reference audio returns None
# ---------------------------------------------------------------------------

def test_generate_xtts_missing_ref_returns_none(tmp_path):
    out = str(tmp_path / "out.mp3")

    gen = TTSAudioGenerator.__new__(TTSAudioGenerator)
    gen.xtts_api_url = "http://localhost:8020"
    gen.xtts_reference_audio = ""
    gen.character_voice_map = {}
    gen.provider = "xtts"

    result = gen._generate_xtts("Hello", out)
    assert result is None


# ---------------------------------------------------------------------------
# 5. _generate_xtts — API error falls back gracefully (returns None)
# ---------------------------------------------------------------------------

def test_generate_xtts_api_error_returns_none(tmp_path):
    ref = tmp_path / "ref.wav"
    ref.write_bytes(_make_wav_bytes())
    out = str(tmp_path / "out.mp3")

    gen = TTSAudioGenerator.__new__(TTSAudioGenerator)
    gen.xtts_api_url = "http://localhost:8020"
    gen.xtts_reference_audio = str(ref)
    gen.character_voice_map = {}
    gen.provider = "xtts"

    with patch("requests.post", side_effect=ConnectionError("refused")):
        result = gen._generate_xtts("Hello", out)

    assert result is None


# ---------------------------------------------------------------------------
# 6. _generate_xtts — Replicate URL dispatches to replicate method
# ---------------------------------------------------------------------------

def test_generate_xtts_replicate_dispatch(tmp_path):
    ref = tmp_path / "ref.wav"
    ref.write_bytes(_make_wav_bytes())
    out = str(tmp_path / "out.mp3")

    gen = TTSAudioGenerator.__new__(TTSAudioGenerator)
    gen.xtts_api_url = "https://api.replicate.com/v1/predictions"
    gen.xtts_reference_audio = str(ref)
    gen.character_voice_map = {}
    gen.provider = "xtts"

    with patch.object(gen, "_generate_xtts_replicate", return_value=out) as mock_rep:
        result = gen._generate_xtts("Hello", out)

    mock_rep.assert_called_once()
    assert result == out


# ---------------------------------------------------------------------------
# 7. _generate_xtts_replicate — success path (polling)
# ---------------------------------------------------------------------------

def test_generate_xtts_replicate_success(tmp_path):
    ref = tmp_path / "ref.wav"
    ref.write_bytes(_make_wav_bytes())
    out = str(tmp_path / "out.mp3")

    audio_bytes = _make_wav_bytes()

    create_resp = MagicMock()
    create_resp.raise_for_status = MagicMock()
    create_resp.json.return_value = {"id": "pred123"}

    poll_resp = MagicMock()
    poll_resp.raise_for_status = MagicMock()
    poll_resp.json.return_value = {
        "status": "succeeded",
        "output": "https://example.com/audio.wav",
    }

    audio_resp = MagicMock()
    audio_resp.raise_for_status = MagicMock()
    audio_resp.content = audio_bytes

    gen = TTSAudioGenerator.__new__(TTSAudioGenerator)
    gen.xtts_api_url = "https://api.replicate.com/v1/predictions"
    gen.xtts_reference_audio = str(ref)
    gen.character_voice_map = {}
    gen.provider = "xtts"

    with patch.dict(os.environ, {"REPLICATE_API_TOKEN": "tok123"}):
        with patch("requests.post", return_value=create_resp):
            with patch("requests.get", side_effect=[poll_resp, audio_resp]):
                with patch("time.sleep"):
                    result = gen._generate_xtts_replicate("Hello", out, str(ref), "vi")

    assert result == out
    assert os.path.exists(out)


# ---------------------------------------------------------------------------
# 8. assign_voices — xtts provider with character_voice_map
# ---------------------------------------------------------------------------

def test_assign_voices_xtts_with_voice_map(tmp_path):
    ref_minh = tmp_path / "minh.wav"
    ref_minh.write_bytes(_make_wav_bytes())
    ref_default = tmp_path / "narrator.wav"
    ref_default.write_bytes(_make_wav_bytes())

    gen = TTSAudioGenerator.__new__(TTSAudioGenerator)
    gen.provider = "xtts"
    gen.xtts_reference_audio = str(ref_default)
    gen.character_voice_map = {"Minh": str(ref_minh)}
    gen.voice = "vi-VN-HoaiMyNeural"

    chars = [_FakeChar("Minh"), _FakeChar("Lan")]
    mapping = gen.assign_voices(chars)

    assert mapping["Minh"] == str(ref_minh)
    assert mapping["Lan"] == str(ref_default)
    assert mapping["narrator"] == str(ref_default)


# ---------------------------------------------------------------------------
# 9. assign_voices — xtts provider with no voice_map uses default ref
# ---------------------------------------------------------------------------

def test_assign_voices_xtts_no_voice_map(tmp_path):
    ref_default = tmp_path / "narrator.wav"
    ref_default.write_bytes(_make_wav_bytes())

    gen = TTSAudioGenerator.__new__(TTSAudioGenerator)
    gen.provider = "xtts"
    gen.xtts_reference_audio = str(ref_default)
    gen.character_voice_map = {}
    gen.voice = "vi-VN-HoaiMyNeural"

    chars = [_FakeChar("Hero"), _FakeChar("Villain")]
    mapping = gen.assign_voices(chars)

    assert mapping["Hero"] == str(ref_default)
    assert mapping["Villain"] == str(ref_default)
    assert mapping["narrator"] == str(ref_default)


# ---------------------------------------------------------------------------
# 10. assign_voices — edge-tts provider still uses gender-based mapping
# ---------------------------------------------------------------------------

def test_assign_voices_edge_tts_unaffected():
    gen = TTSAudioGenerator.__new__(TTSAudioGenerator)
    gen.provider = "edge-tts"
    gen.voice = "vi-VN-HoaiMyNeural"
    gen.xtts_reference_audio = ""
    gen.character_voice_map = {}

    chars = [_FakeChar("NamChar", gender="male"), _FakeChar("NuChar", gender="female")]
    mapping = gen.assign_voices(chars)

    assert mapping["NamChar"] == "vi-VN-NamMinhNeural"
    assert mapping["NuChar"] == "vi-VN-HoaiMyNeural"


# ---------------------------------------------------------------------------
# 11. generate_audio dispatch — calls _generate_xtts and falls back
# ---------------------------------------------------------------------------

def test_generate_audio_xtts_dispatch_fallback(tmp_path):
    out = str(tmp_path / "out.mp3")
    fallback_path = str(tmp_path / "fallback.mp3")

    gen = TTSAudioGenerator.__new__(TTSAudioGenerator)
    gen.provider = "xtts"
    gen.xtts_api_url = "http://localhost:8020"
    gen.xtts_reference_audio = ""  # will cause None
    gen.character_voice_map = {}
    gen.voice = "vi-VN-HoaiMyNeural"
    gen.rate = "+0%"
    gen.volume = "+0%"

    with patch.object(gen, "_generate_xtts", return_value=None) as mock_xtts:
        with patch.object(gen, "_generate_edge_tts", return_value=fallback_path) as mock_edge:
            result = gen.generate_audio("Test text", out)

    mock_xtts.assert_called_once()
    mock_edge.assert_called_once()
    assert result == fallback_path


# ---------------------------------------------------------------------------
# 12. Config save/load round-trips character_voice_map
# ---------------------------------------------------------------------------

def test_config_save_load_character_voice_map(tmp_path):
    """Config should persist and reload character_voice_map dict."""
    import json
    from config import ConfigManager

    cfg_file = tmp_path / "config.json"

    with patch.object(ConfigManager, "CONFIG_FILE", str(cfg_file)):
        # Reset singleton so it re-loads
        with patch.object(ConfigManager, "_instance", None):
            mgr = ConfigManager.__new__(ConfigManager)
            mgr._initialized = False
            mgr.llm = __import__("config").LLMConfig()
            mgr.pipeline = __import__("config").PipelineConfig()
            mgr.pipeline.character_voice_map = {"Minh": "data/voices/minh.wav"}
            mgr.pipeline.xtts_api_url = "http://localhost:8020"
            mgr.pipeline.xtts_reference_audio = "data/voices/narrator.wav"
            mgr.pipeline.tts_provider = "xtts"

            # Save
            os.makedirs(str(tmp_path), exist_ok=True)
            data = {
                "llm": {},
                "pipeline": {
                    "character_voice_map": mgr.pipeline.character_voice_map,
                    "xtts_api_url": mgr.pipeline.xtts_api_url,
                    "xtts_reference_audio": mgr.pipeline.xtts_reference_audio,
                    "tts_provider": mgr.pipeline.tts_provider,
                },
            }
            with open(str(cfg_file), "w") as f:
                json.dump(data, f)

            # Load into a fresh instance
            mgr2 = ConfigManager.__new__(ConfigManager)
            mgr2._initialized = False
            mgr2.llm = __import__("config").LLMConfig()
            mgr2.pipeline = __import__("config").PipelineConfig()
            with patch.object(ConfigManager, "CONFIG_FILE", str(cfg_file)):
                mgr2._load()

    assert mgr2.pipeline.character_voice_map == {"Minh": "data/voices/minh.wav"}
    assert mgr2.pipeline.xtts_api_url == "http://localhost:8020"
    assert mgr2.pipeline.xtts_reference_audio == "data/voices/narrator.wav"


# ---------------------------------------------------------------------------
# 13. Valid audio extension check
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ext,should_pass", [
    (".wav", True),
    (".mp3", True),
    (".flac", True),
    (".ogg", False),
    (".txt", False),
])
def test_valid_audio_extension(tmp_path, ext, should_pass):
    ref = tmp_path / f"ref{ext}"
    ref.write_bytes(b"fake audio")
    out = str(tmp_path / "out.mp3")

    gen = TTSAudioGenerator.__new__(TTSAudioGenerator)
    gen.xtts_api_url = "http://localhost:8020"
    gen.xtts_reference_audio = str(ref)
    gen.character_voice_map = {}
    gen.provider = "xtts"

    mock_resp = MagicMock()
    mock_resp.content = b"audio"
    mock_resp.raise_for_status = MagicMock()

    with patch("requests.post", return_value=mock_resp):
        result = gen._generate_xtts("Hi", out)

    if should_pass:
        assert result == out
    else:
        assert result is None
