"""Tests for TTSAudioGenerator."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.tts_audio_generator import VIETNAMESE_VOICES, TTSAudioGenerator


class TestTTSAudioGeneratorInit:
    def test_default_voice_is_female(self):
        gen = TTSAudioGenerator()
        assert gen.voice == VIETNAMESE_VOICES["female"]

    def test_male_voice_resolved(self):
        gen = TTSAudioGenerator(voice="male")
        assert gen.voice == VIETNAMESE_VOICES["male"]

    def test_custom_voice_passthrough(self):
        custom = "en-US-JennyNeural"
        gen = TTSAudioGenerator(voice=custom)
        assert gen.voice == custom

    def test_rate_and_volume_set(self):
        gen = TTSAudioGenerator(rate="+20%", volume="-10%")
        assert gen.rate == "+20%"
        assert gen.volume == "-10%"


class TestListVoices:
    def test_returns_dict_with_female_and_male(self):
        voices = TTSAudioGenerator.list_voices()
        assert "female" in voices
        assert "male" in voices

    def test_returns_copy_not_original(self):
        v1 = TTSAudioGenerator.list_voices()
        v1["extra"] = "test"
        v2 = TTSAudioGenerator.list_voices()
        assert "extra" not in v2


def _make_async_generate(output_path: str):
    """Return a coroutine that resolves to output_path (simulates _generate_async)."""

    async def _coro(text, path):
        return path

    return _coro


class TestGenerateAudio:
    def test_generate_audio_calls_edge_tts(self, tmp_path):
        output_path = str(tmp_path / "test.mp3")

        async def fake_generate(text, path):
            return path

        gen = TTSAudioGenerator(voice="female")
        with patch.object(gen, "_generate_async", side_effect=fake_generate):
            result = gen.generate_audio("Xin chào thế giới", output_path)

        assert result == output_path

    def test_generate_audio_creates_output_dir(self, tmp_path):
        nested_dir = tmp_path / "deep" / "nested"
        output_path = str(nested_dir / "out.mp3")

        async def fake_generate(text, path):
            return path

        gen = TTSAudioGenerator()
        with patch.object(gen, "_generate_async", side_effect=fake_generate):
            gen.generate_audio("text", output_path)

        assert nested_dir.exists()

    def test_generate_audio_raises_on_failure(self, tmp_path):
        output_path = str(tmp_path / "fail.mp3")

        async def fake_generate(text, path):
            raise RuntimeError("network error")

        gen = TTSAudioGenerator()
        with patch.object(gen, "_generate_async", side_effect=fake_generate):
            with pytest.raises(RuntimeError, match="network error"):
                gen.generate_audio("text", output_path)


class TestGenerateChapterAudio:
    def test_chapter_filename_format(self, tmp_path):
        async def fake_generate(text, path):
            return path

        gen = TTSAudioGenerator()
        with patch.object(gen, "_generate_async", side_effect=fake_generate):
            result = gen.generate_chapter_audio("text", chapter_num=3, output_dir=str(tmp_path))

        assert result == os.path.join(str(tmp_path), "chapter_03.mp3")
