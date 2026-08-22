"""AI image generation from story prompts — supports DALL-E and SD-compatible APIs."""

import asyncio
import os
import logging
import base64
import contextlib
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

import requests

from config import ConfigManager

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Process-wide ceiling on image requests in flight
#
# Image work fans out at two independent levels: across chapters (the pipeline
# media stage, and now the Reader path) and across the panels within a chapter.
# Neither worker count bounds the other, so they multiply — 4 chapters x 3
# panels is 12 concurrent provider calls, not 4 — and no single setting says
# how many requests the provider is actually being asked to serve.
#
# One semaphore, held only around the provider call itself, is that number.
# Workers above it may queue; the provider sees at most this many at once.
# ─────────────────────────────────────────────────────────────────────────────

_REQUEST_SEMAPHORE: Optional[threading.BoundedSemaphore] = None
_REQUEST_SEMAPHORE_SIZE: int = -1
_REQUEST_SEMAPHORE_LOCK = threading.Lock()


def _request_slot():
    """Context manager for one provider call's slot; a no-op when disabled."""
    global _REQUEST_SEMAPHORE, _REQUEST_SEMAPHORE_SIZE
    try:
        size = int(ConfigManager().pipeline.image_max_concurrent_requests)
    except Exception:
        size = 0
    if size <= 0:
        return contextlib.nullcontext()
    with _REQUEST_SEMAPHORE_LOCK:
        # Rebuild on a size change so the setting is live, not boot-time only.
        if _REQUEST_SEMAPHORE is None or _REQUEST_SEMAPHORE_SIZE != size:
            _REQUEST_SEMAPHORE = threading.BoundedSemaphore(size)
            _REQUEST_SEMAPHORE_SIZE = size
        return _REQUEST_SEMAPHORE


def reset_image_request_semaphore() -> None:
    """Drop the shared semaphore. For tests, and for a config reload."""
    global _REQUEST_SEMAPHORE, _REQUEST_SEMAPHORE_SIZE
    with _REQUEST_SEMAPHORE_LOCK:
        _REQUEST_SEMAPHORE = None
        _REQUEST_SEMAPHORE_SIZE = -1


