"""FlowKit integration tests — Phase 01 covers config defaults + provider registration."""

from config.defaults import PipelineConfig
from services.media.image_generator import ImageGenerator


def test_config_flowkit_defaults():
    cfg = PipelineConfig()
    # FlowKit is now the default image provider (Batch 1-3 pivot to image-focused product),
    # so flowkit_enabled and flowkit_risk_acknowledged default to True.
    assert cfg.flowkit_enabled is True
    assert cfg.flowkit_port == 7860
    assert cfg.flowkit_style_reference_path == ""
    assert cfg.flowkit_concurrent_workers == 1
    assert cfg.flowkit_concurrent_workers_max == 4
    assert cfg.flowkit_workers_ramp_threshold == 10
    assert cfg.flowkit_veo_poll_interval == 5.0
    assert cfg.flowkit_account_warning_shown is False
    assert cfg.flowkit_risk_acknowledged is True
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
async def test_request_image_payload_shape(isolated_flow_service, tmp_path, monkeypatch):
    svc = isolated_flow_service
    # request_image short-circuits when flowkit_project_id is empty (real
    # contract: Google Labs Flow needs a project UUID). Inject a fake one so
    # the request actually hits the WS layer. Captcha is solved out-of-band
    # via _solve_captcha — bypass it to keep the test focused on body shape.
    from config import ConfigManager
    monkeypatch.setattr(ConfigManager().pipeline, "flowkit_project_id", "test-project")
    monkeypatch.setattr(svc, "_solve_captcha", AsyncMock(return_value="fake-token"))
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
    # New flowMedia:batchGenerateImages schema nests prompt/model under requests[0].
    req0 = body["requests"][0]
    # Phase 1: the positive prompt now carries a hard no-text suffix (flowkit has
    # no negative-prompt field) — assert the original prompt + suffix are present.
    text = req0["structuredPrompt"]["parts"][0]["text"]
    assert text.startswith("a cat")
    assert "no text" in text
    assert "no speech bubble" in text
    assert req0["imageModelName"] == "GEM_PIX_2"
    assert req0["imageInputs"] == []


@pytest.mark.asyncio
async def test_request_image_payload_split_enabled(isolated_flow_service, tmp_path, monkeypatch):
    svc = isolated_flow_service
    from config import ConfigManager
    monkeypatch.setattr(ConfigManager().pipeline, "flowkit_image_input_type_split", True)
    monkeypatch.setattr(ConfigManager().pipeline, "flowkit_project_id", "test-project")
    monkeypatch.setattr(svc, "_solve_captcha", AsyncMock(return_value="fake-token"))

    captured = []
    svc.set_active_ws(_fake_ws(captured))
    monkeypatch.setattr(svc, "_upload_image", AsyncMock(side_effect=["mid-c", "mid-s"]))

    c = tmp_path / "c.png"
    c.write_bytes(b"x")
    s = tmp_path / "s.png"
    s.write_bytes(b"y")
    with patch.object(svc, "download_to_local", AsyncMock(return_value="/tmp/o.png")):
        task = asyncio.create_task(
            svc.request_image("x", char_refs=[str(c)], style_ref=str(s),
                              output_dir=str(tmp_path / "out"), filename="x.png")
        )
        await _resolve_after(svc, 200, {"fifeUrl": "https://storage.googleapis.com/x"})
        await task

    inputs = captured[0]["params"]["body"]["requests"][0]["imageInputs"]
    # Refs are passed as {"mediaId": ...} entries; split flag controls inputType
    # decoration when the live enum sniff has populated the type map. In the
    # default test config the type map is empty so only mediaId is asserted.
    assert len(inputs) == 2
    assert all("mediaId" in i for i in inputs)


@pytest.mark.asyncio
async def test_video_job_lifecycle(isolated_flow_service, tmp_path, monkeypatch):
    svc = isolated_flow_service
    from config import ConfigManager
    monkeypatch.setattr(ConfigManager().pipeline, "flowkit_project_id", "test-project")
    svc.set_active_ws(_fake_ws([]))
    monkeypatch.setattr(svc, "_upload_image", AsyncMock(return_value="mid-start"))
    start = tmp_path / "start.png"
    start.write_bytes(b"x")

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
# Phase 1: comic aspect ratio + no-text suffix in flowkit body
# ---------------------------------------------------------------------------


