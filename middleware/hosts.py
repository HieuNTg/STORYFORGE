"""Host header and Origin allow lists.

StoryForge binds to loopback, but a loopback bind alone does not stop DNS
rebinding: a page on ``evil.example`` can re-point its own name at 127.0.0.1
and then talk to the API with ``Host: evil.example``. Rejecting unknown Host
headers closes that. Browsers cannot forge the Host header, so an allow list
of the names StoryForge is really reached by is enough:

- ``localhost`` / ``127.0.0.1`` / ``[::1]`` — the host machine,
- ``api`` — the compose service name the Next.js proxy uses,
- ``host.docker.internal`` — a container on the same machine.

``STORYFORGE_ALLOWED_HOSTS`` (comma-separated) adds more, e.g. a LAN name.

Starlette's ``TrustedHostMiddleware`` is not used: it splits the Host header
on the first ``:``, which turns ``[::1]:7860`` into ``[`` and rejects IPv6
loopback. ``TrustedHostsMiddleware`` below parses bracketed IPv6 properly and
also covers WebSocket handshakes.

The Origin side (``origin_allowed``) is for WebSocket upgrades, which CORS
does not cover: any page may open a WebSocket to any host, so the handler has
to check ``Origin`` itself before accepting (cross-site WebSocket hijacking).
"""

from __future__ import annotations

import logging
import os

from starlette.datastructures import Headers
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)

DEFAULT_ALLOWED_HOSTS = [
    "localhost",
    "127.0.0.1",
    "[::1]",
    "::1",
    "api",
    "host.docker.internal",
]

# Frontend (host port 3001) and the API itself (7860), by name and by IP.
_DEFAULT_ORIGINS = [
    "http://localhost:3001",
    "http://127.0.0.1:3001",
    "http://localhost:7860",
    "http://127.0.0.1:7860",
]


def allowed_hosts() -> list[str]:
    """Default hosts plus any listed in ``STORYFORGE_ALLOWED_HOSTS``."""
    raw = os.environ.get("STORYFORGE_ALLOWED_HOSTS", "")
    extra = [h.strip() for h in raw.split(",") if h.strip()]
    return DEFAULT_ALLOWED_HOSTS + [h for h in extra if h not in DEFAULT_ALLOWED_HOSTS]


def _get_allowed_origins() -> list[str]:
    """Read allowed CORS origins from STORYFORGE_ALLOWED_ORIGINS env var.

    Falls back to the local frontend/API defaults. Rejects wildcard '*' with a
    warning — credentials are allowed, which the CORS spec forbids with '*'.

        export STORYFORGE_ALLOWED_ORIGINS="http://storyforge.lan:3001"
    """
    raw = os.environ.get("STORYFORGE_ALLOWED_ORIGINS", "")
    if raw.strip():
        origins = [o.strip() for o in raw.split(",") if o.strip()]
        if "*" in origins:
            logger.warning(
                "STORYFORGE_ALLOWED_ORIGINS contains '*' — ignoring and using "
                "safe defaults instead. Set explicit origins."
            )
            return _DEFAULT_ORIGINS
        return origins
    return _DEFAULT_ORIGINS


def _normalize_origin(origin: str) -> str:
    return origin.strip().rstrip("/").lower()


def origin_allowed(origin: str | None) -> bool:
    """True when *origin* is in the CORS allow list.

    ``None`` (no Origin header) is allowed: browsers always send Origin on a
    WebSocket handshake, so its absence means a non-browser client, which
    cannot be the victim of a cross-site attack.
    """
    if origin is None:
        return True
    wanted = _normalize_origin(origin)
    return any(_normalize_origin(o) == wanted for o in _get_allowed_origins())


def _host_candidates(header: str) -> set[str]:
    """Names to match for a Host header value, port stripped.

    ``[::1]:7860`` → {"[::1]", "::1"}; ``localhost:7860`` → {"localhost"}.
    A malformed value yields an empty set (never matches).
    """
    value = header.strip().lower()
    if not value:
        return set()
    if value.startswith("["):
        end = value.find("]")
        if end == -1:
            return set()
        rest = value[end + 1 :]
        if rest and not (rest.startswith(":") and rest[1:].isdigit()):
            return set()
        bracketed = value[: end + 1]
        return {bracketed, bracketed[1:-1]}
    if value.count(":") == 1:
        name, _, port = value.partition(":")
        if not port.isdigit():
            return set()
        return {name}
    # No port, or a bare (unbracketed) IPv6 literal.
    return {value}


class TrustedHostsMiddleware:
    """Reject HTTP requests and WebSocket handshakes with an unknown Host.

    The allow list is read once, at construction (``allowed_hosts()``).
    HTTP gets ``400 Invalid host header``; a WebSocket is closed before
    accept, which the server answers with 403.
    """

    def __init__(self, app: ASGIApp, hosts: list[str] | None = None) -> None:
        self.app = app
        self.hosts = {h.strip().lower() for h in (hosts or allowed_hosts())}

    def is_trusted(self, header: str) -> bool:
        return bool(_host_candidates(header) & self.hosts)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        host = Headers(scope=scope).get("host", "")
        if self.is_trusted(host):
            await self.app(scope, receive, send)
            return
        logger.warning("Rejected request with untrusted Host header %r", host)
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        response = PlainTextResponse("Invalid host header", status_code=400)
        await response(scope, receive, send)
