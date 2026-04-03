# Shim: re-exports from new location for backward compatibility
from services.media.tts_audio_generator import TTSAudioGenerator, VIETNAMESE_VOICES

__all__ = ["TTSAudioGenerator", "VIETNAMESE_VOICES"]
