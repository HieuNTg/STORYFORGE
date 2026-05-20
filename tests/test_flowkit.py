"""FlowKit integration tests — Phase 01 covers config defaults + provider registration."""

from config.defaults import PipelineConfig
from services.media.image_generator import ImageGenerator


def test_config_flowkit_defaults():
    cfg = PipelineConfig()
    assert cfg.flowkit_enabled is False
    assert cfg.flowkit_port == 7860
    assert cfg.flowkit_style_reference_path == ""
    assert cfg.flowkit_concurrent_workers == 1
    assert cfg.flowkit_concurrent_workers_max == 4
    assert cfg.flowkit_workers_ramp_threshold == 10
    assert cfg.flowkit_veo_poll_interval == 5.0
    assert cfg.flowkit_account_warning_shown is False
    assert cfg.flowkit_risk_acknowledged is False
    assert cfg.flowkit_image_input_type_split is False
    assert cfg.flowkit_callback_hmac_required is False
    assert cfg.flowkit_use_refiner is True


def test_providers_includes_flowkit():
    assert "flowkit" in ImageGenerator.PROVIDERS


# ---------------------------------------------------------------------------
# Phase 03: FlowService
# ---------------------------------------------------------------------------

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def isolated_flow_service(tmp_path, monkeypatch):
    """Fresh FlowService bound to a tmp jobs.db (singleton reset)."""
    monkeypatch.chdir(tmp_path)
    import services.media.flow_service as fs_mod

    monkeypatch.setattr(fs_mod, "_DB_DIR", str(tmp_path / "data" / "flowkit"))
    monkeypatch.setattr(fs_mod, "_DB_PATH", str(tmp_path / "data" / "flowkit" / "jobs.db"))

    fs_mod.FlowService._instance = None
    svc = fs_mod.FlowService()
    svc._ramp.threshold = 3
    svc._ramp.max_workers = 3
    yield svc
    fs_mod.FlowService._instance = None


def _fake_ws(send_capture=None):
    ws = MagicMock()
    if send_capture is not None:
        ws.send_json = AsyncMock(side_effect=lambda payload: send_capture.append(payload))
    else:
        ws.send_json = AsyncMock()
    return ws


async def _resolve_after(svc, status=200, data=None, timeout=2.0):
    """Wait (poll) until a pending request shows up, then resolve it."""
    deadline = asyncio.get_running_loop().time() + timeout
    while not svc.pending_requests:
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("no pending request appeared within timeout")
        await asyncio.sleep(0.01)
    req_id = next(reversed(svc.pending_requests))
    svc.resolve_request({"id": req_id, "status": status, "data": data or {}})


@pytest.mark.asyncio
async def test_flow_service_send_resolves_future(isolated_flow_service):
    svc = isolated_flow_service
    svc.set_active_ws(_fake_ws([]))
    task = asyncio.create_task(svc._send("ping", {"url": "https://labs.google/x"}))
    await _resolve_after(svc, 200, {"ok": True})
    assert await asyncio.wait_for(task, timeout=2) == {"ok": True}


@pytest.mark.asyncio
async def test_flow_service_send_timeout(isolated_flow_service):
    svc = isolated_flow_service
    svc.set_active_ws(_fake_ws([]))
    with pytest.raises(asyncio.TimeoutError):
        await svc._send("ping", {"url": "https://labs.google/x"}, timeout=0.05)
    assert svc.pending_requests == {}


@pytest.mark.asyncio
async def test_send_without_ws_raises(isolated_flow_service):
    svc = isolated_flow_service
    svc.active_ws = None
    with pytest.raises(ConnectionError):
        await svc._send("ping", {"url": "https://labs.google/x"})


@pytest.mark.asyncio
async def test_request_image_payload_shape(isolated_flow_service, tmp_path):
    svc = isolated_flow_service
    captured = []
    svc.set_active_ws(_fake_ws(captured))
    with patch.object(svc, "download_to_local", AsyncMock(return_value="/tmp/o.png")):
        task = asyncio.create_task(
            svc.request_image("a cat", char_refs=[], style_ref=None,
                              output_dir=str(tmp_path / "out"), filename="x.png")
        )
        await _resolve_after(svc, 200, {"fifeUrl": "https://storage.googleapis.com/x"})
        await task
    assert len(captured) == 1
    body = captured[0]["params"]["body"]
    assert body["prompt"] == "a cat"
    assert body["imageModel"] == "GEM_PIX_2"
    assert body["imageInputs"] == []
    assert captured[0]["params"]["captchaAction"] == "image_generation"


