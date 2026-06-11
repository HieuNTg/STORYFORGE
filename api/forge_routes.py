"""Forge-from-Sentence routes — fast synchronous BFF over cheap_model.

Endpoints
---------
- ``POST /api/forge/sentence``        — sync; returns full ForgeResponse JSON.
- ``POST /api/forge/sentence/stream`` — SSE; emits ``stage`` events then ``final``.

Both endpoints:
- Return 404 when ``PipelineConfig.enable_sentence_forge`` is False.
- Are rate-limited 5 req/min/IP using the existing rate limiter backend
  (Redis if ``REDIS_URL`` is set, in-memory fallback otherwise).
- Read the LLM via :class:`services.llm.client.LLMClient` singleton.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from config import ConfigManager
from models.schemas import ForgeRequest, ForgeResponse
from services.forge_service import forge_from_sentence

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/forge", tags=["forge"])


# ---------------------------------------------------------------------------
# Rate limiter (5/min/IP) — piggy-backs on existing backend.
# ---------------------------------------------------------------------------

FORGE_LIMIT_PER_MIN = int(os.environ.get("STORYFORGE_FORGE_RATE_LIMIT", "5"))
_FORGE_WINDOW = 60.0

# In-memory fallback (per-process). Redis path mirrors middleware/rate_limiter.
_forge_lock = threading.Lock()
_forge_state: dict[str, list[float]] = {}


def _client_ip(request: Request) -> str:
    """Resolve client IP, honoring X-Forwarded-For only from trusted proxies.

    Delegates to ``middleware.rate_limiter._get_ip`` so this route shares the
    same proxy-trust policy as the global middleware. Falls back to direct
    socket IP if that helper is unavailable (e.g. unit tests).
    """
    try:
        from middleware.rate_limiter import _get_ip  # type: ignore

        return _get_ip(request)
    except Exception:  # noqa: BLE001 — degrade gracefully
        return request.client.host if request.client else "unknown"


def _check_forge_rate(ip: str) -> bool:
    """True if request is allowed under 5/min/IP. Sliding window per IP."""
    # Try Redis backend first (reuse env var REDIS_URL).
    if os.environ.get("REDIS_URL"):
        try:
            from middleware.rate_limiter import _get_redis  # type: ignore

            r = _get_redis()
            if r is not None:
                key = f"sf:ratelimit:forge:{ip}"
                count = r.incr(key)
                if count == 1:
                    r.expire(key, int(_FORGE_WINDOW))
                return int(count) <= FORGE_LIMIT_PER_MIN
        except Exception as e:  # noqa: BLE001 — fall through to memory
            logger.debug("forge rate redis path failed: %s", e)

    now = time.monotonic()
    with _forge_lock:
        bucket = _forge_state.setdefault(ip, [])
        # Drop timestamps older than the window.
        cutoff = now - _FORGE_WINDOW
        i = 0
        while i < len(bucket) and bucket[i] < cutoff:
            i += 1
        if i:
            del bucket[:i]
        if len(bucket) >= FORGE_LIMIT_PER_MIN:
            return False
        bucket.append(now)
        return True


def _ensure_enabled() -> None:
    cfg = ConfigManager()
    if not getattr(cfg.pipeline, "enable_sentence_forge", False):
        raise HTTPException(status_code=404, detail="forge endpoint disabled")


def _rate_limit_dep(request: Request) -> None:
    ip = _client_ip(request)
    if not _check_forge_rate(ip):
        raise HTTPException(status_code=429, detail="forge rate limit exceeded (5/min)")


def _get_llm():
    """Lazy import + return the LLMClient singleton.

    Tests monkey-patch this module attribute to inject a mock LLM.
    """
    from services.llm_client import LLMClient

    return LLMClient()


def _resolve_model() -> str | None:
    cfg = ConfigManager()
    override = (getattr(cfg.pipeline, "forge_cheap_model_override", "") or "").strip()
    if override:
        return override
    cheap = (getattr(cfg.llm, "cheap_model", "") or "").strip()
    return cheap or None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post(
    "/sentence",
    response_model=ForgeResponse,
    dependencies=[Depends(_rate_limit_dep)],
)
async def forge_sentence(
    req: ForgeRequest,
    _enabled: None = Depends(_ensure_enabled),
) -> ForgeResponse:
    """Synchronous forge. Runs the (sync) LLM call in a threadpool."""
    llm = _get_llm()
    model = _resolve_model()
    try:
        # forge_from_sentence is sync; offload to avoid blocking event loop.
        result = await asyncio.wait_for(
            asyncio.to_thread(forge_from_sentence, llm, req.sentenceIdea, model),
            timeout=45.0,
        )
        return result
    except asyncio.TimeoutError:
        logger.warning("forge timeout for sentence len=%d", len(req.sentenceIdea))
        raise HTTPException(status_code=504, detail="forge timeout")
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — sanitize before returning
        logger.exception("forge_sentence failed")
        raise HTTPException(status_code=502, detail=f"forge failed: {type(e).__name__}")


def _sse(event: str, data: dict | str) -> bytes:
    if not isinstance(data, str):
        data = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {data}\n\n".encode("utf-8")


@router.post(
    "/sentence/stream",
    dependencies=[Depends(_rate_limit_dep)],
)
async def forge_sentence_stream(
    req: ForgeRequest,
    _enabled: None = Depends(_ensure_enabled),
) -> StreamingResponse:
    """SSE wrapper around the sync forge. Emits coarse progress stages, then
    a single ``final`` event with the validated ForgeResponse JSON.

    Stages (order): planning → characters → chapter → choices → final.
    These are heuristic markers around a single LLM round-trip — we do not
    stream tokens here (the underlying service uses ``generate_json``).
    """
    llm = _get_llm()
    model = _resolve_model()
    sentence = req.sentenceIdea

    async def gen():
        yield _sse("forge.stage", {"stage": "planning"})
        # Single LLM call in a thread; emit stage hints while it runs.
        task = asyncio.create_task(
            asyncio.to_thread(forge_from_sentence, llm, sentence, model)
        )
        # Heuristic: emit stage events at fixed cadence while waiting.
        stages = ["characters", "chapter", "choices"]
        idx = 0
        try:
            while not task.done():
                await asyncio.sleep(1.5)
                if idx < len(stages) and not task.done():
                    yield _sse("forge.stage", {"stage": stages[idx]})
                    idx += 1
            try:
                result: ForgeResponse = task.result()
                yield _sse("forge.final", result.model_dump())
            except Exception as e:  # noqa: BLE001
                logger.exception("forge stream failed")
                yield _sse(
                    "forge.error", {"error": type(e).__name__, "message": str(e)[:200]}
                )
        except asyncio.CancelledError:
            task.cancel()
            raise

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


__all__ = ["router"]
