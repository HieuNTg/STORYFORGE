"""TTS package — re-export hub."""

from services.tts.audio_generator import TTSAudioGenerator
from services.tts.voice_manager import VIETNAMESE_VOICES

__all__ = ["TTSAudioGenerator", "VIETNAMESE_VOICES"]