@pytest.mark.asyncio
async def test_request_image_payload_split_enabled(isolated_flow_service, tmp_path, monkeypatch):
    svc = isolated_flow_service
    from config import ConfigManager
    monkeypatch.setattr(ConfigManager().pipeline, "flowkit_image_input_type_split", True)

    captured = []
    svc.set_active_ws(_fake_ws(captured))
    monkeypatch.setattr(svc, "_upload_image", AsyncMock(side_effect=["mid-c", "mid-s"]))

    c = tmp_path / "c.png"; c.write_bytes(b"x")
    s = tmp_path / "s.png"; s.write_bytes(b"y")
    with patch.object(svc, "download_to_local", AsyncMock(return_value="/tmp/o.png")):
        task = asyncio.create_task(
            svc.request_image("x", char_refs=[str(c)], style_ref=str(s),
                              output_dir=str(tmp_path / "out"), filename="x.png")
        )
        await _resolve_after(svc, 200, {"fifeUrl": "https://storage.googleapis.com/x"})
        await task

    inputs = captured[0]["params"]["body"]["imageInputs"]
    assert {i["inputType"] for i in inputs} == {
        "IMAGE_INPUT_TYPE_CHARACTER", "IMAGE_INPUT_TYPE_STYLE",
    }


@pytest.mark.asyncio
async def test_video_job_lifecycle(isolated_flow_service, tmp_path, monkeypatch):
    svc = isolated_flow_service
    svc.set_active_ws(_fake_ws([]))
    monkeypatch.setattr(svc, "_upload_image", AsyncMock(return_value="mid-start"))
    start = tmp_path / "start.png"; start.write_bytes(b"x")

    task = asyncio.create_task(svc.request_video("a horse", str(start)))
    await _resolve_after(svc, 200, {"operationName": "op-123"})
    job_id = await task

    row = await svc.get_job(job_id)
    assert row is not None
    assert row["status"] == "PROCESSING"
    assert row["operation_name"] == "op-123"
    assert row["type"] == "video"


@pytest.mark.asyncio
async def test_download_to_local_retries_on_expired(isolated_flow_service, tmp_path):
    svc = isolated_flow_service
    ws = _fake_ws([])
    svc.set_active_ws(ws)
    fake_responses = [
        MagicMock(status_code=403, raise_for_status=MagicMock()),
        MagicMock(status_code=200, content=b"BYTES", raise_for_status=MagicMock()),
    ]

    class _Client:
        def __init__(self, *a, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url): return fake_responses.pop(0)

    dest = tmp_path / "out" / "f.png"
    with patch("services.media.flow_service.httpx") as hx:
        hx.AsyncClient = _Client
        result = await svc.download_to_local("https://storage.googleapis.com/x", str(dest))
    assert os.path.isfile(result)
    ws.send_json.assert_awaited()


@pytest.mark.asyncio
async def test_download_blocks_disallowed_host(isolated_flow_service, tmp_path):
    svc = isolated_flow_service
    with pytest.raises(ValueError):
        await svc.download_to_local("https://evil.com/x", str(tmp_path / "x.png"))


@pytest.mark.asyncio
async def test_semaphore_serialises_with_one_worker(isolated_flow_service):
    svc = isolated_flow_service
    svc.set_active_ws(_fake_ws([]))
    svc._record_failure()
    assert svc._ramp.current == 1

    state = {"in_flight": 0, "peak": 0}

    async def resolver():
        # Resolve pending requests one-by-one with a small dwell to detect overlap.
        seen = set()
        while len(seen) < 3:
            for rid in list(svc.pending_requests):
                if rid in seen:
                    continue
                seen.add(rid)
                state["in_flight"] += 1
                state["peak"] = max(state["peak"], state["in_flight"])
                await asyncio.sleep(0.02)
                svc.resolve_request({"id": rid, "status": 200, "data": {}})
                state["in_flight"] -= 1
            await asyncio.sleep(0.005)

    async def caller():
        return await svc._send("ping", {"url": "https://labs.google/x"})

    resolver_task = asyncio.create_task(resolver())
    await asyncio.gather(caller(), caller(), caller())
    resolver_task.cancel()
    try:
        await resolver_task
    except asyncio.CancelledError:
        pass
    assert state["peak"] == 1


@pytest.mark.asyncio
async def test_workers_ramp_up_after_n_success(isolated_flow_service):
    svc = isolated_flow_service
    for _ in range(3):
        svc._record_success()
    assert svc._ramp.current == 2
    for _ in range(3):
        svc._record_success()
    assert svc._ramp.current == 3


@pytest.mark.asyncio
async def test_workers_reset_on_failure(isolated_flow_service):
    svc = isolated_flow_service
    for _ in range(3):
        svc._record_success()
    assert svc._ramp.current == 2
    svc._record_failure()
    assert svc._ramp.current == 1
    assert svc._ramp.streak == 0


