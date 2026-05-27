"""FlowKit WS + HTTP routes — single-extension WS singleton + HMAC-gated callback.

WS:    /api/ws/flowkit         (accepts the lone Chrome extension)
HTTP:  /api/ext/callback       (extension fallback; HMAC-gated by config)
       /api/flowkit/status     (frontend badge / health probe)
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect

from config import ConfigManager
from services.media.flow_service import FlowService


def _svc() -> FlowService:
    return FlowService()

logger = logging.getLogger(__name__)

ws_router = APIRouter(prefix="/ws/flowkit", tags=["flowkit"])
http_router = APIRouter(tags=["flowkit"])

_REDACT_KEYS = {
    "flowKey", "flow_key", "authorization", "Authorization",
    "cookie", "Cookie", "secret", "callback_secret",
}


def _redact(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {k: ("<redacted>" if k in _REDACT_KEYS else _redact(v)) for k, v in payload.items()}
    if isinstance(payload, list):
        return [_redact(v) for v in payload]
    return payload


async def _dispatch(msg: Dict[str, Any]) -> None:
    if not isinstance(msg, dict):
        logger.warning("FlowKit WS dropped non-dict frame: %r", msg)
        return

    if "id" in msg and ("status" in msg or "error" in msg or "data" in msg):
        _svc().resolve_request(msg)
        return

    mtype = msg.get("type")
    if mtype == "extension_ready":
        logger.info("FlowKit extension ready (manifest=%s)", msg.get("version"))
    elif mtype == "token_captured":
        _svc().flow_key = msg.get("flowKey") or msg.get("flow_key")
        _svc().flow_key_captured_at = time.time()
        logger.info("FlowKit flow key captured")
    elif mtype == "pong":
        _svc().last_pong_at = time.time()
    elif mtype == "media_urls_refresh":
        _svc().last_media_refresh_at = time.time()
        logger.debug("FlowKit media URLs refreshed")
    else:
        logger.debug("FlowKit WS unknown frame: %s", _redact(msg))


@ws_router.websocket("")
async def flowkit_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    _svc().set_active_ws(websocket)
    try:
        await websocket.send_json(
            {"type": "callback_secret", "secret": _svc().callback_secret}
        )
        while True:
            msg = await websocket.receive_json()
            # Drop frames from a stale connection that's been superseded by a reconnect.
            if _svc().active_ws is not websocket:
                logger.debug("FlowKit WS dropping stale frame from superseded connection")
                continue
            await _dispatch(msg)
    except WebSocketDisconnect:
        logger.info("FlowKit WS disconnected")
    except Exception:
        logger.exception("FlowKit WS error")
    finally:
        if _svc().active_ws is websocket:
            _svc().clear_active_ws()


@http_router.post("/ext/callback")
async def ext_callback(request: Request) -> Dict[str, bool]:
    body = await request.body()
    cfg = ConfigManager().pipeline
    if cfg.flowkit_callback_hmac_required:
        sig = request.headers.get("X-Callback-Signature", "")
        expected = hmac.new(
            _svc().callback_secret.encode("utf-8"),
            body,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(sig, expected):
            raise HTTPException(status_code=401, detail="HMAC mismatch")

    try:
        payload = json.loads(body or b"{}")
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    _svc().resolve_request(payload)
    return {"ok": True}


@http_router.get("/flowkit/status")
async def flowkit_status() -> Dict[str, Any]:
    svc = _svc()
    captured_at = getattr(svc, "flow_key_captured_at", None)
    age = int(time.time() - captured_at) if captured_at else -1
    poll_task = getattr(svc, "_poll_task", None)
    return {
        "connected": svc.active_ws is not None,
        "last_token_age_s": age,
        "pending_ws_requests": len(svc.pending_requests),
        "poll_running": bool(poll_task and not poll_task.done()),
        "workers_current": svc._ramp.current,
        "workers_max": svc._ramp.max_workers,
    }
