"""Vietnamese TTS audio generation using edge-tts."""

import asyncio
import logging
import os
import re
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import reduce
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

    def generate_full_audiobook_parallel(
        self, chapters: list, output_dir: str = "output", max_workers: int = 3
    ) -> list:
        """Generate audio for all chapters in parallel. Returns ordered list of .mp3 paths."""
        os.makedirs(output_dir, exist_ok=True)
        results: dict[int, str] = {}

        def _gen_chapter(ch):
            try:
                path = self.generate_chapter_audio(ch.content, ch.chapter_number, output_dir)
                logger.info(f"Generated audio for chapter {ch.chapter_number}")
                return ch.chapter_number, path
            except Exception as e:
                logger.warning(f"Failed chapter {ch.chapter_number}: {e}")
                return ch.chapter_number, None

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_gen_chapter, ch): ch for ch in chapters}
            for future in as_completed(futures):
                ch_num, path = future.result()
                if path:
                    results[ch_num] = path

        # Return paths in chapter order
        return [results[ch.chapter_number] for ch in chapters if ch.chapter_number in results]

    @staticmethod
    def measure_duration(audio_path: str) -> float:
        """Measure audio file duration in seconds using pydub."""
        try:
            from pydub import AudioSegment
            audio = AudioSegment.from_file(audio_path)
            return len(audio) / 1000.0
        except Exception:
            return 5.0  # default 5 seconds

    def assign_voices(self, characters: list) -> dict:
        """Map characters to Vietnamese voices based on gender."""
        mapping = {"narrator": self.voice}
        for char in characters:
            gender = getattr(char, "gender", None)
            if gender and gender.lower() in ("nam", "male", "m"):
                mapping[char.name] = VIETNAMESE_VOICES["male"]
            else:
                mapping[char.name] = VIETNAMESE_VOICES["female"]
        return mapping

    def _segment_dialogue(self, text: str, voice_map: dict) -> list:
        """Split text into dialogue segments by character."""
        segments = []
        pattern = r"(?:^|\n)\s*(?:—\s*)?([^:\n]+?):\s*(.+?)(?=\n\s*(?:—\s*)?[^:\n]+?:|$)"
        last_end = 0
        for match in re.finditer(pattern, text, re.DOTALL):
            if match.start() > last_end:
                narrator_text = text[last_end:match.start()].strip()
                if narrator_text:
                    segments.append({"speaker": "narrator", "text": narrator_text,
                                     "voice": voice_map.get("narrator", self.voice)})
            speaker = match.group(1).strip()
            speech = match.group(2).strip()
            voice = voice_map.get(speaker, voice_map.get("narrator", self.voice))
            segments.append({"speaker": speaker, "text": speech, "voice": voice})
            last_end = match.end()
        if last_end < len(text):
            remaining = text[last_end:].strip()
            if remaining:
                segments.append({"speaker": "narrator", "text": remaining,
                                  "voice": voice_map.get("narrator", self.voice)})
        if not segments:
            segments.append({"speaker": "narrator", "text": text,
                              "voice": voice_map.get("narrator", self.voice)})
        return segments

    def generate_chapter_multivoice(
        self, chapter_text: str, chapter_num: int,
        voice_map: dict, output_dir: str = "output"
    ) -> tuple:
        """Generate multi-voice audio for a chapter. Returns (path, duration_seconds)."""
        os.makedirs(output_dir, exist_ok=True)
        segments = self._segment_dialogue(chapter_text, voice_map)

        segment_paths = []
        for i, seg in enumerate(segments):
            voice = seg.get("voice", voice_map.get("narrator", self.voice))
            seg_path = os.path.join(output_dir, f"ch{chapter_num:02d}_seg{i:03d}.mp3")
            old_voice = self.voice
            self.voice = voice
            try:
                self.generate_audio(seg["text"], seg_path)
                segment_paths.append(seg_path)
            except Exception as e:
                logger.warning(f"TTS segment {i} failed: {e}")
            finally:
                self.voice = old_voice

        if not segment_paths:
            return "", 0.0

        output_path = os.path.join(output_dir, f"chapter_{chapter_num:02d}.mp3")
        if len(segment_paths) == 1:
            shutil.move(segment_paths[0], output_path)
        else:
            try:
                from pydub import AudioSegment
                segments_list = [AudioSegment.from_file(sp) for sp in segment_paths]
                combined = reduce(lambda a, b: a + b, segments_list, AudioSegment.empty())
                combined.export(output_path, format="mp3")
                for sp in segment_paths:
                    try:
                        os.remove(sp)
                    except OSError:
                        pass
            except Exception as e:
                logger.warning(f"Segment merge failed, using first: {e}")
                shutil.move(segment_paths[0], output_path)

        duration = self.measure_duration(output_path)
        return output_path, duration

    @staticmethod
    def list_voices() -> dict:
        """Return available Vietnamese voices."""
        return VIETNAMESE_VOICES.copy()
