"""Network exposure: loopback bind, startup guard, Host and Origin checks.

StoryForge is local-first: the API binds 127.0.0.1 unless told otherwise,
refuses to start on a non-loopback address without an access token (outside
a container), rejects requests whose Host header is not on the allow list
(DNS rebinding), and rejects WebSocket upgrades from foreign origins (CSWSH).
"""

from __future__ import annotations

import logging

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app import _DEFAULT_ORIGINS, check_exposure, resolve_bind
from middleware.hosts import (
    DEFAULT_ALLOWED_HOSTS,
    allowed_hosts,
    origin_allowed,
)
from services.security.url_validator import validate_base_url

_LOCAL = "localhost:7860"


# --- Host header -----------------------------------------------------------


@pytest.mark.parametrize(
    "host", ["localhost:7860", "127.0.0.1:7860", "api:7860", "[::1]:7860"]
)
def test_trusted_hosts_pass(client, host):
    assert client.get("/api/health", headers={"Host": host}).status_code == 200


@pytest.mark.parametrize("host", ["localhost", "host.docker.internal:7860", "[::1]"])
def test_trusted_hosts_without_port_or_docker_pass(client, host):
    assert client.get("/api/health", headers={"Host": host}).status_code == 200


def test_untrusted_host_rejected(client):
    resp = client.get("/api/health", headers={"Host": "evil.example"})
    assert resp.status_code == 400
    assert resp.text == "Invalid host header"


@pytest.mark.parametrize(
    "host", ["evil.example:7860", "localhost.evil.example", "[::2]:7860", "[::1"]
)
def test_lookalike_hosts_rejected(client, host):
    assert client.get("/api/health", headers={"Host": host}).status_code == 400


def test_allowed_hosts_defaults_and_env(monkeypatch):
    monkeypatch.delenv("STORYFORGE_ALLOWED_HOSTS", raising=False)
    assert DEFAULT_ALLOWED_HOSTS == [
        "localhost",
        "127.0.0.1",
        "[::1]",
        "::1",
        "api",
        "host.docker.internal",
    ]
    assert allowed_hosts() == DEFAULT_ALLOWED_HOSTS
    monkeypatch.setenv("STORYFORGE_ALLOWED_HOSTS", " storyforge.lan , 10.0.0.5 ,")
    assert allowed_hosts() == DEFAULT_ALLOWED_HOSTS + ["storyforge.lan", "10.0.0.5"]


def test_extra_host_from_env_is_trusted(monkeypatch):
    monkeypatch.setenv("STORYFORGE_ALLOWED_HOSTS", "storyforge.lan")
    from app import create_app

    c = TestClient(create_app())
    assert c.get("/api/health", headers={"Host": "storyforge.lan:7860"}).status_code == 200
    assert c.get("/api/health", headers={"Host": "evil.example"}).status_code == 400


def test_websocket_untrusted_host_rejected(client, branch_session):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(branch_session, headers={"Host": "evil.example"}):
            pass


# --- Bind and startup guard ------------------------------------------------


def test_resolve_bind_defaults_to_loopback(monkeypatch):
    monkeypatch.delenv("STORYFORGE_HOST", raising=False)
    monkeypatch.delenv("STORYFORGE_PORT", raising=False)
    assert resolve_bind() == ("127.0.0.1", 7860)


def test_resolve_bind_reads_env(monkeypatch):
    monkeypatch.setenv("STORYFORGE_HOST", "0.0.0.0")
    monkeypatch.setenv("STORYFORGE_PORT", "8000")
    assert resolve_bind() == ("0.0.0.0", 8000)


def test_check_exposure_refuses_lan_without_token():
    with pytest.raises(SystemExit) as exc:
        check_exposure("0.0.0.0", None, in_container=False)
    assert exc.value.code == 2


def test_check_exposure_allows_container_with_warning(caplog):
    with caplog.at_level(logging.WARNING):
        check_exposure("0.0.0.0", None, in_container=True)
    assert "STORYFORGE_ACCESS_TOKEN" in caplog.text


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1", "[::1]"])
def test_check_exposure_loopback_needs_no_token(host):
    check_exposure(host, None, in_container=False)


