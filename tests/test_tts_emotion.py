"""Tests for TTS emotion modulation integration."""

from unittest.mock import MagicMock, patch

import pytest

from services.tts_audio_generator import TTSAudioGenerator


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_fake_async(output_path: str):
    async def _coro(text, path):
        return path
    return _coro


# ── generate_chapter_audio with emotion ──────────────────────────────────────

class TestGenerateChapterAudioEmotion:
    def test_explicit_emotion_adjusts_rate(self, tmp_path):
        """Passing emotion='sad' should temporarily set rate to sad params."""
        gen = TTSAudioGenerator(provider="edge-tts", rate="+0%")
        captured = {}

        async def fake_async(text, path):
            captured["rate"] = gen.rate
            return path

        with patch.object(gen, "_generate_async", side_effect=fake_async):
            gen.generate_chapter_audio("text", chapter_num=1, output_dir=str(tmp_path), emotion="sad")

        assert captured["rate"] == "-15%"

    def test_rate_restored_after_emotion(self, tmp_path):
        """Rate must be restored to original after generation."""
        gen = TTSAudioGenerator(provider="edge-tts", rate="+0%")

        async def fake_async(text, path):
            return path

        with patch.object(gen, "_generate_async", side_effect=fake_async):
            gen.generate_chapter_audio("text", chapter_num=1, output_dir=str(tmp_path), emotion="happy")

        assert gen.rate == "+0%"

    def test_rate_restored_on_exception(self, tmp_path):
        """Rate must be restored even if generation raises."""
        gen = TTSAudioGenerator(provider="edge-tts", rate="+0%")

        async def fail_async(text, path):
            raise RuntimeError("fail")

        with patch.object(gen, "_generate_async", side_effect=fail_async):
            with pytest.raises(RuntimeError):
                gen.generate_chapter_audio("text", chapter_num=1, output_dir=str(tmp_path), emotion="happy")

        assert gen.rate == "+0%"

    def test_no_emotion_no_rate_change(self, tmp_path):
        """No emotion flag and feature disabled: rate must not change."""
        gen = TTSAudioGenerator(provider="edge-tts", rate="+0%")
        captured = {}

        async def fake_async(text, path):
            captured["rate"] = gen.rate
            return path

        with patch.object(gen, "_generate_async", side_effect=fake_async):
            gen.generate_chapter_audio("text", chapter_num=1, output_dir=str(tmp_path))

        assert captured["rate"] == "+0%"


class TestAutoEmotionClassification:
    def test_auto_classify_when_enabled(self, tmp_path):
        """enable_voice_emotion=True should auto-detect emotion and apply rate."""
        gen = TTSAudioGenerator(provider="edge-tts", rate="+0%")
        captured = {}

        async def fake_async(text, path):
            captured["rate"] = gen.rate
            return path

        sad_text = "Anh ấy khóc và buồn mãi không thôi."

        mock_pipeline = MagicMock()
        mock_pipeline.enable_voice_emotion = True

        with patch("services.tts_audio_generator.ConfigManager") as mock_cfg_cls:
            mock_cfg_cls.return_value.pipeline = mock_pipeline
            with patch.object(gen, "_generate_async", side_effect=fake_async):
                gen.generate_chapter_audio(sad_text, chapter_num=1, output_dir=str(tmp_path))

        # sad keywords (khóc, buồn) should be detected → rate = -15%
        assert captured.get("rate") == "-15%"

    def test_no_auto_classify_when_disabled(self, tmp_path):
        """enable_voice_emotion=False should NOT auto-detect emotion."""
        gen = TTSAudioGenerator(provider="edge-tts", rate="+0%")
        captured = {}

        async def fake_async(text, path):
            captured["rate"] = gen.rate
            return path

        sad_text = "Anh ấy khóc và buồn mãi."

        mock_pipeline = MagicMock()
        mock_pipeline.enable_voice_emotion = False

        with patch("services.tts_audio_generator.ConfigManager") as mock_cfg_cls:
            mock_cfg_cls.return_value.pipeline = mock_pipeline
            with patch.object(gen, "_generate_async", side_effect=fake_async):
                gen.generate_chapter_audio(sad_text, chapter_num=1, output_dir=str(tmp_path))

        assert captured.get("rate") == "+0%"


# ── _resolve_xtts_reference ───────────────────────────────────────────────────

class TestResolveXttsReference:
    def test_returns_emotion_specific_path_when_exists(self, tmp_path):
        base_audio = tmp_path / "voice.wav"
        emotion_audio = tmp_path / "voice_sad.wav"
        base_audio.write_bytes(b"base")
        emotion_audio.write_bytes(b"sad variant")

        gen = TTSAudioGenerator(provider="xtts", xtts_reference_audio=str(base_audio))
        result = gen._resolve_xtts_reference(emotion="sad")
        assert result == str(emotion_audio)

    def test_falls_back_to_default_when_emotion_variant_missing(self, tmp_path):
        base_audio = tmp_path / "voice.wav"
        base_audio.write_bytes(b"base")

        gen = TTSAudioGenerator(provider="xtts", xtts_reference_audio=str(base_audio))
        result = gen._resolve_xtts_reference(emotion="happy")
        assert result == str(base_audio)

    def test_no_emotion_returns_default(self, tmp_path):
        base_audio = tmp_path / "voice.wav"
        base_audio.write_bytes(b"base")

        gen = TTSAudioGenerator(provider="xtts", xtts_reference_audio=str(base_audio))
        result = gen._resolve_xtts_reference(emotion="")
        assert result == str(base_audio)

    def test_no_reference_audio_returns_empty(self):
        gen = TTSAudioGenerator(provider="xtts", xtts_reference_audio="")
        result = gen._resolve_xtts_reference(emotion="sad")
        assert result == ""

    def test_no_emotion_no_reference_returns_empty(self):
        gen = TTSAudioGenerator(provider="xtts", xtts_reference_audio="")
        result = gen._resolve_xtts_reference(emotion="")
        assert result == ""
