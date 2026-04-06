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

    def generate_scene(self, prompt: str, reference_images: Optional[list] = None, filename: str = "scene.png", **kwargs) -> Optional[str]:
        """Generate a scene/background image. Returns image path or None.

        Falls back to IP-Adapter if Seedream is unavailable.
        """
        try:
            return self.seedream.generate_scene(prompt, reference_images or [], filename)
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

    def generate_character(self, prompt: str, reference_image: Optional[str] = None, filename: str = "character.png", **kwargs) -> Optional[str]:
        """Generate a character-consistent image. Uses IP-Adapter if reference available."""
        if reference_image:
            try:
                return self.ip_adapter.generate(prompt, reference_image, filename)
            except Exception as e:
                logger.warning(f"IP-Adapter character gen failed: {e}")
        return self.generate_scene(prompt, filename=filename)

    def generate_character_reference(self, name: str, description: str, filename: str = "") -> Optional[str]:
        """Generate a character reference portrait via Seedream."""
        try:
            return self.seedream.generate_character_reference(name, description, filename)
        except Exception as e:
            logger.error(f"Character reference generation failed for {name!r}: {e}")
            return None

    def is_configured(self) -> bool:
        """Return True if at least one provider is configured."""
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