def test_aspect_enum_map_includes_comic_4_5():
    """Phase 1: '4:5' must resolve to a valid (accepted) portrait enum, not the
    PORTRAIT default fallback for an unknown key."""
    from services.media.flow_service import _ASPECT_ENUM_MAP, _aspect_to_enum
    assert "4:5" in _ASPECT_ENUM_MAP
    enum = _aspect_to_enum("4:5")
    assert enum.startswith("IMAGE_ASPECT_RATIO_")
    # Must not silently degrade to the unknown-key default (9:16 portrait).
    assert enum != "IMAGE_ASPECT_RATIO_PORTRAIT"


def test_default_aspect_ratio_is_comic_panel():
    """Config default aspect ratio is the comic webtoon panel, not 9:16 wallpaper."""
    from config.defaults import PipelineConfig
    assert PipelineConfig().flowkit_aspect_ratio == "4:5"


@pytest.mark.asyncio
async def test_request_image_appends_no_text_suffix_and_comic_aspect(
    isolated_flow_service, tmp_path, monkeypatch
):
    """The flowkit request body must carry the no-text suffix appended to the
    positive prompt AND the configured comic aspect enum."""
    svc = isolated_flow_service
    from config import ConfigManager
    cfg = ConfigManager().pipeline
    monkeypatch.setattr(cfg, "flowkit_project_id", "test-project")
    monkeypatch.setattr(cfg, "flowkit_aspect_ratio", "4:5")
    monkeypatch.setattr(svc, "_solve_captcha", AsyncMock(return_value="fake-token"))
    captured = []
    svc.set_active_ws(_fake_ws(captured))
    with patch.object(svc, "download_to_local", AsyncMock(return_value="/tmp/o.png")):
        task = asyncio.create_task(
            svc.request_image("a ruined village", char_refs=[], style_ref=None,
                              output_dir=str(tmp_path / "out"), filename="x.png")
        )
        await _resolve_after(svc, 200, {"fifeUrl": "https://storage.googleapis.com/x"})
        await task

    req0 = captured[0]["params"]["body"]["requests"][0]
    text = req0["structuredPrompt"]["parts"][0]["text"]
    assert text.startswith("a ruined village")
    for token in ("no text", "no watermark", "no caption", "no speech bubble"):
        assert token in text, token
    # 4:5 maps to an accepted portrait enum (not the unknown-key 9:16 default).
    assert req0["imageAspectRatio"].startswith("IMAGE_ASPECT_RATIO_")
    assert req0["imageAspectRatio"] != "IMAGE_ASPECT_RATIO_PORTRAIT"


@pytest.mark.asyncio
async def test_request_image_no_text_suffix_idempotent(
    isolated_flow_service, tmp_path, monkeypatch
):
    """If the prompt already carries the no-text instruction the suffix is not
    appended twice."""
    svc = isolated_flow_service
    from config import ConfigManager
    monkeypatch.setattr(ConfigManager().pipeline, "flowkit_project_id", "test-project")
    monkeypatch.setattr(svc, "_solve_captcha", AsyncMock(return_value="fake-token"))
    captured = []
    svc.set_active_ws(_fake_ws(captured))
    prompt = "medium shot, hero, cel shading, no speech bubble, no text"
    with patch.object(svc, "download_to_local", AsyncMock(return_value="/tmp/o.png")):
        task = asyncio.create_task(
            svc.request_image(prompt, char_refs=[], style_ref=None,
                              output_dir=str(tmp_path / "out"), filename="x.png")
        )
        await _resolve_after(svc, 200, {"fifeUrl": "https://storage.googleapis.com/x"})
        await task

    text = captured[0]["params"]["body"]["requests"][0]["structuredPrompt"]["parts"][0]["text"]
    assert text.count("no speech bubble") == 1


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
            # Real extension (background.js) sends the captured Bearer token under
            # the "token" key — the backend must read it (regression: it only read
            # "flowKey"/"flow_key", so live token capture silently no-op'd).
            ws.send_json({"type": "token_captured", "token": "AIza-fake"})
        # context exit closes ws → server hits WebSocketDisconnect → clear_active_ws
        # TestClient runs sync, so the disconnect handler completes before we get here.
    assert svc.active_ws is None
    assert svc.flow_key == "AIza-fake"


