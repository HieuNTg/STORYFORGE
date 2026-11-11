"""Optional shared access token.

StoryForge is a single-user app that runs on the user's own machine, so by
default every route is open. Setting ``STORYFORGE_ACCESS_TOKEN`` (for example
when exposing the app to a LAN) closes the API: a request then needs either

- ``Authorization: Bearer <token>``, or
- the ``sf_session`` cookie that ``POST /api/session`` issues for the token.

The cookie is what makes browser-native requests work — ``<img src=/media/…>``,
EventSource/SSE and WebSocket upgrades cannot set an ``Authorization`` header.
Its value is an HMAC of a fixed label keyed by the token, so the token itself
never sits in the cookie jar, and rotating the token invalidates every session.

Two enforcement points share one check:

- ``require_access`` — a FastAPI dependency attached at ``APIRouter`` level on
  every API router. Routes listed in ``TOKEN_EXEMPT`` pass through it.
- ``AccessMiddleware`` — covers what routers cannot: the ``/media`` static
  mount and WebSocket upgrades.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import HTTPConnection
from starlette.responses import JSONResponse
from starlette.types import Receive, Scope, Send

ACCESS_TOKEN_ENV = "STORYFORGE_ACCESS_TOKEN"
SESSION_COOKIE = "sf_session"

# (method, path-regex) pairs that stay open in token mode. Health for probes,
# the session endpoints so the browser can learn about and unlock the gate,
# and the read side of public shares. Regexes are matched in full.
TOKEN_EXEMPT: tuple[tuple[str, str], ...] = (
    ("GET", r"/api/health"),
    ("GET", r"/api/session"),
    ("POST", r"/api/session"),
    ("GET", r"/api/share/gallery"),
    ("GET", r"/api/share/[^/]+"),
)

_EXEMPT_COMPILED = tuple((m, re.compile(rx)) for m, rx in TOKEN_EXEMPT)
_SESSION_LABEL = b"storyforge-session-v1"
_DENIED = {"code": "access_token_required"}


def access_token() -> str | None:
    """The configured token, or None when access is open. Read per call so
    tests and restarts pick up changes without re-importing."""
    token = os.environ.get(ACCESS_TOKEN_ENV, "").strip()
    return token or None


def issue_session(token: str) -> str:
    """Session cookie value for *token*: hex HMAC-SHA256 of a fixed label."""
    return hmac.new(token.encode("utf-8"), _SESSION_LABEL, hashlib.sha256).hexdigest()


def is_exempt(method: str, path: str) -> bool:
    """True when (method, path) is in TOKEN_EXEMPT. HEAD counts as GET."""
    method = "GET" if method == "HEAD" else method
    return any(m == method and rx.fullmatch(path) for m, rx in _EXEMPT_COMPILED)


def has_access(conn: HTTPConnection, token: str) -> bool:
    """True when *conn* carries the bearer token or a valid session cookie."""
    scheme, _, credential = conn.headers.get("authorization", "").partition(" ")
    if scheme.lower() == "bearer" and credential:
        if hmac.compare_digest(credential.strip().encode(), token.encode()):
            return True
    cookie = conn.cookies.get(SESSION_COOKIE, "")
    if cookie and hmac.compare_digest(cookie.encode(), issue_session(token).encode()):
        return True
    return False


async def require_access(request: Request) -> None:
    """Router-level dependency: no-op without a token, else 401 unless the
    request is exempt or carries the token / session cookie."""
    token = access_token()
    if token is None:
        return
    if is_exempt(request.method, request.url.path):
        return
    if not has_access(request, token):
        raise HTTPException(status_code=401, detail=_DENIED)


class AccessMiddleware(BaseHTTPMiddleware):
    """Applies the access check to ``/media/*`` and to WebSocket upgrades.

    API routes are guarded by ``require_access`` on their routers; static
    mounts and WebSocket handshakes never reach those dependencies.
    """

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "websocket":
            token = access_token()
            if token is not None and not has_access(HTTPConnection(scope), token):
                # Close before accept: the server answers the handshake with
                # 403 and the client sees close code 1008 (policy violation).
                await send({"type": "websocket.close", "code": 1008})
                return
            await self.app(scope, receive, send)
            return
        await super().__call__(scope, receive, send)

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path == "/media" or path.startswith("/media/"):
            token = access_token()
            if token is not None and not has_access(request, token):
                return JSONResponse(status_code=401, content={"detail": _DENIED})
        return await call_next(request)
