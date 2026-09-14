"""Image generation through a local OpenAI-compatible Qwen proxy.

The proxy (a separate process — see its own ``server/README.md``) drives the
chat.qwen.ai web app and exposes two endpoints this client uses:

  * ``POST {base_url}/images/qwen``        — text-to-image
  * ``POST {base_url}/images/qwen/edits``  — edit an existing image

Why a dedicated client instead of the generic ``sd-api``/``dalle`` paths: the
proxy takes an **aspect ratio** rather than a pixel size, and its edit endpoint
gives the comic pipeline real reference conditioning (the source panel is sent
along and modified) instead of the text-only fallback other providers get.

Images are requested as ``b64_json`` so the bytes arrive inline — the proxy's
``url`` form points back at *its* static mount, which is an extra hop and is
unreachable when the proxy runs on another host.
"""

from __future__ import annotations

import base64
import logging
import os
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)

#: What ``config.pipeline.qwen_local_base_url`` defaults to; the client itself
#: does NOT fall back to it (see ``__init__``).
DEFAULT_BASE_URL = "http://localhost:8000/v1"
DEFAULT_TIMEOUT = 300.0
# Aspect ratios the proxy accepts; a pixel size is snapped to the nearest one
# upstream, so anything WxH is also valid here.
ALLOWED_RATIOS = ("1:1", "4:3", "3:4", "16:9", "9:16", "3:2", "2:3")
# Refuse to inline a reference image bigger than the proxy will accept anyway.
MAX_REFERENCE_BYTES = 10 * 1024 * 1024


class QwenLocalClient:
    """Talk to the local Qwen proxy's image endpoints."""

    def __init__(
        self,
        base_url: str = "",
        api_key: str = "",
        model: str = "",
        size: str = "",
        timeout: float = DEFAULT_TIMEOUT,
    ):
        # Empty means "not configured", not "use the default": the config layer
        # already ships DEFAULT_BASE_URL, so a blank field is the user turning
        # the provider off, and is_configured() has to be able to say so.
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key or ""
        self.model = model or ""
        self.size = size or ""
        self.timeout = timeout or DEFAULT_TIMEOUT

    # ── Configuration / discovery ─────────────────────────────────────────────

    def is_configured(self) -> bool:
        """True when a base URL is set. Reachability is a separate probe."""
        return bool(self.base_url)

    @property
    def health_url(self) -> str:
        """The proxy's ``/health``, which lives one level above ``/v1``."""
        root = self.base_url
        if root.endswith("/v1"):
            root = root[: -len("/v1")]
        return f"{root}/health"

    def status(self) -> dict[str, Any]:
        """Probe the proxy: is it up, and did its Qwen provider start?

        Never raises — the caller is a status badge, not a pipeline step.
        """
        result: dict[str, Any] = {
            "configured": self.is_configured(),
            "reachable": False,
            "qwen_ready": False,
            "base_url": self.base_url,
            "error": "",
        }
        if not self.is_configured():
            result["error"] = "No base URL configured"
            return result
        try:
            response = requests.get(self.health_url, timeout=10)
            result["reachable"] = response.status_code == 200
            if response.status_code != 200:
                result["error"] = f"HTTP {response.status_code}"
                return result
            payload = response.json()
            providers = payload.get("providers") or {}
            result["qwen_ready"] = bool(providers.get("qwen"))
            if not result["qwen_ready"]:
                result["error"] = "Proxy is up but its Qwen provider did not start"
        except requests.RequestException as e:
            result["error"] = str(e)[:200]
        except ValueError as e:  # not JSON
            result["error"] = f"Unexpected health response: {e}"[:200]
        return result

    # ── Generation ────────────────────────────────────────────────────────────

    def text_to_image(
        self, prompt: str, filepath: str, size: str = ""
    ) -> Optional[str]:
        """Generate an image from a prompt; save to ``filepath``."""
        body: dict[str, Any] = {
            "prompt": prompt,
            "n": 1,
            "response_format": "b64_json",
        }
        if self.model:
            body["model"] = self.model
        resolved_size = size or self.size
        if resolved_size:
            body["size"] = resolved_size
        return self._post_and_save("/images/qwen", body, filepath)

    def image_with_refs(
        self,
        prompt: str,
        reference_paths: list,
        filepath: str,
        size: str = "",
    ) -> Optional[str]:
        """Edit the first reference image according to ``prompt``.

        Qwen's edit mode takes exactly one source image, so extra references
        are ignored rather than silently blended.
        """
        source = next((p for p in reference_paths if p and os.path.isfile(p)), None)
        if source is None:
            logger.warning(
                "No readable reference image among %d path(s); "
                "falling back to text-only generation.",
                len(reference_paths),
            )
            return self.text_to_image(prompt, filepath, size)
        if len(reference_paths) > 1:
            logger.info(
                "Qwen edit takes one source image; using %s and ignoring %d other(s).",
                os.path.basename(source),
                len(reference_paths) - 1,
            )

        raw = open(source, "rb").read()
        if len(raw) > MAX_REFERENCE_BYTES:
            logger.warning(
                "Reference %s is %.1f MB (limit %d MB); generating without it.",
                os.path.basename(source),
                len(raw) / (1024 * 1024),
                MAX_REFERENCE_BYTES // (1024 * 1024),
            )
            return self.text_to_image(prompt, filepath, size)

        body: dict[str, Any] = {
            "prompt": prompt,
            "image": base64.b64encode(raw).decode("ascii"),
            "filename": os.path.basename(source),
            "n": 1,
            "response_format": "b64_json",
        }
        if self.model:
            body["model"] = self.model
        resolved_size = size or self.size
        if resolved_size:
            body["size"] = resolved_size
        return self._post_and_save("/images/qwen/edits", body, filepath)

    # ── HTTP plumbing ─────────────────────────────────────────────────────────

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _post_and_save(
        self, path: str, body: dict[str, Any], filepath: str
    ) -> Optional[str]:
        """POST one image request and write the returned bytes to disk."""
        if not self.is_configured():
            logger.error("Qwen local provider skipped: no base URL configured.")
            return None

        url = f"{self.base_url}{path}"
        try:
            response = requests.post(
                url, json=body, headers=self._headers(), timeout=self.timeout
            )
        except requests.RequestException as e:
            logger.error("Qwen local proxy unreachable at %s: %s", url, e)
            return None

        if response.status_code != 200:
            # The proxy answers with FastAPI's {"detail": ...} on every error.
            detail = ""
            try:
                detail = str(response.json().get("detail", ""))[:300]
            except ValueError:
                detail = response.text[:300]
            logger.error(
                "Qwen local proxy returned HTTP %s for %s: %s",
                response.status_code,
                path,
                detail,
            )
            return None

        try:
            payload = response.json()
            entries = payload.get("data") or []
            encoded = entries[0].get("b64_json") if entries else None
        except (ValueError, AttributeError, IndexError, TypeError) as e:
            logger.error("Unexpected response from %s: %s", url, e)
            return None

        if not encoded:
            logger.error("Qwen local proxy returned no image data for %s", path)
            return None

        try:
            data = base64.b64decode(encoded)
        except (ValueError, TypeError) as e:
            logger.error("Qwen local proxy returned undecodable image data: %s", e)
            return None

        os.makedirs(os.path.dirname(os.path.abspath(filepath)) or ".", exist_ok=True)
        with open(filepath, "wb") as handle:
            handle.write(data)
        logger.info("Qwen local image saved: %s (%d bytes)", filepath, len(data))
        return filepath
