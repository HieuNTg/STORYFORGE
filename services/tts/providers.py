"""TTS provider implementations as a mixin class."""

import asyncio
import concurrent.futures
import logging
import os
import threading
from typing import Optional

logger = logging.getLogger(__name__)

VALID_AUDIO_EXTENSIONS = (".wav", ".mp3", ".flac")


class TTSProviderMixin:
    """Mixin providing TTS provider implementations (edge-tts, Kling, XTTS)."""

    VALID_AUDIO_EXTENSIONS = VALID_AUDIO_EXTENSIONS
    _shared_executor: Optional[concurrent.futures.ThreadPoolExecutor] = None
    _executor_lock = threading.Lock()

    @classmethod
    def _get_executor(cls) -> concurrent.futures.ThreadPoolExecutor:
        """Shared ThreadPoolExecutor, lazily created (double-checked locking)."""
        if cls._shared_executor is None:
            with cls._executor_lock:
                if cls._shared_executor is None:
                    cls._shared_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)
        return cls._shared_executor

    async def _generate_edge_tts_async(self, text: str, output_path: str) -> str:
        """Generate audio asynchronously via edge-tts."""
        import edge_tts
        communicate = edge_tts.Communicate(text, self.voice, rate=self.rate, volume=self.volume)
        await communicate.save(output_path)
        return output_path

    async def _generate_async(self, text: str, output_path: str) -> str:
        """Backward-compat alias for _generate_edge_tts_async (used by existing tests)."""
        return await self._generate_edge_tts_async(text, output_path)

    def _generate_edge_tts(self, text: str, output_path: str) -> str:
        """Generate via edge-tts (sync wrapper, handles running event loop)."""
        try:
            try:
                asyncio.get_running_loop()
                running = True
            except RuntimeError:
                running = False
            if running:
                return self._get_executor().submit(
                    asyncio.run, self._generate_async(text, output_path)
                ).result(timeout=300)
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
            headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
            payload = {"text": text, "voice": self.voice, "speed": self.rate, "format": "mp3"}
            resp = requests.post(f"{self.api_url}/tts/generate", headers=headers, json=payload, timeout=120)
            resp.raise_for_status()
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
        """Generate via XTTS v2 API (Coqui local or Replicate). Returns path or None."""
        if not self.xtts_api_url:
            logger.warning("XTTS skipped: xtts_api_url not configured")
            return None
        ref_audio = reference_audio or self.xtts_reference_audio
        if not ref_audio:
            logger.warning("XTTS skipped: no reference audio configured")
            return None
        ext = os.path.splitext(ref_audio)[1].lower()
        if ext not in self.VALID_AUDIO_EXTENSIONS:
            logger.warning("XTTS skipped: unsupported audio extension %s", ext)
            return None
        if not os.path.exists(ref_audio):
            logger.warning("XTTS skipped: reference audio not found: %s", ref_audio)
            return None
        from config import ConfigManager
        lang = language or ConfigManager().pipeline.language or "vi"
        try:
            import requests
            if "replicate" in self.xtts_api_url.lower():
                return self._generate_xtts_replicate(text, output_path, ref_audio, lang)
            with open(ref_audio, "rb") as f:
                audio_bytes = f.read()
            files = {"speaker_wav": (os.path.basename(ref_audio), audio_bytes, "audio/wav")}
            resp = requests.post(
                f"{self.xtts_api_url.rstrip('/')}/tts_to_audio/",
                files=files, data={"text": text, "language": lang}, timeout=60,
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
        self, text: str, output_path: str, ref_audio: str, language: str,
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
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {
            "version": "f559560eb822dc509045f3921a1921234918b91739db4bf3daab2169b71c7a13",
            "input": {"text": text, "speaker_wav": f"data:audio/wav;base64,{audio_b64}", "language": language},
        }
        resp = requests.post(
            "https://api.replicate.com/v1/predictions", headers=headers, json=payload, timeout=30
        )
        resp.raise_for_status()
        prediction_id = resp.json().get("id")
        deadline = time.time() + 120
        while time.time() < deadline:
            poll = requests.get(
                f"https://api.replicate.com/v1/predictions/{prediction_id}",
                headers=headers, timeout=15,
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

    def _resolve_xtts_reference(self, emotion: str = "") -> str:
        """Resolve reference audio, preferring emotion-specific variant."""
        if emotion and self.xtts_reference_audio:
            base, ext = os.path.splitext(self.xtts_reference_audio)
            emotion_path = f"{base}_{emotion}{ext}"
            if os.path.exists(emotion_path):
                return emotion_path
        return self.xtts_reference_audio or ""
