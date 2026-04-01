"""Main TTSAudioGenerator class composing provider and voice mixins."""

import logging
import os
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import reduce
from typing import Optional

from services.tts.providers import TTSProviderMixin
from services.tts.voice_manager import TTSVoiceMixin, VIETNAMESE_VOICES

logger = logging.getLogger(__name__)


def _get_config_manager():
    """Late import of ConfigManager — allows test patching via services.tts_audio_generator."""
    from services import tts_audio_generator as _hub  # noqa: PLC0415
    return _hub.ConfigManager


def _get_emotion_helpers():
    """Late import of emotion helpers — allows test patching via services.tts_audio_generator."""
    from services import tts_audio_generator as _hub  # noqa: PLC0415
    return _hub.classify_emotion, _hub.get_voice_params


class TTSAudioGenerator(TTSProviderMixin, TTSVoiceMixin):
    """Generate audio files from text using pluggable TTS providers."""

    PROVIDERS = ["edge-tts", "kling", "xtts", "none"]

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
        ConfigManager = _get_config_manager()
        cfg = ConfigManager().pipeline
        self._rate_lock = threading.Lock()
        self.provider = provider or cfg.tts_provider or "edge-tts"
        self.api_key = api_key or cfg.kling_tts_api_key or os.environ.get("KLING_TTS_API_KEY", "")
        self.api_url = api_url or cfg.kling_tts_api_url or os.environ.get("KLING_TTS_API_URL", "")
        self.xtts_api_url = xtts_api_url or cfg.xtts_api_url or os.environ.get("XTTS_API_URL", "")
        self.xtts_reference_audio = (
            xtts_reference_audio or cfg.xtts_reference_audio or os.environ.get("XTTS_REFERENCE_AUDIO", "")
        )
        self.character_voice_map: dict = cfg.character_voice_map or {}
        self.voice = VIETNAMESE_VOICES.get(voice, voice)
        self.rate = rate
        self.volume = volume

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
        return self._generate_edge_tts(text, output_path)

    def generate_chapter_audio(
        self,
        chapter_text: str,
        chapter_num: int,
        output_dir: str = "output",
        emotion: str = "",
    ) -> Optional[str]:
        """Generate audio for a single chapter with optional emotion modulation."""
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"chapter_{chapter_num:02d}.mp3")
        ConfigManager = _get_config_manager()
        cfg = ConfigManager().pipeline
        if cfg.enable_voice_emotion and not emotion:
            classify_emotion, _ = _get_emotion_helpers()
            emotion = classify_emotion(chapter_text)
        if emotion:
            logger.info("Chapter %d emotion: %s", chapter_num, emotion)
            _, get_voice_params = _get_emotion_helpers()
            params = get_voice_params(emotion)
            with self._rate_lock:
                saved_rate = self.rate
                self.rate = params["rate"]
            try:
                return self.generate_audio(chapter_text, output_path)
            finally:
                with self._rate_lock:
                    self.rate = saved_rate
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
        return [results[ch.chapter_number] for ch in chapters if ch.chapter_number in results]

    def generate_chapter_multivoice(
        self, chapter_text: str, chapter_num: int, voice_map: dict, output_dir: str = "output",
    ) -> tuple:
        """Generate multi-voice audio for a chapter. Returns (path, duration_seconds)."""
        os.makedirs(output_dir, exist_ok=True)
        segments = self._segment_dialogue(chapter_text, voice_map)
        segment_paths = []
        for i, seg in enumerate(segments):
            voice = seg.get("voice", voice_map.get("narrator", self.voice))
            seg_path = os.path.join(output_dir, f"ch{chapter_num:02d}_seg{i:03d}.mp3")
            is_file_path = (
                isinstance(voice, str)
                and os.path.splitext(voice)[1].lower() in self.VALID_AUDIO_EXTENSIONS
            )
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
                segs = [AudioSegment.from_file(sp) for sp in segment_paths]
                combined = reduce(lambda a, b: a + b, segs, AudioSegment.empty())
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
    def list_providers() -> list:
        """Return available TTS providers."""
        return TTSAudioGenerator.PROVIDERS.copy()
