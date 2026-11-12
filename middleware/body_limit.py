"""Request body size limit (pure ASGI).

Rejects request bodies larger than ``max_bytes`` (10 MB by default):

- ``Content-Length`` above the limit → 413 before the app runs.
- ``Content-Length`` that is not a plain non-negative integer → 400 (it used
  to reach ``int()`` and surface as a 500).
- A chunked body (``Transfer-Encoding`` without ``Content-Length``) is read
  up front, at most ``max_bytes`` of it, and replayed to the app; going over
  the limit → 413. Reading it first matters: inner layers such as CSRF may
  answer without ever reading the body, and an oversized upload must still
  get 413, not whatever that layer says.
- Any other body is counted as the app reads it (``receive`` is wrapped).
  Once over the limit no more body is delivered — the app sees
  ``http.disconnect`` — and, if the app has not started a response yet, the
  client gets 413 and the app's own response is dropped.

Pure ASGI rather than ``BaseHTTPMiddleware`` so it can wrap ``receive``, and
so it adds no task/stream pair per request. It sits inside CORS, so its 413
and 400 responses carry CORS headers and the browser can read them.
"""

from __future__ import annotations

import logging
import re

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)

DEFAULT_MAX_BYTES = 10 * 1024 * 1024  # 10 MB

_DIGITS = re.compile(r"[0-9]+")


def _declared_length(headers: Headers) -> int | None:
    """The declared body length, or ``None`` when absent.

    Raises ``ValueError`` when malformed: non-numeric, negative, or
    conflicting duplicate headers."""
    values = headers.getlist("content-length")
    if not values:
        return None
    lengths = set()
    for value in values:
        value = value.strip()
        if not _DIGITS.fullmatch(value):
            raise ValueError(f"bad Content-Length {value!r}")
        lengths.add(int(value))
    if len(lengths) != 1:
        raise ValueError("conflicting Content-Length headers")
    return lengths.pop()


class BodySizeLimitMiddleware:
    """Enforce a maximum request body size; see the module docstring."""

    def __init__(self, app: ASGIApp, max_bytes: int = DEFAULT_MAX_BYTES) -> None:
        self.app = app
        self.max_bytes = max_bytes

    def _too_large(self) -> JSONResponse:
        mb = self.max_bytes / (1024 * 1024)
        return JSONResponse(
            status_code=413,
            content={"detail": f"Request body too large. Maximum size is {mb:g}MB."},
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        try:
            declared = _declared_length(headers)
        except ValueError:
            response = JSONResponse(
                status_code=400, content={"detail": "Invalid Content-Length header."}
            )
            await response(scope, receive, send)
            return
        if declared is not None and declared > self.max_bytes:
            await self._too_large()(scope, receive, send)
            return

        if declared is None and "transfer-encoding" in headers:
            buffered = await self._read_up_to_limit(receive)
            if buffered is None:
                await self._too_large()(scope, receive, send)
                return
            receive = _replay(buffered, receive)

        await self._call_counted(scope, receive, send)

    async def _read_up_to_limit(self, receive: Receive) -> list[Message] | None:
        """Read the whole body; ``None`` as soon as it passes the limit."""
        messages: list[Message] = []
        total = 0
        while True:
            message = await receive()
            messages.append(message)
            if message["type"] != "http.request":
                return messages  # disconnect: let the app see it
            total += len(message.get("body", b""))
            if total > self.max_bytes:
                return None
            if not message.get("more_body", False):
                return messages

    async def _call_counted(self, scope: Scope, receive: Receive, send: Send) -> None:
        received = 0
        over_limit = False  # stop delivering body
        responded = False  # we sent the 413; drop the app's response
        response_started = False

        async def counted_send(message: Message) -> None:
            nonlocal response_started
            if responded:
                return
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        async def counted_receive() -> Message:
            nonlocal received, over_limit, responded
            if over_limit:
                return {"type": "http.disconnect"}
            message = await receive()
            if message["type"] != "http.request":
                return message
            received += len(message.get("body", b""))
            if received <= self.max_bytes:
                return message
            over_limit = True
            if not response_started:
                responded = True
                await self._too_large()(scope, receive, send)
            return {"type": "http.disconnect"}

        try:
            await self.app(scope, counted_receive, counted_send)
        except Exception:
            # The app may fail on the disconnect we fed it; the client already
            # has its 413, so that failure is expected and not an error.
            if not responded:
                raise
            logger.debug("App raised after oversized body was rejected", exc_info=True)


def _replay(messages: list[Message], receive: Receive) -> Receive:
    """A ``receive`` that returns *messages* first, then defers to *receive*."""
    pending = list(messages)

    async def replay() -> Message:
        if pending:
            return pending.pop(0)
        return await receive()

    return replay