def test_ws_token_captured_accepts_legacy_flowkey(flowkit_app):
    """Back-compat: the older `flowKey` field is still honored."""
    app, svc, _ = flowkit_app
    with TestClient(app) as client:
        with client.websocket_connect("/api/ws/flowkit") as ws:
            ws.receive_json()  # callback_secret
            ws.send_json({"type": "token_captured", "flowKey": "AIza-legacy"})
    assert svc.flow_key == "AIza-legacy"


def test_ws_media_url_refreshed_captured(flowkit_app):
    """Extension volunteers a fresh GCS URL via `media_url_refreshed`; the backend
    must capture it (regression: it listened for `media_urls_refresh` and dropped
    the frame, discarding the URL)."""
    app, svc, _ = flowkit_app
    assert svc.last_media_url is None
    with TestClient(app) as client:
        with client.websocket_connect("/api/ws/flowkit") as ws:
            ws.receive_json()  # callback_secret
            ws.send_json({
                "type": "media_url_refreshed",
                "url": "https://storage.googleapis.com/fresh",
                "ttl": 3600,
            })
    assert svc.last_media_url == "https://storage.googleapis.com/fresh"
    assert svc.last_media_refresh_at > 0


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


# ---------------------------------------------------------------------------
# Phase 05: ImageGenerator flowkit provider + per-session dirs + refiner
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_image_gen_env(tmp_path, monkeypatch):
    """Run image-gen tests in a tmp cwd so output/ writes don't pollute the repo."""
    monkeypatch.chdir(tmp_path)
    import services.media.flow_service as fs_mod
    monkeypatch.setattr(fs_mod, "_DB_DIR", str(tmp_path / "data" / "flowkit"))
    monkeypatch.setattr(fs_mod, "_DB_PATH", str(tmp_path / "data" / "flowkit" / "jobs.db"))
    fs_mod.FlowService._instance = None
    yield tmp_path
    fs_mod.FlowService._instance = None


def test_output_dir_per_session(isolated_image_gen_env):
    from services.media.image_generator import ImageGenerator
    gen = ImageGenerator(provider="none", session_id="abc123", story_title="Tiên Hiệp Test!")
    # Per-story layout: images live under output/<story-slug>/images, where the
    # slug is slug_session_dir(title, session_id).
    assert gen.output_dir.replace("\\", "/").endswith("output/tien_hiep_test__abc123/images")
    assert os.path.isdir(gen.output_dir)


def test_output_dir_fallback(isolated_image_gen_env):
    from services.media.image_generator import ImageGenerator
    gen = ImageGenerator(provider="none")
    assert gen.output_dir.replace("\\", "/") == "output/images"


def test_slug_session_dir_helper():
    from services.media._util import slug_session_dir
    assert slug_session_dir("Hello World!", "sid1") == "hello_world__sid1"
    assert slug_session_dir("", "x") == "story_x"
    assert slug_session_dir("a" * 100, "s") == "a" * 60 + "_s"


@pytest.mark.asyncio
async def test_generate_with_ref_flowkit_branch(isolated_image_gen_env, monkeypatch):
    """Patch flow_service.request_image; assert _flowkit_with_ref routes correctly."""
    from config import ConfigManager
    monkeypatch.setattr(ConfigManager().pipeline, "image_provider", "flowkit")
    monkeypatch.setattr(ConfigManager().pipeline, "flowkit_enabled", True)
    monkeypatch.setattr(ConfigManager().pipeline, "flowkit_use_refiner", False)

    import services.media.flow_service as fs_mod
    fs_mod.FlowService._instance = None
    svc = fs_mod.FlowService()
    svc.active_ws = MagicMock()  # truthy
    svc._main_loop = asyncio.get_running_loop()

    captured: dict = {}

    async def fake_request_image(prompt, char_refs, style_ref, output_dir, filename):
        captured.update(
            prompt=prompt, char_refs=list(char_refs),
            style_ref=style_ref, output_dir=output_dir, filename=filename,
        )
        return os.path.join(output_dir, filename)

    monkeypatch.setattr(svc, "request_image", fake_request_image)

    from services.media.image_generator import ImageGenerator
    gen = ImageGenerator(provider="flowkit", session_id="s1", story_title="Story")

    result = await asyncio.to_thread(
        gen.generate_with_reference, "a hero", ["/tmp/ref.png"], "scene_1.png"
    )
    assert result is not None
    assert captured["prompt"] == "a hero"
    assert captured["char_refs"] == ["/tmp/ref.png"]
    assert captured["style_ref"] is None  # split flag off → no style ref
    assert captured["filename"] == "scene_1.png"


