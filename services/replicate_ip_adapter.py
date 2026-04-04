"""Replicate IP-Adapter client for character-consistent image generation."""
import os
import logging
import base64
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Optional
from config import ConfigManager

logger = logging.getLogger(__name__)


@dataclass
class ImageResult:
    """Result wrapper for a single image generation attempt."""
    prompt: str
    image_url: Optional[str] = None
    error: Optional[str] = None
    success: bool = True


class ReplicateIPAdapter:
    """Generate character-conditioned images via Replicate IP-Adapter API."""

    DEFAULT_MODEL = "tencentarc/ip-adapter-faceid-sdxl"
    API_URL = "https://api.replicate.com/v1/predictions"

    def __init__(self, api_key: str = "", model: str = ""):
        cfg = ConfigManager().pipeline
        self.api_key = api_key or cfg.replicate_api_key or os.environ.get("REPLICATE_API_KEY", "")
        self.model = model or self.DEFAULT_MODEL
        self.output_dir = "output/images"
        os.makedirs(self.output_dir, exist_ok=True)

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def generate(
        self,
        prompt: str,
        reference_image_path: str,
        filename: str = "image.png",
        timeout: int = 120,
    ) -> Optional[str]:
        """Generate image conditioned on reference. Returns file path or None."""
        if not self.is_configured():
            logger.warning("Replicate not configured: missing api_key")
            return None

        if not os.path.exists(reference_image_path):
            logger.warning("Reference image not found: %s", reference_image_path)
            return None

        try:
            # Read reference image as base64
            with open(reference_image_path, "rb") as f:
                ref_b64 = base64.b64encode(f.read()).decode("utf-8")
            ext = os.path.splitext(reference_image_path)[1].lower()
            mime = {
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".png": "image/png",
                ".webp": "image/webp",
            }.get(ext, "image/png")
            data_uri = f"data:{mime};base64,{ref_b64}"

            # Create prediction
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "version": self.model,
                "input": {
                    "prompt": prompt,
                    "image": data_uri,
                    "num_outputs": 1,
                    "guidance_scale": 7.5,
                },
            }
            resp = requests.post(self.API_URL, headers=headers, json=payload, timeout=30)
            resp.raise_for_status()
            prediction = resp.json()

            # Poll for completion
            poll_url = prediction.get("urls", {}).get("get", "")
            if not poll_url:
                logger.error("No poll URL in Replicate response")
                return None

            start = time.time()
            while time.time() - start < timeout:
                time.sleep(3)
                poll_resp = requests.get(poll_url, headers=headers, timeout=15)
                poll_resp.raise_for_status()
                status_data = poll_resp.json()
                status = status_data.get("status", "")

                if status == "succeeded":
                    output = status_data.get("output")
                    if isinstance(output, list) and output:
                        image_url = output[0]
                    elif isinstance(output, str):
                        image_url = output
                    else:
                        logger.error("Unexpected Replicate output format")
                        return None

                    # Download the generated image
                    img_resp = requests.get(image_url, timeout=30)
                    img_resp.raise_for_status()
                    filepath = os.path.join(self.output_dir, filename)
                    with open(filepath, "wb") as f:
                        f.write(img_resp.content)
                    logger.info("Generated IP-Adapter image: %s", filepath)
                    return filepath

                if status == "failed":
                    error = status_data.get("error", "unknown")
                    logger.error("Replicate prediction failed: %s", error)
                    return None

            logger.error("Replicate prediction timed out after %ds", timeout)
            return None

        except Exception as e:
            logger.error("Replicate IP-Adapter error: %s", e)
            return None

    def batch_generate(
        self, requests_list: list[dict], max_workers: int = 5
    ) -> list[ImageResult]:
        """Generate multiple images in parallel. Returns partial results on failure.

        Each dict in requests_list must include the kwargs accepted by generate():
        prompt, reference_image_path, and optionally filename, timeout.
        """
        if not requests_list:
            return []

        results: list[ImageResult] = []
        with ThreadPoolExecutor(max_workers=min(max_workers, len(requests_list))) as executor:
            futures = {
                executor.submit(self.generate, **req): req
                for req in requests_list
            }
            for future in as_completed(futures):
                req = futures[future]
                prompt = req.get("prompt", "")
                try:
                    url = future.result()
                    results.append(ImageResult(prompt=prompt, image_url=url))
                except Exception as e:
                    logger.error("Batch image generation failed for %r: %s", prompt, e)
                    results.append(ImageResult(prompt=prompt, error=str(e), success=False))
        return results
