"""Host header and Origin allow lists.

StoryForge binds to loopback, but a loopback bind alone does not stop DNS
rebinding: a page on ``evil.example`` can re-point its own name at 127.0.0.1
and then talk to the API with ``Host: evil.example``. Rejecting unknown Host
headers closes that. Browsers cannot forge the Host header, so an allow list
of the names StoryForge is really reached by is enough:

- ``localhost`` / ``127.0.0.1`` / ``[::1]`` — the host machine,
- ``api`` — the compose service name the Next.js proxy uses,
- ``host.docker.internal`` — a container on the same machine.

``STORYFORGE_ALLOWED_HOSTS`` (comma-separated) adds more, e.g. a LAN name, and
the host of every ``STORYFORGE_ALLOWED_ORIGINS`` entry is trusted too, so the
LAN recipe needs only the origin.

Behind the Next.js proxy the API never sees the browser's Host: the rewrite
proxy runs with ``changeOrigin`` and sends ``Host: api:7860`` (Docker) or
``localhost:7860`` (dev). The browser's Host arrives in ``X-Forwarded-Host``,
which Next sets from the incoming Host header and overwrites any value the
client sent (``next/dist/server/lib/router-utils/proxy-request.js`` passes it
in the proxy's ``headers`` option, applied after the incoming headers are
copied). So when ``X-Forwarded-Host`` is present, its first value must pass
the same allow list; otherwise a rebound page on ``evil.example:3001`` would
reach the API through the web port.

Starlette's ``TrustedHostMiddleware`` is not used: it splits the Host header
on the first ``:``, which turns ``[::1]:7860`` into ``[`` and rejects IPv6
loopback. ``TrustedHostsMiddleware`` below parses bracketed IPv6 properly and
also covers WebSocket handshakes.

The Origin side (``origin_allowed``) covers what CORS does not:

- WebSocket upgrades: any page may open a WebSocket to any host, so the
  handler checks ``Origin`` itself before accepting (cross-site WebSocket
  hijacking);
- unsafe methods (POST/PUT/PATCH/DELETE): ``TrustedHostsMiddleware`` answers
  403 when a browser-sent ``Origin`` is not on the list. CORS only hides the
  response from a foreign page; the write would already have happened.
  Requests without ``Origin`` (curl, scripts) are left to the CSRF check.
"""

from __future__ import annotations

import logging
import os

from starlette.datastructures import Headers
from starlette.responses import JSONResponse, PlainTextResponse
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


_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def allowed_hosts() -> list[str]:
    """Default hosts, plus ``STORYFORGE_ALLOWED_HOSTS``, plus the host of each
    allowed origin (``STORYFORGE_ALLOWED_ORIGINS``)."""
    raw = os.environ.get("STORYFORGE_ALLOWED_HOSTS", "")
    extra = [h.strip() for h in raw.split(",") if h.strip()]
    extra += [h for h in (_origin_host(o) for o in _get_allowed_origins()) if h]
    hosts = list(DEFAULT_ALLOWED_HOSTS)
    for h in extra:
        if h not in hosts:
            hosts.append(h)
    return hosts


def _origin_host(origin: str) -> str | None:
    """Host part of an origin, lower-cased, port stripped; IPv6 stays bracketed.

    ``http://storyforge.lan:3001`` -> ``storyforge.lan``;
    ``https://[fd00::5]:3001`` -> ``[fd00::5]``. None when unparseable.
    """
    _, sep, rest = origin.strip().partition("://")
    if not sep:
        return None
    names = _host_candidates(rest.split("/", 1)[0])
    if not names:
        return None
    bracketed = [n for n in names if n.startswith("[")]
    return bracketed[0] if bracketed else next(iter(names))


def _get_allowed_origins() -> list[str]:
    """Allowed CORS origins: the local frontend/API defaults plus any listed in
    ``STORYFORGE_ALLOWED_ORIGINS`` (comma-separated, additive).

    A wildcard ``*`` entry is dropped with a warning — credentials are allowed,
    which the CORS spec forbids with ``*``.

        export STORYFORGE_ALLOWED_ORIGINS="http://storyforge.lan:3001"
    """
    raw = os.environ.get("STORYFORGE_ALLOWED_ORIGINS", "")
    configured = [o.strip() for o in raw.split(",") if o.strip()]
    if "*" in configured:
        logger.warning(
            "STORYFORGE_ALLOWED_ORIGINS contains '*' — ignoring it. Set explicit origins."
        )
    origins = list(_DEFAULT_ORIGINS)
    for o in configured:
        if o != "*" and o not in origins:
            origins.append(o)
    return origins


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


def _first_forwarded(value: str) -> str:
    """First entry of a comma-separated ``X-Forwarded-Host`` value."""
    return value.split(",", 1)[0].strip()


class TrustedHostsMiddleware:
    """Reject requests with an unknown Host / X-Forwarded-Host or, on unsafe
    methods, a foreign Origin.

    - ``Host`` must be on the allow list (read once, at construction, from
      ``allowed_hosts()``).
    - ``X-Forwarded-Host``, when present and non-empty, is the browser's Host
      as seen by the Next proxy; its first value must pass the same check.
    - POST/PUT/PATCH/DELETE carrying an ``Origin`` that ``origin_allowed()``
      rejects get ``403`` with ``{"detail": {"code": "origin_not_allowed"}}``.

    A bad host gets ``400 Invalid host header``; a WebSocket is closed before
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
        headers = Headers(scope=scope)
        host = headers.get("host", "")
        forwarded = _first_forwarded(headers.get("x-forwarded-host", ""))
        bad = None
        if not self.is_trusted(host):
            bad = ("Host", host)
        elif forwarded and not self.is_trusted(forwarded):
            bad = ("X-Forwarded-Host", forwarded)
        if bad is not None:
            logger.warning("Rejected request with untrusted %s header %r", *bad)
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 1008})
                return
            response = PlainTextResponse("Invalid host header", status_code=400)
            await response(scope, receive, send)
            return
        if scope["type"] == "http" and scope.get("method") in _UNSAFE_METHODS:
            origin = headers.get("origin")
            if not origin_allowed(origin):
                logger.warning("Rejected %s with foreign Origin %r", scope["method"], origin)
                response = JSONResponse(
                    status_code=403, content={"detail": {"code": "origin_not_allowed"}}
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)
