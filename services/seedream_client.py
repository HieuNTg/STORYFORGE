"""ByteDance Seedream 4.5 client — character-consistent image generation."""

import os
import logging
import base64
from typing import Optional

import requests

logger = logging.getLogger(__name__)


class SeedreamClient:
    """Generate images with character consistency via Seedream Edit Sequential API.

    Supports multiple API providers:
    - BytePlus (official): https://visual.volcengineapi.com
    - AIMLAPI: https://api.aimlapi.com/v2
    - WaveSpeed: https://api.wavespeed.ai/v1
    """

    def __init__(self, api_key: str = "", base_url: str = ""):
        self.api_key = api_key or os.environ.get("SEEDREAM_API_KEY", "")
        self.base_url = base_url or os.environ.get(
            "SEEDREAM_API_URL", "https://api.aimlapi.com/v2"
        )
        self.output_dir = "output/images"
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs("output/characters", exist_ok=True)

    def is_configured(self) -> bool:
        """Check if API key is set."""
        return bool(self.api_key)

    def generate_character_reference(
        self, name: str, description: str, filename: str = ""
    ) -> Optional[str]:
        """Generate character reference portrait.
        Returns path to saved image or None."""
        if not self.is_configured():
            logger.warning("Seedream API key not configured")
            return None

        prompt = (
            f"Character portrait for film production. "
            f"{description}. "
            f"Neutral background, studio lighting, photorealistic, "
            f"detailed facial features, cinematic quality, 4K"
        )

        fname = filename or f"{name.lower().replace(' ', '_')}_reference.png"
        output_path = os.path.join("output/characters", fname)

        return self._text_to_image(prompt, output_path)

    def generate_scene(
        self,
        scene_prompt: str,
        reference_images: list,
        filename: str = "scene.png",
    ) -> Optional[str]:
        """Generate scene with character consistency from reference images.

        reference_images: list of file paths to character reference images.
        Returns path to generated scene image or None.
        """
        if not self.is_configured():
            logger.warning("Seedream API key not configured")
            return None

        output_path = os.path.join(self.output_dir, filename)

        if reference_images:
            return self._edit_sequential(scene_prompt, reference_images, output_path)
        else:
            return self._text_to_image(scene_prompt, output_path)

    # ── Private helpers ────────────────────────────────────────────────────────

    def _text_to_image(self, prompt: str, output_path: str) -> Optional[str]:
        """Text-to-image generation."""
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": "seedream-4.5",
                "prompt": prompt,
                "num_images": 1,
                "image_size": {"width": 1024, "height": 1024},
            }
            resp = requests.post(
                f"{self.base_url}/images/generations",
                headers=headers,
                json=payload,
                timeout=60,
            )
            resp.raise_for_status()
            return self._save_response_image(resp.json(), output_path)
        except Exception as e:
            logger.error(f"Seedream text-to-image failed: {e}")
            return None

    def _edit_sequential(
        self, prompt: str, reference_paths: list, output_path: str
    ) -> Optional[str]:
        """Edit Sequential API — maintains character identity from references."""
        try:
            # Read reference images as base64
            image_data = []
            for ref_path in reference_paths[:10]:  # Max 10 references
                if os.path.exists(ref_path):
                    with open(ref_path, "rb") as f:
                        b64 = base64.b64encode(f.read()).decode("utf-8")
                        image_data.append(f"data:image/png;base64,{b64}")

            if not image_data:
                return self._text_to_image(prompt, output_path)

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": "seedream-4.5-edit-sequential",
                "prompt": prompt,
                "images": image_data,
                "num_images": 1,
                "image_size": {"width": 1024, "height": 1024},
            }
            resp = requests.post(
                f"{self.base_url}/images/edits",
                headers=headers,
                json=payload,
                timeout=90,
            )
            resp.raise_for_status()
            return self._save_response_image(resp.json(), output_path)
        except Exception as e:
            logger.error(f"Seedream edit-sequential failed: {e}")
            # Fallback to text-to-image without references
            return self._text_to_image(prompt, output_path)

    def _save_response_image(self, response: dict, output_path: str) -> Optional[str]:
        """Save image from API response (handles b64_json, base64, and url formats)."""
        try:
            data = response.get("data", response.get("results", []))
            if not data:
                return None

            img_data = data[0]

            # Base64 response
            if "b64_json" in img_data:
                raw = base64.b64decode(img_data["b64_json"])
            elif "base64" in img_data:
                raw = base64.b64decode(img_data["base64"])
            # URL response
            elif "url" in img_data:
                resp = requests.get(img_data["url"], timeout=30)
                raw = resp.content
            else:
                logger.error(f"Unknown response format: {list(img_data.keys())}")
                return None

            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
            with open(output_path, "wb") as f:
                f.write(raw)

            logger.info(f"Saved image: {output_path}")
            return output_path
        except Exception as e:
            logger.error(f"Failed to save image: {e}")
            return None
