"""Optional shared access token (STORYFORGE_ACCESS_TOKEN).

Unset: everything is open (single user on their own machine). Set: every API
route, /media/* and WebSocket upgrades need ``Authorization: Bearer <token>``
or the ``sf_session`` cookie issued by ``POST /api/session`` — the cookie is
what lets browser-native requests (<img src=/media/...>, EventSource, WS) in.
"""

from __future__ import annotations

import re

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

TOKEN = "s3cret"


def _with_csrf(client: TestClient) -> TestClient:
    """Prime the double-submit CSRF cookie and echo it on every request,
    the way the frontend's apiFetch does."""
    client.get("/api/health")
    client.headers["x-csrf-token"] = client.cookies.get("csrf_token")
    return client


@pytest.fixture
def media_root(tmp_path, monkeypatch):
    import services.output_paths as output_paths

    root = tmp_path / "output"
    root.mkdir()
    monkeypatch.setattr(output_paths, "OUTPUT_ROOT", str(root))
    return root


@pytest.fixture
def sample_media_file(media_root):
    img = media_root / "some-story" / "images"
    img.mkdir(parents=True)
    (img / "cover.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")
    return "some-story/images/cover.png"


@pytest.fixture
def client_with_token(monkeypatch, media_root):
    monkeypatch.setenv("STORYFORGE_ACCESS_TOKEN", TOKEN)
    from app import create_app

    return _with_csrf(TestClient(create_app()))


@pytest.fixture
def open_client(monkeypatch, media_root):
    monkeypatch.delenv("STORYFORGE_ACCESS_TOKEN", raising=False)
    from app import create_app

    return _with_csrf(TestClient(create_app()))


# --- brief tests -------------------------------------------------------------


def test_no_token_configured_everything_open(client):
    assert client.get("/api/config").status_code == 200


def test_token_required_on_api(client_with_token):
    r = client_with_token.get("/api/config")
    assert r.status_code == 401 and r.json()["detail"]["code"] == "access_token_required"


def test_bearer_token_accepted(client_with_token):
    r = client_with_token.get("/api/config", headers={"Authorization": f"Bearer {TOKEN}"})
    assert r.status_code == 200


def test_session_cookie_unlocks_media_and_sse(client_with_token, sample_media_file):
    assert client_with_token.post("/api/session", json={"token": TOKEN}).status_code == 204
    assert client_with_token.get(f"/media/{sample_media_file}").status_code == 200
    assert client_with_token.get("/api/config").status_code == 200


def test_wrong_token_rejected(client_with_token):
    r = client_with_token.post("/api/session", json={"token": "nope"})
    assert r.status_code == 401
    assert "sf_session" not in r.cookies


def test_exempt_routes_open_in_token_mode(client_with_token):
    for path in ("/api/health", "/api/session", "/api/share/gallery"):
        assert client_with_token.get(path).status_code != 401, path


def test_auth_routes_removed(client):
    _with_csrf(client)  # else CSRF answers 403 before routing
    assert client.post("/api/auth/register", json={}).status_code == 404
    assert client.post("/api/auth/login", json={}).status_code == 404
    assert client.get("/api/auth/me").status_code == 404


def test_every_api_route_has_require_access():
    from app import create_app
    from middleware.access import TOKEN_EXEMPT, require_access

    def _calls(dependant) -> set:
        found = {dependant.call}
        for sub in dependant.dependencies:
            found |= _calls(sub)
        return found

    def _exempt(route: APIRoute) -> bool:
        return all(
            any(m == method and re.fullmatch(rx, route.path) for m, rx in TOKEN_EXEMPT)
            for method in route.methods - {"HEAD"}
        )

    app = create_app()
    unguarded = [
        f"{sorted(r.methods)} {r.path}"
        for r in app.routes
        if isinstance(r, APIRoute)
        and r.path.startswith("/api")
        and not _exempt(r)
        and require_access not in _calls(r.dependant)
    ]
    assert unguarded == []


# --- the rest of the contract -----------------------------------------------


def test_media_needs_token(client_with_token, sample_media_file):
    r = client_with_token.get(f"/media/{sample_media_file}")
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "access_token_required"
    ok = client_with_token.get(
        f"/media/{sample_media_file}", headers={"Authorization": f"Bearer {TOKEN}"}
    )
    assert ok.status_code == 200


def test_media_open_without_token(open_client, sample_media_file):
    assert open_client.get(f"/media/{sample_media_file}").status_code == 200


def test_run_recovery_route_needs_token_then_cookie_unlocks(client_with_token):
    """Browser-side stream/recovery fetches carry the cookie, not a header."""
    path = "/api/pipeline/run/does-not-exist"
    assert client_with_token.get(path).status_code == 401
    client_with_token.post("/api/session", json={"token": TOKEN})
    assert client_with_token.get(path).status_code != 401