class ImageGenerator:
    """Generate images from prompts using various AI providers."""

    PROVIDERS = [
        "dalle",
        "sd-api",
        "seedream",
        "replicate",
        "huggingface",
        "flowkit",
        "codex",
        "qwen-local",
        "none",
    ]

    def __init__(
        self,
        provider: str = "none",
        api_key: str = "",
        base_url: str = "",
        session_id: Optional[str] = None,
        story_title: Optional[str] = None,
    ):
        config = ConfigManager()
        cfg = config.pipeline
        self.provider = provider or cfg.image_provider
        # DALL-E should work when the user has already configured an OpenAI LLM
        # key; a separate image_api_key remains an optional override.
        self.api_key = (
            api_key
            or cfg.image_api_key
            or os.environ.get("IMAGE_API_KEY", "")
            or (
                config.llm.api_key
                if "openai.com" in (config.llm.base_url or "")
                else ""
            )
        )
        self.base_url = (
            base_url
            or cfg.image_api_url
            or os.environ.get("IMAGE_API_URL", "")
            or (
                config.llm.base_url
                if "openai.com" in (config.llm.base_url or "")
                else "https://api.openai.com/v1"
            )
        )
        self.hf_token = cfg.hf_token or os.environ.get("HF_TOKEN", "")
        self.hf_model = cfg.hf_image_model
        self.session_id = session_id
        self.story_title = story_title
        # Scene panels live under the per-story output layout:
        #   output/<story-slug>/images
        # The resolver derives the slug from title (+session when present) —
        # the same slug everything else for this story uses. Library jobs pass
        # story_title with session_id=None (localStorage stories have no
        # session); they MUST still get a per-story folder, or every story's
        # ``chNN_panelNN.png`` collides in one shared dir. Falls back to a
        # global images dir only when no title is known (CLI / standalone use).
        from services.output_paths import OUTPUT_ROOT, images_dir

        if story_title:
            self.output_dir = images_dir(story_title, session_id=session_id)
        else:
            self.output_dir = os.path.join(OUTPUT_ROOT, "images")
        os.makedirs(self.output_dir, exist_ok=True)

    # ── Public API ────────────────────────────────────────────────────────────

    def generate(
        self, prompt: str, filename: str = "image.png", size: str = "1024x1024"
    ) -> Optional[str]:
        """Generate image from prompt. Returns saved file path or None."""
        if self.provider == "none":
            logger.info(
                "Image gen disabled (prompt-only mode). Prompt: %.100s...", prompt
            )
            return None

        if self.provider == "dalle":
            return self._generate_dalle(prompt, filename, size)
        if self.provider == "sd-api":
            return self._generate_sd(prompt, filename)
        if self.provider == "seedream":
            return self._generate_seedream(prompt, filename)
        if self.provider == "huggingface":
            return self._generate_huggingface(prompt, filename)
        if self.provider == "flowkit":
            return self._generate_flowkit(prompt, filename, size)
        if self.provider == "codex":
            return self._generate_codex(prompt, filename, size)
        if self.provider == "qwen-local":
            return self._generate_qwen_local(prompt, filename, size)

        logger.warning("Unknown image provider: %s", self.provider)
        return None

    def generate_with_reference(
        self,
        prompt: str,
        reference_paths: list,
        filename: str = "image.png",
        size: str = "1024x1024",
    ) -> Optional[str]:
        """Generate image conditioned on character reference images.

        For providers with native reference support (seedream, replicate),
        uses the reference image directly. For others, falls back to text-only.
        """
        if not reference_paths:
            return self.generate(prompt, filename, size)

        if self.provider == "flowkit":
            return self._flowkit_with_ref(prompt, reference_paths, filename)
        if self.provider == "codex":
            return self._codex_with_ref(prompt, reference_paths, filename, size)
        if self.provider == "qwen-local":
            return self._qwen_local_with_ref(prompt, reference_paths, filename, size)
        if self.provider == "seedream":
            return self._seedream_with_ref(prompt, reference_paths, filename)
        if self.provider == "replicate":
            return self._replicate_with_ref(prompt, reference_paths[0], filename)

        # DALL-E/SD/HF: no native reference support, drop refs and go text-only
        logger.info(
            "Provider %s does not support reference images; dropping %d ref(s)",
            self.provider,
            len(reference_paths),
        )
        return self.generate(prompt, filename, size)

    def generate_story_images(
        self,
        image_prompts: list,
        chapter_number: int = 0,
        character_references: dict | None = None,
        keep_positions: bool = False,
    ) -> list:
        """Generate images for a list of ImagePrompt objects. Returns saved paths.

        ``character_references`` maps character name → reference image path. When
        a prompt's ``characters_in_scene`` contains names with refs, we route via
        ``generate_with_reference`` so img2img-capable providers (seedream,
        replicate) condition on the uploaded reference. Providers without native
        reference support fall through to text-only generation transparently.

        ``keep_positions`` makes a failed panel yield ``None`` instead of being
        dropped, so index N of the result is still panel N. The page compositor
        needs that: it slices this list positionally per page, so a dropped panel
        used to shift every later one into the wrong cell. Callers that just want
        a list of URLs leave it False and keep the old contract.
        """
        refs = character_references or {}
        _pipeline_cfg = ConfigManager().pipeline
        # A panel sometimes comes back empty (Codex occasionally drops one, a
        # transient provider hiccup, etc.). Retry it a few times rather than
        # silently shipping a chapter with a hole in it.
        _retries = max(0, int(_pipeline_cfg.panel_retry_attempts))
        prompts = list(image_prompts)
        if not prompts:
            return []

        # Panels are independent provider calls, so they run concurrently rather
        # than in a queue. Results are written by index and only then flattened:
        # completion order is not panel order, and the compositor slices this
        # list positionally.
        slots: list = [None] * len(prompts)
        workers = max(1, min(len(prompts), int(_pipeline_cfg.comic_panel_workers)))
        if workers == 1:
            for i, ip in enumerate(prompts):
                slots[i] = self._generate_one_panel(i, ip, chapter_number, refs, _retries)
        else:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {
                    executor.submit(
                        self._generate_one_panel, i, ip, chapter_number, refs, _retries
                    ): i
                    for i, ip in enumerate(prompts)
                }
                for future in as_completed(futures):
                    i = futures[future]
                    try:
                        slots[i] = future.result()
                    except Exception as e:
                        # One panel blowing up must not cost the chapter its
                        # other nineteen.
                        logger.error(
                            "Panel %d (ch%02d) raised: %s (type=%s)",
                            i + 1,
                            chapter_number,
                            e,
                            type(e).__name__,
                        )

        for i, path in enumerate(slots):
            if path:
                continue
            logger.error(
                "Panel %d (ch%02d) failed after %d attempt(s); %s",
                i + 1,
                chapter_number,
                _retries + 1,
                "placeholder kept" if keep_positions else "skipped",
            )
        if keep_positions:
            # Hold the slot. The page compositor slices this list positionally,
            # so dropping a failed panel shifted every later panel into the wrong
            # cell — speech balloons landing on the wrong art for the rest of the
            # chapter, silently.
            return slots
        return [p for p in slots if p]

    def _generate_one_panel(self, i, ip, chapter_number: int, refs: dict, retries: int):
        """Generate a single panel with its retries. Returns a path or None."""
        prompt = ip.dalle_prompt if self.provider == "dalle" else ip.sd_prompt
        if not prompt:
            prompt = ip.scene_description
        filename = f"ch{chapter_number:02d}_panel{i + 1:02d}.png"
        # Generate at the aspect of the compositor cell this panel lands in.
        # Everything used to be square, so a panel dropped into a 2.1:1 tier
        # cell lost more than half its height to the center crop.
        size = getattr(ip, "target_size", "") or "1024x1024"

        scene_refs: list[str] = []
        for name in getattr(ip, "characters_in_scene", []) or []:
            ref = refs.get(name)
            if ref and os.path.exists(ref) and ref not in scene_refs:
                scene_refs.append(ref)

        if not scene_refs:
            # Comic consistency fallback: when no character in this panel
            # name-matches a stored reference, still attach the chapter's
            # main-character reference (first existing ref in the map) so the
            # protagonist's face doesn't drift across panels. Only kicks in
            # when at least one usable reference image actually exists on disk
            # — with no refs at all we keep the text-only path.
            for ref in refs.values():
                if ref and os.path.exists(ref):
                    scene_refs.append(ref)
                    break

        path = None
        for attempt in range(retries + 1):
            # The slot is held around the provider call only — never across the
            # retry backoff — so a retrying panel does not sit on capacity its
            # siblings could use.
            with _request_slot():
                if scene_refs:
                    path = self.generate_with_reference(
                        prompt, scene_refs, filename, size
                    )
                else:
                    path = self.generate(prompt, filename, size)
            if path:
                break
            if attempt < retries:
                logger.warning(
                    "Panel %d (ch%02d) returned no image; retry %d/%d",
                    i + 1,
                    chapter_number,
                    attempt + 1,
                    retries,
                )
        return path

    # ── Private providers ─────────────────────────────────────────────────────

    # Sizes each hosted backend will actually accept. A cell-matched size like
    # "1024x480" is legal for local backends but a 400 from DALL-E, so it is
    # snapped to the closest aspect the provider does support instead of being
    # dropped (dropping it would put us back to square panels in tier cells).
    _DALLE_SIZES = ("1024x1024", "1792x1024", "1024x1792")
    _CODEX_SIZES = ("1024x1024", "1536x1024", "1024x1536")

    @staticmethod
    def _snap_size(size: str, allowed: tuple) -> str:
        """Closest allowed WxH by aspect ratio; falls back to the first entry."""
        try:
            w, h = (int(v) for v in str(size).lower().split("x"))
            if w <= 0 or h <= 0:
                raise ValueError(size)
        except (ValueError, TypeError):
            return allowed[0]
        target = w / h

        def _ar(spec: str) -> float:
            aw, ah = (int(v) for v in spec.split("x"))
            return aw / ah

        return min(allowed, key=lambda spec: abs(_ar(spec) - target))

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
                "size": self._snap_size(size, self._DALLE_SIZES),
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

    def _generate_huggingface(self, prompt: str, filename: str) -> Optional[str]:
        """Generate via HuggingFace Inference API (free tier, FLUX.1 Schnell default)."""
        if not self.hf_token:
            logger.error("HuggingFace generation skipped: no HF_TOKEN configured.")
            return None
        try:
            headers = {"Authorization": f"Bearer {self.hf_token}"}
            payload = {"inputs": prompt}
            api_url = f"https://api-inference.huggingface.co/models/{self.hf_model}"

            max_retries = 2
            for attempt in range(max_retries + 1):
                resp = requests.post(
                    api_url, headers=headers, json=payload, timeout=120
                )
                if resp.status_code == 503 and attempt < max_retries:
                    delay = 5 * (3**attempt)  # 5s, 15s
                    logger.warning(
                        "HuggingFace model loading, retry %d/%d in %ds...",
                        attempt + 1,
                        max_retries,
                        delay,
                    )
                    time.sleep(delay)
                    continue
                break

            resp.raise_for_status()

            filepath = os.path.join(self.output_dir, filename)
            with open(filepath, "wb") as f:
                f.write(resp.content)

            logger.info("Generated HuggingFace image: %s (%s)", filepath, self.hf_model)
            return filepath
        except Exception as e:
            logger.error("HuggingFace generation failed: %s", e)
            return None

    def _generate_seedream(self, prompt: str, filename: str) -> Optional[str]:
        """Generate via ByteDance Seedream API (delegates to SeedreamClient)."""
        from services.seedream_client import (
            SeedreamClient,
        )  # local import avoids circular deps

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

    def _seedream_with_ref(
        self, prompt: str, reference_paths: list, filename: str
    ) -> Optional[str]:
        """Generate via Seedream with character references."""
        from services.seedream_client import (
            SeedreamClient,
        )  # local import avoids circular deps

        cfg = ConfigManager().pipeline
        client = SeedreamClient(
            api_key=cfg.seedream_api_key, base_url=cfg.seedream_api_url
        )
        if not client.is_configured():
            logger.warning("Seedream not configured for reference generation")
            return self.generate(prompt, filename)
        filepath = os.path.join(self.output_dir, filename)
        return client.generate_scene(prompt, reference_paths, filepath)

    def _replicate_with_ref(
        self, prompt: str, reference_path: str, filename: str
    ) -> Optional[str]:
        """Generate via Replicate IP-Adapter with character reference."""
        from services.replicate_ip_adapter import ReplicateIPAdapter  # local import

        client = ReplicateIPAdapter()
        if not client.is_configured():
            logger.warning("Replicate not configured for reference generation")
            return self.generate(prompt, filename)
        return client.generate(prompt, reference_path, filename)

    # ── Codex (ChatGPT Plus image-gen via the user's own Codex login) ─────────

    def _codex_client(self):
        from services.media.codex_image_client import CodexImageClient

        cfg = ConfigManager().pipeline
        return CodexImageClient(model=getattr(cfg, "codex_model", "") or "")

    def _generate_codex(self, prompt: str, filename: str, size: str) -> Optional[str]:
        """Text-only image generation via ChatGPT (Codex/gpt-image-2-codex)."""
        client = self._codex_client()
        if not client.is_configured():
            logger.error("Codex generation skipped: no ~/.codex login found.")
            return None
        filepath = os.path.join(self.output_dir, filename)
        return client.text_to_image(prompt, filepath, self._snap_size(size, self._CODEX_SIZES))

    def _codex_with_ref(
        self, prompt: str, reference_paths: list, filename: str, size: str
    ) -> Optional[str]:
        """Reference-conditioned generation (character consistency) via Codex."""
        client = self._codex_client()
        if not client.is_configured():
            logger.warning("Codex not configured for reference generation")
            return self.generate(prompt, filename, size)
        filepath = os.path.join(self.output_dir, filename)
        return client.image_with_refs(
            prompt, reference_paths, filepath, self._snap_size(size, self._CODEX_SIZES)
        )

    # ── Qwen local proxy (OpenAI-compatible server driving chat.qwen.ai) ──────

    def _qwen_local_client(self):
        from services.media.qwen_local_client import QwenLocalClient

        cfg = ConfigManager().pipeline
        return QwenLocalClient(
            base_url=getattr(cfg, "qwen_local_base_url", ""),
            api_key=getattr(cfg, "qwen_local_api_key", ""),
            model=getattr(cfg, "qwen_local_model", ""),
            size=getattr(cfg, "qwen_local_size", ""),
            timeout=getattr(cfg, "qwen_local_timeout", 300.0),
        )

    def _generate_qwen_local(
        self, prompt: str, filename: str, size: str
    ) -> Optional[str]:
        """Text-to-image via the local Qwen proxy."""
        client = self._qwen_local_client()
        if not client.is_configured():
            logger.error("Qwen local generation skipped: no base URL configured.")
            return None
        filepath = os.path.join(self.output_dir, filename)
        return client.text_to_image(prompt, filepath, size)

    def _qwen_local_with_ref(
        self, prompt: str, reference_paths: list, filename: str, size: str
    ) -> Optional[str]:
        """Reference-conditioned generation via the proxy's edit endpoint.

        Qwen's edit mode rewrites the reference image itself, which keeps a
        character's likeness far better than re-describing them in text. Users
        who would rather have a fresh composition can turn it off with
        ``qwen_local_use_edit_for_refs``.
        """
        client = self._qwen_local_client()
        if not client.is_configured():
            logger.warning("Qwen local not configured for reference generation")
            return None
        filepath = os.path.join(self.output_dir, filename)
        cfg = ConfigManager().pipeline
        if not getattr(cfg, "qwen_local_use_edit_for_refs", True):
            return client.text_to_image(prompt, filepath, size)
        return client.image_with_refs(prompt, reference_paths, filepath, size)

    # ── FlowKit (Google Labs proxy via Chrome extension WS) ───────────────────

    def _flowkit_refine(self, prompt: str) -> str:
        """Run cinematic refiner if flag enabled; on failure, fall back to raw prompt."""
        cfg = ConfigManager().pipeline
        if not cfg.flowkit_use_refiner:
            return prompt
        try:
            from services.media.image_prompt_generator import ImagePromptGenerator

            return ImagePromptGenerator().refine_to_cinematic_prompt(prompt) or prompt
        except Exception as e:
            logger.warning("FlowKit refiner failed, using raw prompt: %s", e)
            return prompt

    def _flowkit_call(self, coro_factory) -> Optional[str]:
        """Bridge a sync executor worker to FlowService's asyncio loop.

        Precondition: caller is on a worker thread (not the FlowService loop);
        FlowService captured ``_main_loop`` when the WS connected.
        """
        from services.media.flow_service import FlowService

        flow_service = FlowService()
        cfg = ConfigManager().pipeline
        if not cfg.flowkit_enabled or flow_service.active_ws is None:
            logger.warning(
                "FlowKit not ready (enabled=%s, ws_connected=%s)",
                cfg.flowkit_enabled,
                flow_service.active_ws is not None,
            )
            return None
        loop = getattr(flow_service, "_main_loop", None)
        if loop is None:
            logger.error("FlowKit unavailable: FlowService has no captured main loop")
            return None
        try:
            fut = asyncio.run_coroutine_threadsafe(coro_factory(), loop)
            timeout = max(30.0, float(cfg.flowkit_request_timeout))
            return fut.result(timeout=timeout)
        except Exception as e:
            logger.exception("FlowKit generation failed: %s (%s)", type(e).__name__, e)
            return None

    def _generate_flowkit(
        self, prompt: str, filename: str, size: str = "1024x1024"
    ) -> Optional[str]:
        """Text-only image generation via Google Labs Flow (Imagen)."""
        from services.media.flow_service import FlowService

        flow_service = FlowService()
        if flow_service.active_ws is None:
            logger.warning(
                "FlowKit not connected (no active WebSocket); skipping generation"
            )
            return None
        refined = self._flowkit_refine(prompt)
        return self._flowkit_call(
            lambda: flow_service.request_image(
                refined, [], None, self.output_dir, filename
            )
        )

    def _flowkit_with_ref(
        self, prompt: str, reference_paths: list, filename: str
    ) -> Optional[str]:
        """Reference-conditioned generation. Splits CHARACTER/STYLE refs when split flag set."""
        from services.media.flow_service import FlowService

        flow_service = FlowService()
        if flow_service.active_ws is None:
            logger.warning(
                "FlowKit not connected (no active WebSocket); skipping generation"
            )
            return None
        cfg = ConfigManager().pipeline
        refined = self._flowkit_refine(prompt)
        char_refs = list(reference_paths or [])
        style_ref: Optional[str] = None
        if cfg.flowkit_image_input_type_split:
            style_path = cfg.flowkit_style_reference_path
            if style_path and os.path.isfile(style_path):
                style_ref = style_path
        return self._flowkit_call(
            lambda: flow_service.request_image(
                refined, char_refs, style_ref, self.output_dir, filename
            )
        )
