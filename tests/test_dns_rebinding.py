"""DNS rebinding through the Next.js proxy, and Origin checks on writes.

The Next rewrite proxy (``changeOrigin: true``) rewrites ``Host`` to the API's
own address (``api:7860`` in Docker, ``localhost:7860`` in dev) and puts the
browser's real Host in ``X-Forwarded-Host``. A Host check that only looks at
``Host`` therefore waves through a rebound page on ``evil.example:3001``. The
forwarded host has to pass the same allow list.

A browser-sent ``Origin`` on an unsafe method is a second, independent check:
a foreign origin is rejected with 403 before CSRF or the route runs.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from middleware.hosts import allowed_hosts, origin_allowed

PROXY_HOST = "api:7860"


def _csrf(client: TestClient) -> TestClient:
    client.get("/api/health")
    client.headers["x-csrf-token"] = client.cookies.get("csrf_token")
    return client


@pytest.fixture
def fresh_client(monkeypatch):
    """Factory: a TestClient over an app built after env changes."""

    def make() -> TestClient:
        from app import create_app

        return TestClient(create_app())

    return make


# --- X-Forwarded-Host ---------------------------------------------------------


def test_reviewer_probe_rebound_forwarded_host_rejected(client):
    """The reviewer's probe: proxy Host, rebound browser host, rebound origin."""
    r = client.get(
        "/api/config",
        headers={
            "Host": PROXY_HOST,
            "X-Forwarded-Host": "evil.example:3001",
            "Origin": "http://evil.example:3001",
        },
    )
    assert r.status_code == 400
    assert r.text == "Invalid host header"


def test_forwarded_evil_host_rejected(client):
    r = client.get(
        "/api/health",
        headers={"Host": PROXY_HOST, "X-Forwarded-Host": "evil.example:3001"},
    )
    assert r.status_code == 400


@pytest.mark.parametrize(
    "forwarded", ["localhost:3001", "127.0.0.1:3001", "[::1]:3001", "localhost"]
)
def test_forwarded_loopback_hosts_pass(client, forwarded):
    r = client.get(
        "/api/health", headers={"Host": PROXY_HOST, "X-Forwarded-Host": forwarded}
    )
    assert r.status_code == 200


def test_forwarded_host_first_value_is_checked(client):
    r = client.get(
        "/api/health",
        headers={"Host": PROXY_HOST, "X-Forwarded-Host": "evil.example:3001, localhost:3001"},
    )
    assert r.status_code == 400
    r = client.get(
        "/api/health",
        headers={"Host": PROXY_HOST, "X-Forwarded-Host": " localhost:3001 ,evil.example"},
    )
    assert r.status_code == 200


def test_forwarded_lookalike_rejected(client):
    r = client.get(
        "/api/health",
        headers={"Host": PROXY_HOST, "X-Forwarded-Host": "localhost.evil.example:3001"},
    )
    assert r.status_code == 400


def test_lan_origin_host_trusted_via_forwarded_host(monkeypatch, fresh_client):
    """The LAN recipe sets only STORYFORGE_ALLOWED_ORIGINS; its host must be
    trusted as a forwarded host without also setting ALLOWED_HOSTS."""
    monkeypatch.setenv("STORYFORGE_ALLOWED_ORIGINS", "http://192.168.1.20:3001")
    c = fresh_client()
    r = c.get(
        "/api/health",
        headers={"Host": PROXY_HOST, "X-Forwarded-Host": "192.168.1.20:3001"},
    )
    assert r.status_code == 200
    r = c.get(
        "/api/health",
        headers={"Host": PROXY_HOST, "X-Forwarded-Host": "192.168.1.21:3001"},
    )
    assert r.status_code == 400


def test_allowed_hosts_include_origin_hosts(monkeypatch):
    monkeypatch.setenv("STORYFORGE_ALLOWED_HOSTS", "")
    monkeypatch.setenv(
        "STORYFORGE_ALLOWED_ORIGINS", "http://storyforge.lan:3001, https://[fd00::5]:3001"
    )
    hosts = allowed_hosts()
    assert "storyforge.lan" in hosts
    assert "[fd00::5]" in hosts


