"""Backward-compat re-export hub — real code lives in services/tts/."""

from services.tts import TTSAudioGenerator, VIETNAMESE_VOICES
# Keep these names here so test patches and lazy imports in services/tts/ continue to work:
#   patch("services.tts_audio_generator.ConfigManager")
#   patch("services.tts_audio_generator.classify_emotion")
from config import ConfigManager  # noqa: F401
from services.emotion_classifier import classify_emotion, get_voice_params  # noqa: F401

__all__ = ["TTSAudioGenerator", "VIETNAMESE_VOICES"]