@pytest.mark.asyncio
async def test_clear_active_ws_fails_pending(isolated_flow_service):
    svc = isolated_flow_service
    svc.set_active_ws(_fake_ws([]))
    task = asyncio.create_task(svc._send("ping", {"url": "https://labs.google/x"}))
    await asyncio.sleep(0.02)
    svc.clear_active_ws()
    with pytest.raises((ConnectionError, RuntimeError)):
        await asyncio.wait_for(task, timeout=1)


def test_extract_fife_url_nested():
    from services.media.flow_service import FlowService
    payload = {"items": [{"meta": {"fifeUrl": "https://storage.googleapis.com/foo"}}]}
    assert FlowService._extract_fife_url(payload) == "https://storage.googleapis.com/foo"


# ---------------------------------------------------------------------------
# Phase 04: WS router + HTTP callback + status
# ---------------------------------------------------------------------------

import hashlib
import hmac
import json as _json

from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def flowkit_app(tmp_path, monkeypatch):
    """Mount FlowKit routers on an isolated FastAPI app with a clean singleton."""
    monkeypatch.chdir(tmp_path)
    import services.media.flow_service as fs_mod

    monkeypatch.setattr(fs_mod, "_DB_DIR", str(tmp_path / "data" / "flowkit"))
    monkeypatch.setattr(fs_mod, "_DB_PATH", str(tmp_path / "data" / "flowkit" / "jobs.db"))
    fs_mod.FlowService._instance = None
    svc = fs_mod.FlowService()

    import api.flowkit as flowkit_mod  # singleton looked up dynamically — no reload needed

    app = FastAPI()
    app.include_router(flowkit_mod.ws_router, prefix="/api")
    app.include_router(flowkit_mod.http_router, prefix="/api")

    yield app, svc, flowkit_mod
    fs_mod.FlowService._instance = None


def test_ws_lifecycle(flowkit_app):
    app, svc, _ = flowkit_app
    with TestClient(app) as client:
        with client.websocket_connect("/api/ws/flowkit") as ws:
            secret_msg = ws.receive_json()
            assert secret_msg["type"] == "callback_secret"
            assert secret_msg["secret"] == svc.callback_secret
            assert svc.active_ws is not None
            ws.send_json({"type": "extension_ready", "version": "1.0.0"})
            ws.send_json({"type": "token_captured", "flowKey": "AIza-fake"})
        # context exit closes ws → server hits WebSocketDisconnect → clear_active_ws
        # TestClient runs sync, so the disconnect handler completes before we get here.
    assert svc.active_ws is None
    assert svc.flow_key == "AIza-fake"


def test_ws_response_resolves_future(flowkit_app):
    app, svc, _ = flowkit_app
    with TestClient(app) as client:
        with client.websocket_connect("/api/ws/flowkit") as ws:
            ws.receive_json()  # callback_secret

            # Pre-register a pending future for a known request id.
            loop = asyncio.new_event_loop()
            try:
                fut = loop.create_future()
                svc.pending_requests["req-xyz"] = fut
                ws.send_json({"id": "req-xyz", "status": 200, "data": {"ok": True}})
                # Pump the server's dispatch by sending another message + reading nothing
                # — TestClient is synchronous so by the time send_json returns the server
                # task has been scheduled. A small wait lets it run.
                import time as _t
                deadline = _t.time() + 2.0
                while not fut.done() and _t.time() < deadline:
                    _t.sleep(0.01)
                assert fut.done(), "future not resolved by WS response"
                assert fut.result() == {"id": "req-xyz", "status": 200, "data": {"ok": True}}
            finally:
                loop.close()


def test_ext_callback_hmac_disabled_accepts_plaintext(flowkit_app, monkeypatch):
    app, svc, _ = flowkit_app
    from config import ConfigManager
    monkeypatch.setattr(ConfigManager().pipeline, "flowkit_callback_hmac_required", False)

    loop = asyncio.new_event_loop()
    try:
        fut = loop.create_future()
        svc.pending_requests["req-plain"] = fut
        with TestClient(app) as client:
            r = client.post(
                "/api/ext/callback",
                json={"id": "req-plain", "status": 200, "data": {"v": 1}},
            )
        assert r.status_code == 200
        assert fut.done() and fut.result()["data"] == {"v": 1}
    finally:
        loop.close()


def test_ext_callback_hmac_invalid_401(flowkit_app, monkeypatch):
    app, svc, _ = flowkit_app
    from config import ConfigManager
    monkeypatch.setattr(ConfigManager().pipeline, "flowkit_callback_hmac_required", True)

    body = b'{"id":"req-bad","status":200,"data":{}}'
    with TestClient(app) as client:
        r = client.post(
            "/api/ext/callback",
            content=body,
            headers={"X-Callback-Signature": "deadbeef", "Content-Type": "application/json"},
        )
    assert r.status_code == 401


