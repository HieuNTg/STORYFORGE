"""ByteDance Seedream 4.5 client — character-consistent image generation."""

import os
import re
import logging
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Optional

import requests

MAX_REF_SIZE = 10 * 1024 * 1024  # 10MB

logger = logging.getLogger(__name__)


@dataclass
class ImageResult:
    """Result wrapper for a single image generation attempt."""
    prompt: str
    image_url: Optional[str] = None
    error: Optional[str] = None
    success: bool = True


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

        safe_name = re.sub(r'[^\w\-.]', '_', name.lower())
        fname = filename or f"{safe_name}_reference.png"
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

    def batch_generate(
        self, requests_list: list[dict], max_workers: int = 5
    ) -> list[ImageResult]:
        """Generate multiple scenes in parallel. Returns partial results on failure.

        Each dict in requests_list must include the kwargs accepted by generate_scene():
        scene_prompt, reference_images, and optionally filename.
        """
        if not requests_list:
            return []

        results: list[ImageResult] = []
        with ThreadPoolExecutor(max_workers=min(max_workers, len(requests_list))) as executor:
            futures = {
                executor.submit(self.generate_scene, **req): req
                for req in requests_list
            }
            for future in as_completed(futures):
                req = futures[future]
                prompt = req.get("scene_prompt", "")
                try:
                    path = future.result()
                    results.append(ImageResult(prompt=prompt, image_url=path))
                except Exception as e:
                    logger.error("Batch scene generation failed for %r: %s", prompt, e)
                    results.append(ImageResult(prompt=prompt, error=str(e), success=False))
        return results

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
                if not os.path.exists(ref_path):
                    continue
                if os.path.getsize(ref_path) > MAX_REF_SIZE:
                    logger.warning(f"Skipping reference image (too large >10MB): {ref_path}")
                    continue
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