@pytest.mark.asyncio
async def test_flowkit_image_input_type_split_off_no_style(isolated_image_gen_env, monkeypatch, tmp_path):
    from config import ConfigManager
    cfg = ConfigManager().pipeline
    monkeypatch.setattr(cfg, "flowkit_enabled", True)
    monkeypatch.setattr(cfg, "flowkit_use_refiner", False)
    monkeypatch.setattr(cfg, "flowkit_image_input_type_split", False)
    style_path = tmp_path / "style.png"
    style_path.write_bytes(b"x")
    monkeypatch.setattr(cfg, "flowkit_style_reference_path", str(style_path))

    import services.media.flow_service as fs_mod
    fs_mod.FlowService._instance = None
    svc = fs_mod.FlowService()
    svc.active_ws = MagicMock()
    svc._main_loop = asyncio.get_running_loop()

    captured: dict = {}

    async def fake_request_image(prompt, char_refs, style_ref, output_dir, filename):
        captured["style_ref"] = style_ref
        return os.path.join(output_dir, filename)

    monkeypatch.setattr(svc, "request_image", fake_request_image)

    from services.media.image_generator import ImageGenerator
    gen = ImageGenerator(provider="flowkit")
    await asyncio.to_thread(gen.generate_with_reference, "p", ["/tmp/c.png"], "f.png")
    # Split flag off: style_ref must be None even if path is configured.
    assert captured["style_ref"] is None


@pytest.mark.asyncio
async def test_flowkit_image_input_type_split_on_passes_style(isolated_image_gen_env, monkeypatch, tmp_path):
    from config import ConfigManager
    cfg = ConfigManager().pipeline
    monkeypatch.setattr(cfg, "flowkit_enabled", True)
    monkeypatch.setattr(cfg, "flowkit_use_refiner", False)
    monkeypatch.setattr(cfg, "flowkit_image_input_type_split", True)
    style_path = tmp_path / "style.png"
    style_path.write_bytes(b"x")
    monkeypatch.setattr(cfg, "flowkit_style_reference_path", str(style_path))

    import services.media.flow_service as fs_mod
    fs_mod.FlowService._instance = None
    svc = fs_mod.FlowService()
    svc.active_ws = MagicMock()
    svc._main_loop = asyncio.get_running_loop()

    captured: dict = {}

    async def fake_request_image(prompt, char_refs, style_ref, output_dir, filename):
        captured["style_ref"] = style_ref
        return os.path.join(output_dir, filename)

    monkeypatch.setattr(svc, "request_image", fake_request_image)

    from services.media.image_generator import ImageGenerator
    gen = ImageGenerator(provider="flowkit")
    await asyncio.to_thread(gen.generate_with_reference, "p", ["/tmp/c.png"], "f.png")
    assert captured["style_ref"] == str(style_path)


@pytest.mark.asyncio
async def test_refiner_called_when_enabled(isolated_image_gen_env, monkeypatch):
    from config import ConfigManager
    monkeypatch.setattr(ConfigManager().pipeline, "flowkit_enabled", True)
    monkeypatch.setattr(ConfigManager().pipeline, "flowkit_use_refiner", True)

    import services.media.flow_service as fs_mod
    fs_mod.FlowService._instance = None
    svc = fs_mod.FlowService()
    svc.active_ws = MagicMock()
    svc._main_loop = asyncio.get_running_loop()

    captured: dict = {}

    async def fake_request_image(prompt, *a, **kw):
        captured["prompt"] = prompt
        return "/tmp/x.png"

    monkeypatch.setattr(svc, "request_image", fake_request_image)

    refine_calls = {"n": 0}

    def fake_refine(self_, text):
        refine_calls["n"] += 1
        return f"CINEMATIC: {text}"

    from services.media.image_prompt_generator import ImagePromptGenerator
    monkeypatch.setattr(
        ImagePromptGenerator, "refine_to_cinematic_prompt", fake_refine, raising=True
    )

    from services.media.image_generator import ImageGenerator
    gen = ImageGenerator(provider="flowkit")
    await asyncio.to_thread(gen.generate, "raw scene", "f.png")
    assert refine_calls["n"] == 1
    assert captured["prompt"] == "CINEMATIC: raw scene"


