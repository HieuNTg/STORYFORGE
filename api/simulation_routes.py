"""Simulation transcript routes — structured TranscriptTurn[] view.

Endpoints
---------
- ``GET  /api/simulation/{session_id}/transcript`` — extracts the simulator
  artifact for an existing pipeline session into ``SimulationTranscript``.
- ``POST /api/simulation/continue`` — generates ONE next ``TranscriptTurn``
  via cheap_model, given recent history + characters + topic.

Both endpoints return 404 when ``enable_simulation_transcript`` is False.
The continue endpoint is rate-limited (10/min/IP, separate bucket).
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from config import ConfigManager
from models.schemas import (
    SimulationContinueRequest,
    SimulationTranscript,
    TranscriptTurn,
)
from services.simulation_continue_service import continue_dialogue
from services.simulation_transcript_extractor import extract as extract_transcript

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/simulation", tags=["simulation"])

CONTINUE_LIMIT_PER_MIN = int(os.environ.get("STORYFORGE_SIMULATION_RATE_LIMIT", "10"))
_CONTINUE_WINDOW = 60.0

_continue_lock = threading.Lock()
_continue_state: dict[str, list[float]] = {}


def _client_ip(request: Request) -> str:
    try:
        from middleware.rate_limiter import _get_ip  # type: ignore
        return _get_ip(request)
    except Exception:  # noqa: BLE001
        return request.client.host if request.client else "unknown"


def _check_continue_rate(ip: str) -> bool:
    if os.environ.get("REDIS_URL"):
        try:
            from middleware.rate_limiter import _get_redis  # type: ignore
            r = _get_redis()
            if r is not None:
                key = f"sf:ratelimit:simulation:{ip}"
                # Atomic INCR + EXPIRE via pipeline so a partial failure cannot
                # leave a counter with no TTL (would leak the bucket forever).
                pipe = r.pipeline()
                pipe.incr(key)
                pipe.expire(key, int(_CONTINUE_WINDOW), nx=True)
                count, _ = pipe.execute()
                return int(count) <= CONTINUE_LIMIT_PER_MIN
        except Exception as e:  # noqa: BLE001
            logger.debug("simulation rate redis path failed: %s", e)

    now = time.monotonic()
    with _continue_lock:
        bucket = _continue_state.setdefault(ip, [])
        cutoff = now - _CONTINUE_WINDOW
        i = 0
        while i < len(bucket) and bucket[i] < cutoff:
            i += 1
        if i:
            del bucket[:i]
        if len(bucket) >= CONTINUE_LIMIT_PER_MIN:
            return False
        bucket.append(now)
        return True


def _ensure_enabled() -> None:
    cfg = ConfigManager()
    if not getattr(cfg.pipeline, "enable_simulation_transcript", False):
        raise HTTPException(status_code=404, detail="simulation endpoint disabled")


def _rate_limit_dep(request: Request) -> None:
    ip = _client_ip(request)
    if not _check_continue_rate(ip):
        raise HTTPException(
            status_code=429,
            detail=f"simulation rate limit exceeded ({CONTINUE_LIMIT_PER_MIN}/min)",
        )


def _get_llm():
    from services.llm_client import LLMClient
    return LLMClient()


def _resolve_model() -> str | None:
    cfg = ConfigManager()
    override = (getattr(cfg.pipeline, "simulation_continue_cheap_model_override", "") or "").strip()
    if override:
        return override
    cheap = (getattr(cfg.llm, "cheap_model", "") or "").strip()
    return cheap or None


def _lookup_session_artifact(session_id: str) -> Any:
    """Best-effort lookup of a simulator artifact for an existing session."""
    try:
        from api.pipeline_routes import _sessions  # type: ignore
    except Exception:
        return None
    entry = _sessions.get(session_id)
    if not entry:
        return None
    orch = entry[0]
    output = getattr(orch, "output", None)
    return getattr(output, "simulation_result", None) if output is not None else None


@router.get(
    "/{session_id}/transcript",
    response_model=SimulationTranscript,
)
async def get_transcript_route(
    session_id: str,
    _enabled: None = Depends(_ensure_enabled),
) -> SimulationTranscript:
    artifact = _lookup_session_artifact(session_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="simulation artifact not found")
    return extract_transcript(artifact)


@router.post(
    "/continue",
    response_model=TranscriptTurn,
    dependencies=[Depends(_rate_limit_dep)],
)
async def continue_route(
    req: SimulationContinueRequest,
    _enabled: None = Depends(_ensure_enabled),
) -> TranscriptTurn:
    llm = _get_llm()
    model = _resolve_model()
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(
                continue_dialogue,
                llm,
                req.characters,
                req.historyLogs,
                req.topic,
                req.dramaLevel or "high",
                model,
            ),
            timeout=30.0,
        )
        return result
    except asyncio.TimeoutError:
        logger.warning("simulation continue timeout")
        raise HTTPException(status_code=504, detail="simulation continue timeout")
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        logger.exception("continue_route failed")
        raise HTTPException(
            status_code=502,
            detail=f"simulation continue failed: {type(e).__name__}",
        )


__all__ = ["router"]