def test_check_exposure_lan_with_token_starts():
    check_exposure("0.0.0.0", "s3cret", in_container=False)


# --- Origin ----------------------------------------------------------------


def test_default_origins_cover_frontend_and_api():
    assert _DEFAULT_ORIGINS == [
        "http://localhost:3001",
        "http://127.0.0.1:3001",
        "http://localhost:7860",
        "http://127.0.0.1:7860",
    ]


def test_origin_allowed(monkeypatch):
    monkeypatch.delenv("STORYFORGE_ALLOWED_ORIGINS", raising=False)
    assert origin_allowed(None) is True
    assert origin_allowed("http://localhost:3001") is True
    assert origin_allowed("https://evil.example") is False


@pytest.fixture
def branch_session(monkeypatch):
    """Make /api/ws/branch/abc a live session so only the origin decides."""
    from api import branch_websocket

    monkeypatch.setattr(
        branch_websocket.manager, "get_current_node", lambda _sid: {"id": "root"}
    )
    return "/api/ws/branch/abc"


def test_branch_ws_rejects_foreign_origin(client):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(
            "/api/ws/branch/x", headers={"Origin": "https://evil.example"}
        ):
            pass


def test_branch_ws_foreign_origin_closes_1008(client, branch_session):
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(
            branch_session, headers={"Host": _LOCAL, "Origin": "https://evil.example"},
        ):
            pass
    assert exc.value.code == 1008


def test_branch_ws_allows_frontend_origin(client, branch_session):
    with client.websocket_connect(
        branch_session, headers={"Host": _LOCAL, "Origin": "http://localhost:3001"}
    ) as ws:
        assert ws.receive_json()["type"] == "sync"


def test_branch_ws_allows_no_origin(client, branch_session):
    with client.websocket_connect(branch_session, headers={"Host": _LOCAL}) as ws:
        assert ws.receive_json()["type"] == "sync"


# --- SSRF exception and Ollama preset --------------------------------------


def test_host_docker_internal_allowed_but_other_private_blocked(monkeypatch):
    monkeypatch.delenv("STORYFORGE_ALLOW_PRIVATE_BASE_URL", raising=False)
    validate_base_url("http://host.docker.internal:11434/v1")  # no raise
    with pytest.raises(HTTPException):
        validate_base_url("http://192.168.1.10/v1")


def test_host_docker_internal_is_not_dns_resolved(monkeypatch):
    """The exception is by exact name, before resolution: in Docker it
    resolves to a private gateway address, which would otherwise be blocked."""
    import services.security.url_validator as uv

    monkeypatch.delenv("STORYFORGE_ALLOW_PRIVATE_BASE_URL", raising=False)

    def _boom(host):
        raise AssertionError(f"resolved {host}")

    monkeypatch.setattr(uv, "_resolved_addresses", _boom)
    validate_base_url("http://host.docker.internal:11434/v1")
    validate_base_url("http://HOST.DOCKER.INTERNAL:11434/v1")


def test_host_docker_internal_lookalike_still_checked(monkeypatch):
    import ipaddress

    import services.security.url_validator as uv

    monkeypatch.delenv("STORYFORGE_ALLOW_PRIVATE_BASE_URL", raising=False)
    monkeypatch.setattr(
        uv, "_resolved_addresses", lambda _h: [ipaddress.ip_address("172.17.0.1")]
    )
    with pytest.raises(HTTPException):
        validate_base_url("http://host.docker.internal.evil.example/v1")


def _ollama(client):
    presets = client.get(
        "/api/config/provider-presets", headers={"Host": _LOCAL}
    ).json()["presets"]
    return next(p for p in presets if p["name"] == "Ollama")


def test_ollama_preset_uses_localhost_outside_container(client, monkeypatch):
    monkeypatch.delenv("STORYFORGE_IN_CONTAINER", raising=False)
    assert _ollama(client)["base_url"] == "http://localhost:11434/v1"


def test_ollama_preset_uses_host_docker_internal_in_container(client, monkeypatch):
    monkeypatch.setenv("STORYFORGE_IN_CONTAINER", "1")
    assert _ollama(client)["base_url"] == "http://host.docker.internal:11434/v1"