def test_ext_callback_hmac_valid_resolves(flowkit_app, monkeypatch):
    app, svc, _ = flowkit_app
    from config import ConfigManager
    monkeypatch.setattr(ConfigManager().pipeline, "flowkit_callback_hmac_required", True)

    loop = asyncio.new_event_loop()
    try:
        fut = loop.create_future()
        svc.pending_requests["req-good"] = fut
        body = _json.dumps({"id": "req-good", "status": 200, "data": {"ok": True}}).encode()
        sig = hmac.new(svc.callback_secret.encode(), body, hashlib.sha256).hexdigest()
        with TestClient(app) as client:
            r = client.post(
                "/api/ext/callback",
                content=body,
                headers={"X-Callback-Signature": sig, "Content-Type": "application/json"},
            )
        assert r.status_code == 200
        assert fut.done() and fut.result()["data"] == {"ok": True}
    finally:
        loop.close()


def test_flowkit_status_disconnected(flowkit_app):
    app, svc, _ = flowkit_app
    svc.active_ws = None
    with TestClient(app) as client:
        r = client.get("/api/flowkit/status")
    assert r.status_code == 200
    body = r.json()
    assert body["connected"] is False
    assert body["pending_ws_requests"] == 0
    assert body["workers_current"] >= 1


def test_flowkit_status_connected(flowkit_app):
    app, svc, _ = flowkit_app
    with TestClient(app) as client:
        with client.websocket_connect("/api/ws/flowkit") as ws:
            ws.receive_json()  # secret
            r = client.get("/api/flowkit/status")
            assert r.status_code == 200
            assert r.json()["connected"] is True


def test_ext_callback_rejects_invalid_json(flowkit_app, monkeypatch):
    app, _, _ = flowkit_app
    from config import ConfigManager
    monkeypatch.setattr(ConfigManager().pipeline, "flowkit_callback_hmac_required", False)
    with TestClient(app) as client:
        r = client.post(
            "/api/ext/callback",
            content=b"not-json{",
            headers={"Content-Type": "application/json"},
        )
    assert r.status_code == 400


def test_redact_strips_sensitive_keys():
    from api.flowkit import _redact
    out = _redact({"flowKey": "secret", "nested": {"Authorization": "Bearer x", "ok": 1}})
    assert out["flowKey"] == "<redacted>"
    assert out["nested"]["Authorization"] == "<redacted>"
    assert out["nested"]["ok"] == 1


@pytest.mark.asyncio
async def test_no_overshoot_on_ramp_down_mid_flight(isolated_flow_service):
    """Regression: a ramp reset while N callers are in-flight must not let a new
    caller bypass the new cap. Condition-gate (vs swapped semaphore) guarantees
    in-flight callers can never exceed _ramp.current."""
    svc = isolated_flow_service
    svc.set_active_ws(_fake_ws([]))
    # Start at 3 workers.
    for _ in range(3):
        svc._record_success()
    assert svc._ramp.current == 2  # threshold=3, max=3 -> ramped once
    for _ in range(3):
        svc._record_success()
    assert svc._ramp.current == 3

    state = {"active": 0, "peak_after_reset": 0, "reset_done": False}

    async def resolver():
        seen = set()
        while len(seen) < 4:
            for rid in list(svc.pending_requests):
                if rid in seen:
                    continue
                seen.add(rid)
                state["active"] += 1
                if state["reset_done"]:
                    state["peak_after_reset"] = max(state["peak_after_reset"], state["active"])
                await asyncio.sleep(0.02)
                svc.resolve_request({"id": rid, "status": 200, "data": {}})
                state["active"] -= 1
            await asyncio.sleep(0.005)

    async def caller():
        return await svc._send("ping", {"url": "https://labs.google/x"})

    resolver_task = asyncio.create_task(resolver())
    # Kick off 4 callers; immediately reset ramp.
    callers = [asyncio.create_task(caller()) for _ in range(4)]
    await asyncio.sleep(0.005)
    svc._record_failure()
    state["reset_done"] = True
    assert svc._ramp.current == 1
    await asyncio.gather(*callers)
    resolver_task.cancel()
    try:
        await resolver_task
    except asyncio.CancelledError:
        pass
    # After reset, no NEW caller may enter while the active count >= 1.
    # Peak observed under the new cap must be <= 1 (current).
    assert state["peak_after_reset"] <= 1, f"overshoot after ramp-down: {state['peak_after_reset']}"
