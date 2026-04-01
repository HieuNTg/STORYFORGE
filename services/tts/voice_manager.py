"""Voice assignment and dialogue segmentation mixin."""

import logging
import os
import re

logger = logging.getLogger(__name__)

# Vietnamese voices available in edge-tts
VIETNAMESE_VOICES = {
    "female": "vi-VN-HoaiMyNeural",
    "male": "vi-VN-NamMinhNeural",
}


class TTSVoiceMixin:
    """Mixin providing voice assignment and dialogue segmentation."""

    @staticmethod
    def measure_duration(audio_path: str) -> float:
        """Measure audio file duration in seconds using pydub."""
        try:
            from pydub import AudioSegment

            audio = AudioSegment.from_file(audio_path)
            return len(audio) / 1000.0
        except Exception as e:
            logger.debug(f"Duration measure failed: {e}")
            return 5.0  # default 5 seconds

    def assign_voices(self, characters: list) -> dict:
        """Map characters to voices. For xtts provider returns reference audio paths."""
        if self.provider == "xtts":
            return self._assign_voices_xtts(characters)

        mapping = {"narrator": self.voice}
        for char in characters:
            gender = getattr(char, "gender", None)
            if gender and gender.lower() in ("nam", "male", "m"):
                mapping[char.name] = VIETNAMESE_VOICES["male"]
            else:
                mapping[char.name] = VIETNAMESE_VOICES["female"]
        return mapping

    def _assign_voices_xtts(self, characters: list) -> dict:
        """Map characters to reference audio paths for XTTS provider."""
        mapping = {"narrator": self.xtts_reference_audio or self.voice}
        for char in characters:
            name = getattr(char, "name", str(char))
            ref = self.character_voice_map.get(name, self.xtts_reference_audio)
            if ref:
                if not os.path.exists(ref):
                    logger.warning("XTTS voice file missing for %s: %s", name, ref)
                mapping[name] = ref
            else:
                logger.warning("XTTS no reference audio for %s, using default voice", name)
                mapping[name] = self.voice
        return mapping

    def _segment_dialogue(self, text: str, voice_map: dict) -> list:
        """Split text into dialogue segments by character."""
        segments = []
        pattern = r"(?:^|\n)\s*(?:—\s*)?([^:\n]+?):\s*(.+?)(?=\n\s*(?:—\s*)?[^:\n]+?:|$)"
        last_end = 0
        for match in re.finditer(pattern, text, re.DOTALL):
            if match.start() > last_end:
                narrator_text = text[last_end : match.start()].strip()
                if narrator_text:
                    segments.append(
                        {
                            "speaker": "narrator",
                            "text": narrator_text,
                            "voice": voice_map.get("narrator", self.voice),
                        }
                    )
            speaker = match.group(1).strip()
            speech = match.group(2).strip()
            voice = voice_map.get(speaker, voice_map.get("narrator", self.voice))
            segments.append({"speaker": speaker, "text": speech, "voice": voice})
            last_end = match.end()
        if last_end < len(text):
            remaining = text[last_end:].strip()
            if remaining:
                segments.append(
                    {
                        "speaker": "narrator",
                        "text": remaining,
                        "voice": voice_map.get("narrator", self.voice),
                    }
                )
        if not segments:
            segments.append(
                {"speaker": "narrator", "text": text, "voice": voice_map.get("narrator", self.voice)}
            )
        return segments

    @staticmethod
    def list_voices() -> dict:
        """Return available Vietnamese voices."""
        return VIETNAMESE_VOICES.copy()
