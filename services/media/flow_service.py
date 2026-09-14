"""FlowService — singleton WS-backed proxy to Google Labs Flow (Imagen 3 + Veo).

Owns:
- the single extension WebSocket (set via `set_active_ws` / `clear_active_ws`)
- per-request futures keyed by uuid (`pending_requests`)
- adaptive concurrency ramp (1 → flowkit_concurrent_workers_max)
- SQLite jobs queue for Veo async polling
- httpx downloader for GCS signed URLs (1h expiry)

Pure asyncio (CLAUDE.md §10). No real network in tests (CLAUDE.md §9).
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
import secrets
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
from uuid import uuid4

try:  # optional
    import httpx
except ImportError:  # pragma: no cover
    httpx = None  # type: ignore

from config import ConfigManager

logger = logging.getLogger(__name__)


# Outbound download host allowlist — keeps the WS-driven downloader from being
# weaponised to hit arbitrary URLs if the upstream extension is hijacked.
_DOWNLOAD_HOSTS = {
    "storage.googleapis.com",
    "labs.google",
    "fife.usercontent.google.com",
    "lh3.googleusercontent.com",
    "flow-content.google",
}

_ASPECT_ENUM_MAP = {
    "1:1": "IMAGE_ASPECT_RATIO_SQUARE",
    "9:16": "IMAGE_ASPECT_RATIO_PORTRAIT",
    "16:9": "IMAGE_ASPECT_RATIO_LANDSCAPE",
    "3:4": "IMAGE_ASPECT_RATIO_PORTRAIT_THREE_FOUR",
    # Comic webtoon panel. Flow/Imagen has no native 4:5 enum, so we map to the
    # nearest accepted portrait ratio (3:4 ≈ 0.75 vs 4:5 = 0.8) to avoid an
    # "unknown enum" rejection while still producing a panel-shaped (not 9:16
    # full-page wallpaper) frame.
    "4:5": "IMAGE_ASPECT_RATIO_PORTRAIT_THREE_FOUR",
    "4:3": "IMAGE_ASPECT_RATIO_LANDSCAPE_FOUR_THREE",
}

# Appended to every flowkit positive prompt: the flowMedia:batchGenerateImages
# schema has no negative-prompt field, so the only way to suppress model-invented
# text/captions/bubbles is to bake the prohibition into the positive prompt.
_NO_TEXT_SUFFIX = (
    "no text, no letters, no watermark, no caption, "
    "no speech bubble, no signpost, no logo"
)


def _aspect_to_enum(aspect: str) -> str:
    return _ASPECT_ENUM_MAP.get((aspect or "").strip(), "IMAGE_ASPECT_RATIO_PORTRAIT")


@dataclass
class _RampState:
    current: int = 1
    streak: int = 0
    max_workers: int = 4
    threshold: int = 10


class FlowService:
    """Singleton orchestrator. Use module-level `flow_service`."""

    _instance: Optional["FlowService"] = None

    def __new__(cls) -> "FlowService":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:  # type: ignore[attr-defined]
            return
        self._initialized = True

        self.pending_requests: Dict[str, asyncio.Future] = {}
        self.active_ws = None  # set by api/flowkit.py router
        self.flow_key: Optional[str] = None
        self.callback_secret: str = secrets.token_hex(16)
        # Last GCS signed URL volunteered by the extension (background.js
        # "media_url_refreshed"). Captured for observability; signed URLs expire
        # ~1h so this is a best-effort hint, not a guaranteed-fresh download source.
        self.last_media_url: Optional[str] = None
        self.last_media_refresh_at: float = 0.0

        cfg = ConfigManager().pipeline
        self._ramp = _RampState(
            current=max(1, int(cfg.flowkit_concurrent_workers)),
            max_workers=max(1, int(cfg.flowkit_concurrent_workers_max)),
            threshold=max(1, int(cfg.flowkit_workers_ramp_threshold)),
        )
        # Concurrency gate: long-lived Condition + active-count tracks current capacity.
        # We mutate `_ramp.current` (the soft cap) instead of swapping the semaphore,
        # so in-flight callers can never exceed the cap during a ramp transition.
        self._gate = asyncio.Condition()
        self._active = 0
        self._account_warning_logged = False

    # ------------------------------------------------------------------ config

    @property
    def _cfg(self):
        return ConfigManager().pipeline

    # ----------------------------------------------------------------- ws hook

    def set_active_ws(self, ws) -> None:
        self.active_ws = ws
        # Capture the loop the WS lives on so sync callers (executor workers)
        # can hand coroutines back via run_coroutine_threadsafe.
        try:
            self._main_loop = asyncio.get_running_loop()
        except RuntimeError:
            self._main_loop = None
        self.log_account_warning()

    def clear_active_ws(self) -> None:
        self.active_ws = None
        # Atomic swap-and-drain so a concurrent resolve_request can't double-set
        # a future that we're about to fail.
        pending = self.pending_requests
        self.pending_requests = {}
        for fut in pending.values():
            if not fut.done():
                fut.set_exception(ConnectionError("FlowKit WS disconnected"))

    def log_account_warning(self) -> None:
        if self._account_warning_logged:
            return
        self._account_warning_logged = True
        if not self._cfg.flowkit_account_warning_shown:
            logger.warning(
                "FlowKit account-ban risk — automated traffic on personal Google "
                "accounts may trigger rate limits or suspension. Use a secondary account."
            )

    # The jobs SQLite layer (init_db, _db_execute, _db_query and the flow_jobs
    # schema) went with video generation — flow_jobs only ever held Veo jobs.
    # Image generation is synchronous over the extension WS and never touched it.

    # --------------------------------------------------------------- ramp logic

    def _record_success(self) -> None:
        self._ramp.streak += 1
        if (
            self._ramp.streak >= self._ramp.threshold
            and self._ramp.current < self._ramp.max_workers
        ):
            self._ramp.current += 1
            self._ramp.streak = 0
            logger.info("FlowKit ramp up workers=%d", self._ramp.current)

    def _record_failure(self) -> None:
        if self._ramp.current != 1 or self._ramp.streak != 0:
            logger.info(
                "FlowKit ramp reset (was workers=%d streak=%d)",
                self._ramp.current,
                self._ramp.streak,
            )
        self._ramp.streak = 0
        self._ramp.current = 1
        # Wake any waiters so the (now lower) cap is re-checked. Existing in-flight
        # callers above the new cap finish normally — the cap only gates entry.

    async def _acquire_slot(self) -> None:
        async with self._gate:
            while self._active >= self._ramp.current:
                await self._gate.wait()
            self._active += 1

    async def _release_slot(self) -> None:
        async with self._gate:
            self._active = max(0, self._active - 1)
            self._gate.notify_all()

    # ------------------------------------------------------------ ws dispatch

    async def _send(
        self,
        method: str,
        params: dict,
        timeout: float = 60.0,
        ws_method: str = "api_request",
    ) -> dict:
        if self.active_ws is None:
            raise ConnectionError("FlowKit extension not connected")

        await self._acquire_slot()
        try:
            req_id = str(uuid4())
            loop = asyncio.get_running_loop()
            fut: asyncio.Future = loop.create_future()
            self.pending_requests[req_id] = fut
            # ws_method = the dispatch verb the extension routes on (background.js:109-110).
            # "api_request" → handleApiRequest (URL fetch). "solve_captcha" → handleSolveCaptcha.
            # `method` is just a human-readable label for the logical operation we're invoking
            # (e.g. "batchGenerateImages") and only appears in logs.
            payload = {"id": req_id, "method": ws_method, "params": params}
            logger.info(
                "FlowKit WS OUT id=%s ws_method=%s op=%s param_keys=%s",
                req_id,
                ws_method,
                method,
                list(params.keys()),
            )
            try:
                await self.active_ws.send_json(payload)
            except Exception:
                self.pending_requests.pop(req_id, None)
                self._record_failure()
                raise
            try:
                result = await asyncio.wait_for(fut, timeout=timeout)
            except asyncio.TimeoutError:
                # Distinct branch so the operator can tell timeouts apart from
                # protocol/transport errors when triaging silent avatar misses.
                self.pending_requests.pop(req_id, None)
                self._record_failure()
                logger.warning(
                    "FlowKit WS TIMEOUT id=%s op=%s after %.1fs",
                    req_id,
                    method,
                    timeout,
                )
                raise
            except Exception:
                self.pending_requests.pop(req_id, None)
                self._record_failure()
                raise

            status = result.get("status", 0)
            if status == 429 or (
                isinstance(result.get("data"), dict)
                and result["data"].get("captchaBlocked")
            ):
                self._record_failure()
                raise RuntimeError(f"FlowKit upstream rejected: status={status}")
            if not (200 <= status < 300):
                self._record_failure()
                logger.error(
                    "FlowKit upstream error: status=%s data=%s",
                    status,
                    str(result.get("data"))[:1500],
                )
                raise RuntimeError(f"FlowKit upstream error: status={status}")

            self._record_success()
            return result.get("data") or {}
        finally:
            await self._release_slot()

    async def _solve_captcha(
        self, action: str = "IMAGE_GENERATION", timeout: float = 20.0
    ) -> str:
        """Ask extension to call grecaptcha.enterprise.execute() and return the token."""
        data = await self._send(
            "solve_captcha",
            {"action": action},
            timeout=timeout,
            ws_method="solve_captcha",
        )
        token = data.get("token") if isinstance(data, dict) else None
        if not token:
            raise RuntimeError(
                "FlowKit captcha solve returned no token (is labs.google tab open?)"
            )
        return token

    def note_media_url(self, url: Optional[str], ttl: Optional[float] = None) -> None:
        """Record a fresh GCS signed URL the extension observed and volunteered.

        The extension cannot re-sign a *specific* expired URL on demand (it only
        passively sniffs URLs the Flow page fetches), so this is observability /
        best-effort hint only — the download retry in ``download_to_local`` does
        not yet correlate by mediaId.
        """
        if not url:
            return
        self.last_media_url = url
        self.last_media_refresh_at = time.time()
        logger.debug("FlowKit media URL refreshed (ttl=%s)", ttl)

    def resolve_request(self, payload: dict) -> bool:
        req_id = payload.get("id")
        if not req_id:
            return False
        fut = self.pending_requests.pop(req_id, None)
        if fut is None or fut.done():
            return False
        fut.set_result(payload)
        return True

    # ------------------------------------------------------------- public API

    async def request_image(
        self,
        prompt: str,
        char_refs: Optional[List[str]] = None,
        style_ref: Optional[str] = None,
        output_dir: Optional[str] = None,
        filename: str = "image.png",
        aspect_override: Optional[str] = None,
        seed_override: Optional[int] = None,
    ) -> str:
        """Generate an image via Flow.

        ``aspect_override`` and ``seed_override`` let callers (e.g. the avatar
        helper) opt out of the global config for one specific call — avatars
        want a square 1:1 frame plus a deterministic seed derived from the
        character name so re-extracts are idempotent, even when the user has
        a portrait/landscape global default.
        """
        char_refs = char_refs or []
        if output_dir is None:
            from services.output_paths import OUTPUT_ROOT

            output_dir = os.path.join(OUTPUT_ROOT, "images")
        cfg = self._cfg

        project_id = (cfg.flowkit_project_id or "").strip()
        if not project_id:
            raise RuntimeError(
                "flowkit_project_id is empty. Open labs.google/fx/tools/flow/project/<UUID>, "
                "copy the UUID, and set pipeline.flowkit_project_id via /api/config."
            )

        media_inputs: List[dict] = []
        for ref_path in char_refs:
            media_id = await self._upload_image(ref_path, project_id)
            media_inputs.append({"mediaId": media_id})
        if style_ref:
            media_id = await self._upload_image(style_ref, project_id)
            media_inputs.append({"mediaId": media_id})

        recaptcha = await self._solve_captcha("IMAGE_GENERATION")
        client_ctx = {
            "recaptchaContext": {
                "token": recaptcha,
                "applicationType": "RECAPTCHA_APPLICATION_TYPE_WEB",
            },
            "projectId": project_id,
            "tool": "PINHOLE",
            "sessionId": f";{int(time.time() * 1000)}",
        }
        aspect_enum = _aspect_to_enum(aspect_override or cfg.flowkit_aspect_ratio)
        seed = (
            seed_override
            if seed_override is not None
            else random.randint(0, 2_147_483_647)
        )
        # The LLM-generated negative_prompt never reaches flowkit (schema has no
        # negative field), so bake a hard no-text suffix into the positive prompt
        # to stop the model inventing captions/bubbles/signs. Idempotent.
        prompt_text = (prompt or "").strip()
        if "no speech bubble" not in prompt_text.lower():
            sep = "" if (not prompt_text or prompt_text.endswith((",", "."))) else ", "
            prompt_text = f"{prompt_text}{sep}{_NO_TEXT_SUFFIX}"
        body: Dict[str, Any] = {
            "clientContext": client_ctx,
            "mediaGenerationContext": {"batchId": str(uuid4())},
            "useNewMedia": True,
            "requests": [
                {
                    "clientContext": client_ctx,
                    "imageModelName": "GEM_PIX_2",
                    "imageAspectRatio": aspect_enum,
                    "structuredPrompt": {"parts": [{"text": prompt_text}]},
                    "seed": seed,
                    "imageInputs": media_inputs,
                }
            ],
        }

        logger.info(
            "FlowKit flowMedia:batchGenerateImages REQUEST project=%s aspect=%s refs=%d seed=%d",
            project_id,
            aspect_enum,
            len(media_inputs),
            seed,
        )
        result = await self._send(
            "flowMedia:batchGenerateImages",
            {
                "url": f"https://aisandbox-pa.googleapis.com/v1/projects/{project_id}/flowMedia:batchGenerateImages",
                "method": "POST",
                "body": body,
            },
        )
        logger.info(
            "FlowKit flowMedia:batchGenerateImages RESPONSE type=%s keys=%s",
            type(result).__name__,
            list(result.keys()) if isinstance(result, dict) else "(non-dict)",
        )

        fife_url = self._extract_fife_url(result)
        if not fife_url:
            logger.error(
                "FlowKit batchGenerateImages full response (no fifeUrl): %s",
                str(result)[:2000],
            )
            raise RuntimeError("FlowKit batchGenerateImages returned no fifeUrl")

        os.makedirs(output_dir, exist_ok=True)
        dest = os.path.join(output_dir, filename)
        return await self.download_to_local(fife_url, dest)

    # Video generation lived here: request_video(), get_job(), and a background
    # poll loop that woke every flowkit_veo_poll_interval seconds from boot to
    # check Veo jobs. It is gone with the product decision to be image-focused
    # (no video, no TTS). request_video had no production caller at all — only a
    # test — yet the poll task ran for the lifetime of every process that had
    # FlowKit enabled, which is the image path everyone uses.

    # ----------------------------------------------------------- file helpers

    async def _upload_image(self, path: str, project_id: str) -> str:
        if not os.path.isfile(path):
            raise FileNotFoundError(path)
        import base64

        with open(path, "rb") as fh:
            blob = base64.b64encode(fh.read()).decode("ascii")
        result = await self._send(
            "flow/uploadImage",
            {
                "url": "https://aisandbox-pa.googleapis.com/v1/flow/uploadImage",
                "method": "POST",
                "body": {
                    "clientContext": {"projectId": project_id, "tool": "PINHOLE"},
                    "imageBytes": blob,
                },
            },
        )
        media = result.get("media") if isinstance(result, dict) else None
        media_id = (media or {}).get("name") if isinstance(media, dict) else None
        media_id = media_id or result.get("mediaId") or result.get("media_id")
        if not media_id:
            raise RuntimeError(
                f"FlowKit uploadImage returned no mediaId; payload keys={list(result.keys()) if isinstance(result, dict) else type(result).__name__}"
            )
        return media_id

    async def download_to_local(self, url: str, dest_path: str) -> str:
        if httpx is None:  # pragma: no cover
            raise RuntimeError("httpx not installed")
        parsed = urlparse(url)
        if parsed.hostname not in _DOWNLOAD_HOSTS:
            raise ValueError(f"download host not allowlisted: {parsed.hostname}")

        os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)
        async with httpx.AsyncClient(timeout=60.0) as client:
            for attempt in range(2):
                resp = await client.get(url)
                if resp.status_code in (403, 410):
                    # GCS signed URL expired. Signal the extension (handled by
                    # background.js handleMediaRefresh — best-effort, no on-demand
                    # re-sign) then retry once. True expiry generally needs a fresh
                    # generation; this retry only recovers transient propagation 403s.
                    if attempt == 0 and self.active_ws is not None:
                        try:
                            await self.active_ws.send_json(
                                {"method": "media_urls_refresh"}
                            )
                        except Exception:
                            pass
                        await asyncio.sleep(1.0)
                        continue
                    raise RuntimeError(f"download expired: {resp.status_code}")
                resp.raise_for_status()
                with open(dest_path, "wb") as fh:
                    fh.write(resp.content)
                return os.path.abspath(dest_path)
        raise RuntimeError("download_to_local exhausted retries")

    @staticmethod
    def _extract_fife_url(payload: Any) -> Optional[str]:
        if not payload:
            return None
        if isinstance(payload, str):
            return (
                payload
                if "googleusercontent.com" in payload
                or "storage.googleapis.com" in payload
                else None
            )
        if isinstance(payload, dict):
            for key in ("fifeUrl", "fife_url", "url", "mediaUrl"):
                if key in payload and isinstance(payload[key], str):
                    return payload[key]
            for v in payload.values():
                found = FlowService._extract_fife_url(v)
                if found:
                    return found
        if isinstance(payload, list):
            for v in payload:
                found = FlowService._extract_fife_url(v)
                if found:
                    return found
        return None


flow_service = FlowService()