def test_websocket_forwarded_evil_host_rejected(client, monkeypatch):
    from starlette.websockets import WebSocketDisconnect

    from api import branch_websocket

    # A live session, so only the host check can refuse the upgrade.
    monkeypatch.setattr(
        branch_websocket.manager, "get_current_node", lambda _sid: {"id": "root"}
    )
    with client.websocket_connect(
        "/api/ws/branch/abc",
        headers={"Host": PROXY_HOST, "X-Forwarded-Host": "localhost:3001"},
    ):
        pass
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(
            "/api/ws/branch/abc",
            headers={"Host": PROXY_HOST, "X-Forwarded-Host": "evil.example:3001"},
        ):
            pass


# --- Origin on unsafe methods -------------------------------------------------


def test_post_with_foreign_origin_rejected(client):
    c = _csrf(client)
    r = c.post(
        "/api/session",
        json={"token": "x"},
        headers={"Host": PROXY_HOST, "Origin": "http://evil.example:3001"},
    )
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "origin_not_allowed"


@pytest.mark.parametrize("method", ["put", "patch", "delete"])
def test_other_unsafe_methods_with_foreign_origin_rejected(client, method):
    c = _csrf(client)
    r = getattr(c, method)(
        "/api/session", headers={"Origin": "http://evil.example:3001"}
    )
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "origin_not_allowed"


def test_post_without_origin_not_blocked_by_origin_check(client):
    c = _csrf(client)
    r = c.post("/api/session", json={"token": "x"}, headers={"Host": PROXY_HOST})
    assert r.status_code == 204


def test_post_with_allowed_origin_passes(client):
    c = _csrf(client)
    r = c.post(
        "/api/session",
        json={"token": "x"},
        headers={
            "Host": PROXY_HOST,
            "X-Forwarded-Host": "localhost:3001",
            "Origin": "http://localhost:3001",
        },
    )
    assert r.status_code == 204


def test_get_with_foreign_origin_not_blocked_by_origin_check(client):
    # Reads are left to CORS (the browser withholds the response).
    r = client.get("/api/health", headers={"Origin": "http://evil.example:3001"})
    assert r.status_code == 200


def test_post_with_configured_lan_origin_passes(monkeypatch, fresh_client):
    monkeypatch.setenv("STORYFORGE_ALLOWED_ORIGINS", "http://192.168.1.20:3001")
    c = _csrf(fresh_client())
    r = c.post(
        "/api/session",
        json={"token": "x"},
        headers={
            "Host": PROXY_HOST,
            "X-Forwarded-Host": "192.168.1.20:3001",
            "Origin": "http://192.168.1.20:3001",
        },
    )
    assert r.status_code == 204


# --- M1: STORYFORGE_ALLOWED_ORIGINS is additive ---------------------------------


def test_configured_origins_add_to_defaults(monkeypatch):
    from middleware.hosts import _DEFAULT_ORIGINS, _get_allowed_origins

    monkeypatch.setenv("STORYFORGE_ALLOWED_ORIGINS", "http://storyforge.lan:3001")
    origins = _get_allowed_origins()
    assert origins == _DEFAULT_ORIGINS + ["http://storyforge.lan:3001"]
    assert origin_allowed("http://localhost:3001") is True
    assert origin_allowed("http://storyforge.lan:3001") is True


def test_wildcard_origin_dropped_others_kept(monkeypatch):
    from middleware.hosts import _DEFAULT_ORIGINS, _get_allowed_origins

    monkeypatch.setenv("STORYFORGE_ALLOWED_ORIGINS", "*, http://storyforge.lan:3001")
    assert _get_allowed_origins() == _DEFAULT_ORIGINS + ["http://storyforge.lan:3001"]
