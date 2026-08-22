"""Unified image generation interface — wraps IP-Adapter and Seedream behind a single API."""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class ImageProvider:
    """Single entry point for image generation.

    Delegates to Seedream (primary) or IP-Adapter (character consistency) based on task.
    Existing clients (SeedreamClient, ReplicateIPAdapter) are unchanged — this is an
    abstraction layer only.
    """

    def __init__(self):
        self._seedream = None
        self._ip_adapter = None
        self._qwen_local = None

    @property
    def seedream(self):
        if self._seedream is None:
            from services.seedream_client import SeedreamClient

            self._seedream = SeedreamClient()
        return self._seedream

    @property
    def ip_adapter(self):
        if self._ip_adapter is None:
            from services.replicate_ip_adapter import ReplicateIPAdapter

            self._ip_adapter = ReplicateIPAdapter()
        return self._ip_adapter

    @property
    def qwen_local(self):
        if self._qwen_local is None:
            from config import ConfigManager
            from services.media.qwen_local_client import QwenLocalClient

            cfg = ConfigManager().pipeline
            self._qwen_local = QwenLocalClient(
                base_url=getattr(cfg, "qwen_local_base_url", ""),
                api_key=getattr(cfg, "qwen_local_api_key", ""),
                model=getattr(cfg, "qwen_local_model", ""),
                size=getattr(cfg, "qwen_local_size", ""),
                timeout=getattr(cfg, "qwen_local_timeout", 300.0),
            )
        return self._qwen_local

    def generate_scene(
        self,
        prompt: str,
        reference_images: Optional[list] = None,
        filename: str = "scene.png",
        **kwargs,
    ) -> Optional[str]:
        """Generate a scene/background image. Returns image path or None.

        Falls back to IP-Adapter if Seedream is unavailable.
        """
        try:
            return self.seedream.generate_scene(
                prompt, reference_images or [], filename
            )
        except Exception as e:
            logger.warning(f"Seedream failed, trying IP-Adapter: {e}")
            try:
                ref = (reference_images or [None])[0]
                if ref:
                    return self.ip_adapter.generate(prompt, ref, filename)
                return None
            except Exception as e2:
                logger.error(f"All image providers failed: {e2}")
                return None

    def generate_character(
        self,
        prompt: str,
        reference_image: Optional[str] = None,
        filename: str = "character.png",
        **kwargs,
    ) -> Optional[str]:
        """Generate a character-consistent image. Uses IP-Adapter if reference available."""
        if reference_image:
            try:
                return self.ip_adapter.generate(prompt, reference_image, filename)
            except Exception as e:
                logger.warning(f"IP-Adapter character gen failed: {e}")
        return self.generate_scene(prompt, filename=filename)

    def generate_character_reference(
        self, name: str, description: str, filename: str = ""
    ) -> Optional[str]:
        """Generate a character reference portrait.

        Routed to the Qwen local proxy when that is the selected provider, so
        the panels generated later have a reference to stay consistent with;
        otherwise Seedream, as before.
        """
        try:
            from config import ConfigManager

            if ConfigManager().pipeline.image_provider == "qwen-local":
                return self._qwen_local_reference(name, description, filename)
        except Exception as e:
            logger.warning(f"Qwen local reference routing failed for {name!r}: {e}")
        try:
            return self.seedream.generate_character_reference(
                name, description, filename
            )
        except Exception as e:
            logger.error(f"Character reference generation failed for {name!r}: {e}")
            return None

    def _qwen_local_reference(
        self, name: str, description: str, filename: str = ""
    ) -> Optional[str]:
        """Portrait through the Qwen proxy, saved where Seedream would put it."""
        import os
        import re

        from services.output_paths import OUTPUT_ROOT

        from services.media._util import COLOR_CLAUSE

        prompt = (
            f"Character portrait for film production. "
            f"{description}. "
            f"Neutral background, studio lighting, photorealistic, "
            f"detailed facial features, cinematic quality, 4K, {COLOR_CLAUSE}"
        )
        safe_name = re.sub(r"[^\w\-.]", "_", name.lower())
        output_path = os.path.join(
            OUTPUT_ROOT, "characters", filename or f"{safe_name}_reference.png"
        )
        return self.qwen_local.text_to_image(prompt, output_path)

    def is_configured(self) -> bool:
        """Return True if at least one provider is configured.

        FlowKit counts as configured only when the Chrome extension is currently
        connected — without an active WS the proxy can't reach Google Labs. The
        Qwen local proxy is judged on config alone: probing it costs an HTTP
        round-trip and this runs once per character.
        """
        try:
            from config import ConfigManager

            cfg = ConfigManager().pipeline
            if cfg.image_provider == "flowkit":
                from services.media.flow_service import FlowService

                flow_service = FlowService()
                return bool(cfg.flowkit_enabled and flow_service.active_ws is not None)
            if cfg.image_provider == "qwen-local":
                return self.qwen_local.is_configured()
        except Exception:
            pass
        try:
            if self.seedream.is_configured():
                return True
        except Exception:
            pass
        try:
            if self.ip_adapter.is_configured():
                return True
        except Exception:
            pass
        return False