@pytest.mark.asyncio
async def test_refiner_skipped_when_disabled(isolated_image_gen_env, monkeypatch):
    from config import ConfigManager
    monkeypatch.setattr(ConfigManager().pipeline, "flowkit_enabled", True)
    monkeypatch.setattr(ConfigManager().pipeline, "flowkit_use_refiner", False)

    import services.media.flow_service as fs_mod
    fs_mod.FlowService._instance = None
    svc = fs_mod.FlowService()
    svc.active_ws = MagicMock()
    svc._main_loop = asyncio.get_running_loop()

    captured: dict = {}

    async def fake_request_image(prompt, *a, **kw):
        captured["prompt"] = prompt
        return "/tmp/x.png"

    monkeypatch.setattr(svc, "request_image", fake_request_image)

    refine_calls = {"n": 0}

    def fake_refine(self_, text):
        refine_calls["n"] += 1
        return f"CINEMATIC: {text}"

    from services.media.image_prompt_generator import ImagePromptGenerator
    monkeypatch.setattr(
        ImagePromptGenerator, "refine_to_cinematic_prompt", fake_refine, raising=True
    )

    from services.media.image_generator import ImageGenerator
    gen = ImageGenerator(provider="flowkit")
    await asyncio.to_thread(gen.generate, "raw scene", "f.png")
    assert refine_calls["n"] == 0
    assert captured["prompt"] == "raw scene"


def test_refine_to_cinematic_prompt_returns_refined(monkeypatch):
    from services.media.image_prompt_generator import ImagePromptGenerator
    gen = ImagePromptGenerator()
    monkeypatch.setattr(
        gen.llm, "generate",
        MagicMock(return_value="wide shot, golden hour, hero, oil painting"),
        raising=False,
    )
    out = gen.refine_to_cinematic_prompt("hero stands on cliff")
    assert "golden hour" in out


def test_refine_to_cinematic_prompt_fallback_on_error(monkeypatch):
    from services.media.image_prompt_generator import ImagePromptGenerator
    gen = ImagePromptGenerator()
    monkeypatch.setattr(
        gen.llm, "generate",
        MagicMock(side_effect=RuntimeError("llm down")),
        raising=False,
    )
    out = gen.refine_to_cinematic_prompt("hero stands on cliff")
    assert out == "hero stands on cliff"


def test_refine_to_cinematic_prompt_rejects_refusal(monkeypatch):
    """A model refusal must be discarded so the base prompt is used (the real-world bug)."""
    from services.media.image_prompt_generator import ImagePromptGenerator
    gen = ImagePromptGenerator()
    monkeypatch.setattr(
        gen.llm, "generate",
        MagicMock(return_value=(
            "Bạn đã đăng nhập chưa? Tôi không thể tạo bất kỳ hình ảnh nào cho bạn."
        )),
        raising=False,
    )
    out = gen.refine_to_cinematic_prompt("hero stands on cliff")
    assert out == "hero stands on cliff"


def test_refine_to_cinematic_prompt_unwraps_json(monkeypatch):
    """A reply fenced as ```json {"prompt": ...}``` is unwrapped, not discarded."""
    from services.media.image_prompt_generator import ImagePromptGenerator
    gen = ImagePromptGenerator()
    monkeypatch.setattr(
        gen.llm, "generate",
        MagicMock(return_value=(
            '```json\n{"prompt": "low angle, neon rim light, lone hero, cyberpunk"}\n```'
        )),
        raising=False,
    )
    out = gen.refine_to_cinematic_prompt("hero stands on cliff")
    assert "neon rim light" in out


