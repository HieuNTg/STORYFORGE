"""AI image generation from story prompts — supports DALL-E and SD-compatible APIs."""

import os
import logging
import base64
from typing import Optional

import requests

from config import ConfigManager

logger = logging.getLogger(__name__)


class ImageGenerator:
    """Generate images from prompts using various AI providers."""

    PROVIDERS = ["dalle", "sd-api", "seedream", "none"]  # none = prompt-only mode

    def __init__(self, provider: str = "none", api_key: str = "", base_url: str = ""):
        cfg = ConfigManager().pipeline
        self.provider = provider or cfg.image_provider
        self.api_key = api_key or cfg.image_api_key or os.environ.get("IMAGE_API_KEY", "")
        self.base_url = (
            base_url
            or cfg.image_api_url
            or os.environ.get("IMAGE_API_URL", "https://api.openai.com/v1")
        )
        self.output_dir = "output/images"
        os.makedirs(self.output_dir, exist_ok=True)

    # ── Public API ────────────────────────────────────────────────────────────

    def generate(
        self, prompt: str, filename: str = "image.png", size: str = "1024x1024"
    ) -> Optional[str]:
        """Generate image from prompt. Returns saved file path or None."""
        if self.provider == "none":
            logger.info("Image gen disabled (prompt-only mode). Prompt: %.100s...", prompt)
            return None

        if self.provider == "dalle":
            return self._generate_dalle(prompt, filename, size)
        if self.provider == "sd-api":
            return self._generate_sd(prompt, filename)
        if self.provider == "seedream":
            return self._generate_seedream(prompt, filename)

        logger.warning("Unknown image provider: %s", self.provider)
        return None

    def generate_story_images(
        self, image_prompts: list, chapter_number: int = 0
    ) -> list[str]:
        """Generate images for a list of ImagePrompt objects. Returns saved paths."""
        paths: list[str] = []
        for i, ip in enumerate(image_prompts):
            prompt = ip.dalle_prompt if self.provider == "dalle" else ip.sd_prompt
            if not prompt:
                prompt = ip.scene_description
            filename = f"ch{chapter_number:02d}_panel{i + 1:02d}.png"
            path = self.generate(prompt, filename)
            if path:
                paths.append(path)
        return paths

    # ── Private providers ─────────────────────────────────────────────────────

    def _generate_dalle(self, prompt: str, filename: str, size: str) -> Optional[str]:
        """Generate via OpenAI DALL-E 3 API."""
        if not self.api_key:
            logger.error("DALL-E generation skipped: no api_key configured.")
            return None
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": "dall-e-3",
                "prompt": prompt,
                "n": 1,
                "size": size,
                "response_format": "b64_json",
            }
            resp = requests.post(
                f"{self.base_url}/images/generations",
                headers=headers,
                json=payload,
                timeout=60,
            )
            resp.raise_for_status()

            b64_data = resp.json()["data"][0]["b64_json"]
            filepath = os.path.join(self.output_dir, filename)
            with open(filepath, "wb") as f:
                f.write(base64.b64decode(b64_data))

            logger.info("Generated DALL-E image: %s", filepath)
            return filepath
        except Exception as e:
            logger.error("DALL-E generation failed: %s", e)
            return None

    def _generate_sd(self, prompt: str, filename: str) -> Optional[str]:
        """Generate via SD-compatible API (Automatic1111, ComfyUI, etc.)."""
        try:
            payload = {
                "prompt": prompt,
                "negative_prompt": "text, watermark, blurry, low quality, deformed",
                "steps": 30,
                "width": 1024,
                "height": 1024,
            }
            resp = requests.post(
                f"{self.base_url}/sdapi/v1/txt2img",
                json=payload,
                timeout=120,
            )
            resp.raise_for_status()

            b64_data = resp.json()["images"][0]
            filepath = os.path.join(self.output_dir, filename)
            with open(filepath, "wb") as f:
                f.write(base64.b64decode(b64_data))

            logger.info("Generated SD image: %s", filepath)
            return filepath
        except Exception as e:
            logger.error("SD generation failed: %s", e)
            return None

    def _generate_seedream(self, prompt: str, filename: str) -> Optional[str]:
        """Generate via ByteDance Seedream API (delegates to SeedreamClient)."""
        from services.seedream_client import SeedreamClient  # local import avoids circular deps

        cfg = ConfigManager().pipeline
        client = SeedreamClient(
            api_key=cfg.seedream_api_key,
            base_url=cfg.seedream_api_url,
        )
        if not client.is_configured():
            logger.error("Seedream generation skipped: no seedream_api_key configured.")
            return None

        filepath = os.path.join(self.output_dir, filename)
        result = client._text_to_image(prompt, filepath)
        if result:
            logger.info("Generated Seedream image: %s", result)
        return result