def test_session_cookie_attributes(client_with_token):
    r = client_with_token.post("/api/session", json={"token": TOKEN})
    set_cookie = r.headers["set-cookie"].lower()
    assert "sf_session=" in set_cookie
    assert "httponly" in set_cookie
    assert "samesite=strict" in set_cookie
    assert "secure" not in set_cookie  # plain http in tests
    from middleware.access import issue_session

    assert client_with_token.cookies.get("sf_session") == issue_session(TOKEN)
    assert TOKEN not in client_with_token.cookies.get("sf_session")


def test_session_cookie_secure_behind_https(client_with_token):
    r = client_with_token.post(
        "/api/session", json={"token": TOKEN}, headers={"x-forwarded-proto": "https"}
    )
    assert "secure" in r.headers["set-cookie"].lower()


def test_get_session_open_mode(open_client):
    assert open_client.get("/api/session").json() == {"required": False, "valid": True}


def test_get_session_reports_state(client_with_token):
    assert client_with_token.get("/api/session").json() == {"required": True, "valid": False}
    bearer = {"Authorization": f"Bearer {TOKEN}"}
    assert client_with_token.get("/api/session", headers=bearer).json()["valid"] is True
    client_with_token.post("/api/session", json={"token": TOKEN})
    assert client_with_token.get("/api/session").json() == {"required": True, "valid": True}


def test_delete_session_clears_cookie(client_with_token):
    client_with_token.post("/api/session", json={"token": TOKEN})
    r = client_with_token.delete("/api/session")
    assert r.status_code == 204
    assert "sf_session" not in client_with_token.cookies
    assert client_with_token.get("/api/config").status_code == 401


def test_forged_cookie_rejected(client_with_token):
    client_with_token.cookies.set("sf_session", TOKEN)
    assert client_with_token.get("/api/config").status_code == 401


def test_session_from_old_token_rejected_after_rotation(client_with_token, monkeypatch):
    client_with_token.post("/api/session", json={"token": TOKEN})
    monkeypatch.setenv("STORYFORGE_ACCESS_TOKEN", "rotated")
    assert client_with_token.get("/api/config").status_code == 401


def test_session_post_stays_csrf_protected(client_with_token):
    client_with_token.headers.pop("x-csrf-token")
    assert client_with_token.post("/api/session", json={"token": TOKEN}).status_code == 403


def test_share_view_exempt_but_share_writes_guarded(client_with_token):
    assert client_with_token.get("/api/share/0123456789ab").status_code != 401
    assert client_with_token.delete("/api/share/0123456789ab").status_code == 401
    assert client_with_token.post("/api/share/create", json={}).status_code == 401


def test_deep_health_is_not_exempt(client_with_token):
    assert client_with_token.get("/api/health/deep").status_code == 401


@pytest.fixture
def branch_session(monkeypatch):
    """Make /api/ws/branch/abc a live session so only access decides."""
    from api import branch_websocket

    monkeypatch.setattr(
        branch_websocket.manager, "get_current_node", lambda _sid: {"id": "root"}
    )
    return "/api/ws/branch/abc"


def test_websocket_needs_token(client_with_token, branch_session):
    with pytest.raises(WebSocketDisconnect) as exc:
        with client_with_token.websocket_connect(branch_session):
            pass
    assert exc.value.code == 1008


def test_websocket_accepts_session_cookie(client_with_token, branch_session):
    client_with_token.post("/api/session", json={"token": TOKEN})
    with client_with_token.websocket_connect(branch_session) as ws:
        assert ws.receive_json()["type"] == "sync"


def test_websocket_accepts_bearer(client_with_token, branch_session):
    with client_with_token.websocket_connect(
        branch_session, headers={"Authorization": f"Bearer {TOKEN}"}
    ) as ws:
        assert ws.receive_json()["type"] == "sync"


def test_websocket_open_without_token(open_client, branch_session):
    with open_client.websocket_connect(branch_session) as ws:
        assert ws.receive_json()["type"] == "sync"


def test_require_access_is_noop_without_token(monkeypatch):
    import asyncio

    from starlette.requests import Request

    from middleware.access import access_token, require_access

    monkeypatch.setenv("STORYFORGE_ACCESS_TOKEN", "   ")
    assert access_token() is None
    req = Request({"type": "http", "method": "GET", "path": "/api/config", "headers": []})
    assert asyncio.run(require_access(req)) is None


def test_issue_session_is_hmac_of_token():
    import hashlib
    import hmac

    from middleware.access import issue_session

    sig = issue_session(TOKEN)
    assert re.fullmatch(r"[0-9a-f]{64}", sig)
    assert sig != issue_session("other")
    assert sig == issue_session(TOKEN)
    # keyed by the token: same label, different key, different digest
    assert hmac.compare_digest(sig, issue_session(TOKEN))
    assert sig != hashlib.sha256(TOKEN.encode()).hexdigest()


def test_post_session_open_mode_sets_no_cookie(open_client):
    r = open_client.post("/api/session", json={"token": "anything"})
    assert r.status_code == 204
    assert "sf_session" not in r.cookies