def test_is_configured_requires_ws(isolated_image_gen_env, monkeypatch):
    from config import ConfigManager
    monkeypatch.setattr(ConfigManager().pipeline, "image_provider", "flowkit")
    monkeypatch.setattr(ConfigManager().pipeline, "flowkit_enabled", True)

    import services.media.flow_service as fs_mod
    fs_mod.FlowService._instance = None
    svc = fs_mod.FlowService()
    svc.active_ws = None

    from services.media.image_provider import ImageProvider
    p = ImageProvider()
    assert p.is_configured() is False

    svc.active_ws = MagicMock()
    assert p.is_configured() is True


def test_flowkit_not_ready_returns_none(isolated_image_gen_env, monkeypatch):
    """No WS connected → _generate_flowkit returns None, no crash."""
    from config import ConfigManager
    monkeypatch.setattr(ConfigManager().pipeline, "flowkit_enabled", True)

    import services.media.flow_service as fs_mod
    fs_mod.FlowService._instance = None
    svc = fs_mod.FlowService()
    svc.active_ws = None

    from services.media.image_generator import ImageGenerator
    gen = ImageGenerator(provider="flowkit")
    assert gen.generate("scene", "f.png") is None


def test_handlers_relpath_subdirs(isolated_image_gen_env, monkeypatch):
    """services.handlers maps panel paths to OUTPUT_ROOT-relative /media names.

    Under the per-story layout panels live at ``output/<story-slug>/images/...``;
    handlers store the path relative to OUTPUT_ROOT so the ``/media`` mount
    (which serves OUTPUT_ROOT) resolves it as ``/media/<rel>``.
    """
    import services.handlers as handlers_mod

    # Build minimal fake objects to drive handle_generate_images.
    class _Ch:
        chapter_number = 1
        title = "ch1"
        content = "x"
        summary = ""
        images: list = []

    class _Story:
        chapters = [_Ch()]

    class _Output:
        enhanced_story = _Story()
        story_draft = type("D", (), {"title": "T", "characters": []})()

    class _Orch:
        session_id = "sid1"
        output = _Output()

    # Patch the heavy dependencies.
    monkeypatch.setattr(
        "services.media.image_prompt_generator.ImagePromptGenerator.generate_from_chapter",
        lambda self, *a, **kw: [MagicMock(panel_number=1)],
    )
    # Force the legacy scene-extraction path regardless of the local
    # comic_shot_list_enabled flag — the shot-list path calls the real LLM.
    from config import ConfigManager
    monkeypatch.setattr(
        ConfigManager().pipeline, "comic_shot_list_enabled", False, raising=False,
    )

    sub = "output/t_sid1/images"
    os.makedirs(sub, exist_ok=True)
    fake_path = os.path.join(sub, "ch01_panel01.png")

    monkeypatch.setattr(
        "services.media.image_generator.ImageGenerator.generate_story_images",
        lambda self, *a, **kw: [fake_path],
    )

    paths, msg = handlers_mod.handle_generate_images(_Orch(), provider="none")
    assert paths == [fake_path]
    # Chapter image entries keep the full OUTPUT_ROOT-relative path (story slug
    # + images subdir), not just the basename, so /media resolves it.
    assert _Orch.output.enhanced_story.chapters[0].images == ["t_sid1/images/ch01_panel01.png"]


# ---------------------------------------------------------------------------
# Phase 6 — config_routes risk-ack validator
# ---------------------------------------------------------------------------


@pytest.fixture
def config_app():
    from api.config_routes import router as config_router

    app = FastAPI()
    app.include_router(config_router, prefix="/api")
    return app


def test_config_patch_rejects_enable_without_ack(config_app, monkeypatch):
    """Enabling flowkit without prior risk acknowledgement must 400."""
    from config import ConfigManager

    cfg = ConfigManager()
    cfg.pipeline.flowkit_risk_acknowledged = False
    cfg.pipeline.flowkit_enabled = False
    cfg.pipeline.image_provider = "none"
    monkeypatch.setattr(cfg, "save", lambda: None)

    with TestClient(config_app) as client:
        resp = client.put(
            "/api/config",
            json={"image_provider": "flowkit", "flowkit_enabled": True},
        )
        assert resp.status_code == 400
        assert "flowkit_risk_acknowledged" in resp.json()["detail"]


