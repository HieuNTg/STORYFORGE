"""Vietnamese TTS audio generation — supports edge-tts, Kling TTS API, and XTTS v2."""

import asyncio
import concurrent.futures
import logging
import os
import re
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import reduce
from typing import Optional

from config import ConfigManager

logger = logging.getLogger(__name__)

# Vietnamese voices available in edge-tts
VIETNAMESE_VOICES = {
    "female": "vi-VN-HoaiMyNeural",
    "male": "vi-VN-NamMinhNeural",
}


class TTSAudioGenerator:
    """Generate audio files from text using pluggable TTS providers."""

    PROVIDERS = ["edge-tts", "kling", "xtts", "none"]

    VALID_AUDIO_EXTENSIONS = (".wav", ".mp3", ".flac")

    _shared_executor: Optional[concurrent.futures.ThreadPoolExecutor] = None
    _executor_lock = threading.Lock()

    @classmethod
    def _get_executor(cls) -> concurrent.futures.ThreadPoolExecutor:
        """Return the shared ThreadPoolExecutor, creating it lazily (double-checked locking)."""
        if cls._shared_executor is None:
            with cls._executor_lock:
                if cls._shared_executor is None:
                    cls._shared_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)
        return cls._shared_executor

    def __init__(
        self,
        provider: str = "",
        voice: str = "female",
        rate: str = "+0%",
        volume: str = "+0%",
        api_key: str = "",
        api_url: str = "",
        xtts_api_url: str = "",
        xtts_reference_audio: str = "",
    ):
        cfg = ConfigManager().pipeline
        self.provider = provider or cfg.tts_provider or "edge-tts"
        self.api_key = api_key or cfg.kling_tts_api_key or os.environ.get("KLING_TTS_API_KEY", "")
        self.api_url = api_url or cfg.kling_tts_api_url or os.environ.get("KLING_TTS_API_URL", "")
        self.xtts_api_url = (
            xtts_api_url
            or cfg.xtts_api_url
            or os.environ.get("XTTS_API_URL", "")
        )
        self.xtts_reference_audio = (
            xtts_reference_audio
            or cfg.xtts_reference_audio
            or os.environ.get("XTTS_REFERENCE_AUDIO", "")
        )
        self.character_voice_map: dict = cfg.character_voice_map or {}
        self.voice = VIETNAMESE_VOICES.get(voice, voice)
        self.rate = rate
        self.volume = volume

    # ── Async helper for edge-tts ─────────────────────────────────────────────

    async def _generate_edge_tts_async(self, text: str, output_path: str) -> str:
        """Generate audio file asynchronously via edge-tts."""
        import edge_tts

        communicate = edge_tts.Communicate(text, self.voice, rate=self.rate, volume=self.volume)
        await communicate.save(output_path)
        return output_path

    async def _generate_async(self, text: str, output_path: str) -> str:
        """Backward-compat alias for _generate_edge_tts_async (used by existing tests)."""
        return await self._generate_edge_tts_async(text, output_path)

    # ── Public API ────────────────────────────────────────────────────────────

    def generate_audio(self, text: str, output_path: str) -> Optional[str]:
        """Generate audio file from text. Returns path to .mp3 file or None."""
        if self.provider == "none":
            logger.info("TTS disabled (none provider)")
            return None

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        if self.provider == "kling":
            return self._generate_kling(text, output_path)

        if self.provider == "xtts":
            result = self._generate_xtts(text, output_path)
            if result is None:
                logger.warning("XTTS failed, falling back to edge-tts")
                return self._generate_edge_tts(text, output_path)
            return result

        # Default: edge-tts
        return self._generate_edge_tts(text, output_path)

    def generate_chapter_audio(
        self, chapter_text: str, chapter_num: int, output_dir: str = "output"
    ) -> Optional[str]:
        """Generate audio for a single chapter."""
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"chapter_{chapter_num:02d}.mp3")
        return self.generate_audio(chapter_text, output_path)

    def generate_full_audiobook(self, chapters: list, output_dir: str = "output") -> list:
        """Generate audio for all chapters. Returns list of .mp3 paths (skips None)."""
        os.makedirs(output_dir, exist_ok=True)
        paths = []
        for ch in chapters:
            try:
                path = self.generate_chapter_audio(ch.content, ch.chapter_number, output_dir)
                if path:
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
                if path:
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

    # ── Private providers ─────────────────────────────────────────────────────

    def _generate_edge_tts(self, text: str, output_path: str) -> str:
        """Generate via edge-tts."""
        try:
            try:
                loop = asyncio.get_running_loop()
                running = True
            except RuntimeError:
                running = False

            if running:
                result = self._get_executor().submit(
                    asyncio.run, self._generate_async(text, output_path)
                ).result(timeout=300)
                return result
            else:
                return asyncio.run(self._generate_async(text, output_path))
        except Exception as e:
            logger.error(f"TTS generation failed: {e}")
            raise

    def _generate_kling(self, text: str, output_path: str) -> Optional[str]:
        """Generate via Kling TTS API."""
        if not self.api_key:
            logger.error("Kling TTS skipped: no api_key configured")
            return None
        try:
            import requests

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "text": text,
                "voice": self.voice,
                "speed": self.rate,
                "format": "mp3",
            }
            resp = requests.post(
                f"{self.api_url}/tts/generate",
                headers=headers,
                json=payload,
                timeout=120,
            )
            resp.raise_for_status()

            # Handle response — binary audio or JSON with base64
            content_type = resp.headers.get("Content-Type", "")
            if "audio" in content_type or "octet-stream" in content_type:
                with open(output_path, "wb") as f:
                    f.write(resp.content)
            else:
                import base64

                data = resp.json()
                audio_data = data.get("audio", data.get("data", ""))
                with open(output_path, "wb") as f:
                    f.write(base64.b64decode(audio_data))

            logger.info("Generated Kling TTS: %s", output_path)
            return output_path
        except Exception as e:
            logger.error("Kling TTS failed: %s", e)
            return None

    def _generate_xtts(
        self,
        text: str,
        output_path: str,
        reference_audio: Optional[str] = None,
        language: str = "",
    ) -> Optional[str]:
        """Generate via XTTS v2 API (Coqui local server or Replicate).

        Args:
            text: Text to synthesize.
            output_path: Destination file path.
            reference_audio: Override reference audio path (per-character).
            language: Language code (defaults to config language).

        Returns:
            output_path on success, None on failure (caller should fallback).
        """
        if not self.xtts_api_url:
            logger.warning("XTTS skipped: xtts_api_url not configured")
            return None

        ref_audio = reference_audio or self.xtts_reference_audio
        if not ref_audio:
            logger.warning("XTTS skipped: no reference audio configured")
            return None

        # Validate extension
        ext = os.path.splitext(ref_audio)[1].lower()
        if ext not in self.VALID_AUDIO_EXTENSIONS:
            logger.warning("XTTS skipped: unsupported audio extension %s", ext)
            return None

        if not os.path.exists(ref_audio):
            logger.warning("XTTS skipped: reference audio not found: %s", ref_audio)
            return None

        cfg_lang = ConfigManager().pipeline.language or "vi"
        lang = language or cfg_lang

        try:
            import requests

            if "replicate" in self.xtts_api_url.lower():
                return self._generate_xtts_replicate(text, output_path, ref_audio, lang)

            # Local Coqui TTS server
            with open(ref_audio, "rb") as f:
                audio_bytes = f.read()

            files = {"speaker_wav": (os.path.basename(ref_audio), audio_bytes, "audio/wav")}
            data = {"text": text, "language": lang}

            resp = requests.post(
                f"{self.xtts_api_url.rstrip('/')}/tts_to_audio/",
                files=files,
                data=data,
                timeout=60,
            )
            resp.raise_for_status()

            with open(output_path, "wb") as f:
                f.write(resp.content)

            logger.info("XTTS generated: %s", output_path)
            return output_path

        except Exception as e:
            logger.warning("XTTS generation failed: %s", e)
            return None

    def _generate_xtts_replicate(
        self,
        text: str,
        output_path: str,
        ref_audio: str,
        language: str,
    ) -> Optional[str]:
        """Generate via Replicate API for XTTS v2."""
        import base64
        import time

        import requests

        api_key = os.environ.get("REPLICATE_API_TOKEN", "")
        if not api_key:
            logger.warning("XTTS Replicate skipped: REPLICATE_API_TOKEN not set")
            return None

        with open(ref_audio, "rb") as f:
            audio_b64 = base64.b64encode(f.read()).decode()

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "version": "f559560eb822dc509045f3921a1921234918b91739db4bf3daab2169b71c7a13",
            "input": {
                "text": text,
                "speaker_wav": f"data:audio/wav;base64,{audio_b64}",
                "language": language,
            },
        }

        resp = requests.post(
            "https://api.replicate.com/v1/predictions",
            headers=headers,
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        prediction = resp.json()
        prediction_id = prediction.get("id")

        # Poll for result (max 120 seconds)
        deadline = time.time() + 120
        while time.time() < deadline:
            poll = requests.get(
                f"https://api.replicate.com/v1/predictions/{prediction_id}",
                headers=headers,
                timeout=15,
            )
            poll.raise_for_status()
            result = poll.json()
            status = result.get("status")
            if status == "succeeded":
                audio_url = result.get("output")
                if not audio_url:
                    logger.warning("XTTS Replicate: no output URL in response")
                    return None
                audio_resp = requests.get(audio_url, timeout=60)
                audio_resp.raise_for_status()
                with open(output_path, "wb") as f:
                    f.write(audio_resp.content)
                logger.info("XTTS Replicate generated: %s", output_path)
                return output_path
            elif status in ("failed", "canceled"):
                logger.warning("XTTS Replicate prediction %s: %s", prediction_id, status)
                return None
            time.sleep(3)

        logger.warning("XTTS Replicate prediction %s timed out", prediction_id)
        return None

    # ── Utility / helpers ─────────────────────────────────────────────────────

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

    def generate_chapter_multivoice(
        self,
        chapter_text: str,
        chapter_num: int,
        voice_map: dict,
        output_dir: str = "output",
    ) -> tuple:
        """Generate multi-voice audio for a chapter. Returns (path, duration_seconds)."""
        os.makedirs(output_dir, exist_ok=True)
        segments = self._segment_dialogue(chapter_text, voice_map)

        segment_paths = []
        for i, seg in enumerate(segments):
            voice = seg.get("voice", voice_map.get("narrator", self.voice))
            seg_path = os.path.join(output_dir, f"ch{chapter_num:02d}_seg{i:03d}.mp3")

            # When voice value is a file path, use XTTS directly with that reference
            is_file_path = isinstance(voice, str) and os.path.splitext(voice)[1].lower() in self.VALID_AUDIO_EXTENSIONS
            if is_file_path and self.provider == "xtts":
                try:
                    os.makedirs(os.path.dirname(seg_path) or ".", exist_ok=True)
                    result = self._generate_xtts(seg["text"], seg_path, reference_audio=voice)
                    if result is None:
                        result = self._generate_edge_tts(seg["text"], seg_path)
                    if result:
                        segment_paths.append(seg_path)
                except Exception as e:
                    logger.warning(f"TTS segment {i} failed: {e}")
                continue

            old_voice = self.voice
            self.voice = voice
            try:
                result = self.generate_audio(seg["text"], seg_path)
                if result:
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

    @staticmethod
    def list_providers() -> list:
        """Return available TTS providers."""
        return TTSAudioGenerator.PROVIDERS.copy()
