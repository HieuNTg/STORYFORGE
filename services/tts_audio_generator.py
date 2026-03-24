"""Vietnamese TTS audio generation using edge-tts."""

import asyncio
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# Vietnamese voices available in edge-tts
VIETNAMESE_VOICES = {
    "female": "vi-VN-HoaiMyNeural",
    "male": "vi-VN-NamMinhNeural",
}


class TTSAudioGenerator:
    """Generate audio files from text using edge-tts."""

    def __init__(self, voice: str = "female", rate: str = "+0%", volume: str = "+0%"):
        self.voice = VIETNAMESE_VOICES.get(voice, voice)
        self.rate = rate
        self.volume = volume

    async def _generate_async(self, text: str, output_path: str) -> str:
        """Generate audio file asynchronously."""
        import edge_tts

        communicate = edge_tts.Communicate(text, self.voice, rate=self.rate, volume=self.volume)
        await communicate.save(output_path)
        return output_path

    def generate_audio(self, text: str, output_path: str) -> str:
        """Generate audio file from text. Returns path to .mp3 file."""
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        try:
            try:
                loop = asyncio.get_running_loop()
                running = True
            except RuntimeError:
                running = False

            if running:
                # Already in async context — run in a new thread with its own loop
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor() as pool:
                    result = pool.submit(
                        asyncio.run, self._generate_async(text, output_path)
                    ).result(timeout=300)
                return result
            else:
                return asyncio.run(self._generate_async(text, output_path))
        except Exception as e:
            logger.error(f"TTS generation failed: {e}")
            raise

    def generate_chapter_audio(
        self, chapter_text: str, chapter_num: int, output_dir: str = "output"
    ) -> str:
        """Generate audio for a single chapter."""
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"chapter_{chapter_num:02d}.mp3")
        return self.generate_audio(chapter_text, output_path)

    def generate_full_audiobook(self, chapters: list, output_dir: str = "output") -> list:
        """Generate audio for all chapters. Returns list of .mp3 paths."""
        os.makedirs(output_dir, exist_ok=True)
        paths = []
        for ch in chapters:
            try:
                path = self.generate_chapter_audio(ch.content, ch.chapter_number, output_dir)
                paths.append(path)
                logger.info(f"Generated audio for chapter {ch.chapter_number}")
            except Exception as e:
                logger.warning(f"Failed chapter {ch.chapter_number}: {e}")
        return paths

    @staticmethod
    def list_voices() -> dict:
        """Return available Vietnamese voices."""
        return VIETNAMESE_VOICES.copy()