def test_config_patch_accepts_enable_when_acked(config_app, monkeypatch):
    """Same PATCH succeeds when ack is in the body alongside the enable flag."""
    from config import ConfigManager

    cfg = ConfigManager()
    cfg.pipeline.flowkit_risk_acknowledged = False
    cfg.pipeline.flowkit_enabled = False
    cfg.pipeline.image_provider = "none"
    monkeypatch.setattr(cfg, "save", lambda: None)

    with TestClient(config_app) as client:
        resp = client.put(
            "/api/config",
            json={
                "image_provider": "flowkit",
                "flowkit_enabled": True,
                "flowkit_risk_acknowledged": True,
            },
        )
        assert resp.status_code == 200
        assert cfg.pipeline.flowkit_enabled is True
        assert cfg.pipeline.flowkit_risk_acknowledged is True
        assert cfg.pipeline.image_provider == "flowkit"


def test_config_patch_accepts_enable_when_previously_acked(config_app, monkeypatch):
    """Toggling enabled alone is fine if ack already on current state."""
    from config import ConfigManager

    cfg = ConfigManager()
    cfg.pipeline.flowkit_risk_acknowledged = True
    cfg.pipeline.flowkit_enabled = False
    cfg.pipeline.image_provider = "flowkit"
    monkeypatch.setattr(cfg, "save", lambda: None)

    with TestClient(config_app) as client:
        resp = client.put("/api/config", json={"flowkit_enabled": True})
        assert resp.status_code == 200
        assert cfg.pipeline.flowkit_enabled is True


def test_config_patch_persists_all_flowkit_fields(config_app, monkeypatch):
    """Every flowkit_* field in ConfigUpdate must round-trip into PipelineConfig."""
    from config import ConfigManager

    cfg = ConfigManager()
    cfg.pipeline.flowkit_risk_acknowledged = True  # pre-ack so gate passes
    monkeypatch.setattr(cfg, "save", lambda: None)

    body = {
        "flowkit_enabled": True,
        "flowkit_port": 9000,
        "flowkit_style_reference_path": "C:/refs/style.png",
        "flowkit_concurrent_workers_max": 7,
        "flowkit_workers_ramp_threshold": 25,
        "flowkit_veo_poll_interval": 12.5,
        "flowkit_account_warning_shown": True,
        "flowkit_risk_acknowledged": True,
        "flowkit_image_input_type_split": True,
        "flowkit_callback_hmac_required": True,
        "flowkit_use_refiner": False,
        "flowkit_request_timeout": 240.0,
    }
    with TestClient(config_app) as client:
        resp = client.put("/api/config", json=body)
        assert resp.status_code == 200

    for attr, expected in body.items():
        assert getattr(cfg.pipeline, attr) == expected, attr


def test_config_get_returns_all_flowkit_fields(config_app, monkeypatch):
    """GET /api/config must echo persisted flowkit_* so the UI can rehydrate."""
    from config import ConfigManager

    cfg = ConfigManager()
    cfg.pipeline.flowkit_enabled = True
    cfg.pipeline.flowkit_port = 9999
    cfg.pipeline.flowkit_risk_acknowledged = True
    cfg.pipeline.flowkit_request_timeout = 222.0

    with TestClient(config_app) as client:
        resp = client.get("/api/config")
        assert resp.status_code == 200
        pipeline = resp.json()["pipeline"]
        for key in (
            "flowkit_enabled", "flowkit_port", "flowkit_style_reference_path",
            "flowkit_concurrent_workers", "flowkit_concurrent_workers_max",
            "flowkit_workers_ramp_threshold", "flowkit_veo_poll_interval",
            "flowkit_account_warning_shown", "flowkit_risk_acknowledged",
            "flowkit_image_input_type_split", "flowkit_callback_hmac_required",
            "flowkit_use_refiner", "flowkit_request_timeout",
        ):
            assert key in pipeline, key
        assert pipeline["flowkit_enabled"] is True
        assert pipeline["flowkit_port"] == 9999
        assert pipeline["flowkit_request_timeout"] == 222.0
