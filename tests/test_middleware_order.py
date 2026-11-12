"""Middleware order, request body limit, CSP and API-docs gating.

The order matters for what a rejected request still carries: a 413 from the
body limit must have CORS headers (so the browser can read it), and a 429
from the rate limiter must have the trace ID (so it can be matched to logs).
"""

from __future__ import annotations

import asyncio
import logging

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

ORIGIN = "http://localhost:3001"
TEN_MB = 10 * 1024 * 1024

EXPECTED_ORDER = [
    "TrustedHostsMiddleware",
    "TraceIDMiddleware",
    "CORSMiddleware",
    "BodySizeLimitMiddleware",
    "SecurityHeadersMiddleware",
    "CSRFMiddleware",
    "AccessMiddleware",
    "RateLimitMiddleware",
    "SanitizationMiddleware",
    "AuditMiddleware",
    "MetricsMiddleware",
    "GZipMiddleware",
]


def test_effective_middleware_order():
    from app import create_app

    app = create_app()
    # Starlette inserts each add_middleware() at index 0: user_middleware is
    # listed outermost first.
    names = [m.cls.__name__ for m in app.user_middleware]
    assert names == EXPECTED_ORDER


def test_body_limit_is_pure_asgi():
    from starlette.middleware.base import BaseHTTPMiddleware

    from middleware.body_limit import BodySizeLimitMiddleware

    assert not issubclass(BodySizeLimitMiddleware, BaseHTTPMiddleware)


# --- body limit through the full app ----------------------------------------


def test_413_has_cors_header(client):
    r = client.post(
        "/api/pipeline/run",
        content=b"x" * (TEN_MB + 1),
        headers={"Origin": ORIGIN, "Content-Type": "application/json"},
    )
    assert r.status_code == 413
    assert r.headers["access-control-allow-origin"] == ORIGIN


def test_chunked_oversize_rejected(client):
    def gen():
        for _ in range(11):
            yield b"x" * (1024 * 1024)

    r = client.post("/api/pipeline/run", content=gen(), headers={"Origin": ORIGIN})
    assert r.status_code == 413
    assert r.headers["access-control-allow-origin"] == ORIGIN


def test_bad_content_length_is_400(client):
    r = client.post(
        "/api/pipeline/run", content=b"{}", headers={"Content-Length": "abc"}
    )
    assert r.status_code == 400


def test_body_within_limit_passes_body_limit(client):
    # Reaches CSRF (no token) instead of being stopped by the body limit.
    r = client.post("/api/pipeline/run", content=b"{}")
    assert r.status_code == 403


def test_chunked_body_within_limit_is_delivered_intact():
    from middleware.body_limit import BodySizeLimitMiddleware

    app = FastAPI()

    @app.post("/echo")
    async def echo(request: Request):
        return {"size": len(await request.body())}

    app.add_middleware(BodySizeLimitMiddleware, max_bytes=1000)

    def gen():
        for _ in range(9):
            yield b"y" * 100

    r = TestClient(app).post("/echo", content=gen())
    assert r.status_code == 200 and r.json() == {"size": 900}


# --- body limit, unit level (ASGI messages) ---------------------------------


async def _run(mw, headers, chunks):
    """Drive *mw* with an HTTP scope; return the messages it sent."""
    pending = list(chunks)

    async def receive():
        if pending:
            body = pending.pop(0)
            return {"type": "http.request", "body": body, "more_body": bool(pending)}
        await asyncio.sleep(3600)  # client idle until disconnect

    sent: list[dict] = []

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/x",
        "headers": [(k.encode(), v.encode()) for k, v in headers],
    }
    await mw(scope, receive, send)
    return sent


def _status(sent):
    starts = [m for m in sent if m["type"] == "http.response.start"]
    assert len(starts) == 1, sent
    return starts[0]["status"]


def test_streamed_body_counted_while_app_reads():
    """No Content-Length and no Transfer-Encoding (e.g. HTTP/2): the limit is
    enforced as the app reads, and the app's own response is suppressed."""
    from middleware.body_limit import BodySizeLimitMiddleware

    reads: list[dict] = []

    async def app(scope, receive, send):
        while True:
            msg = await receive()
            reads.append(msg)
            if msg["type"] != "http.request" or not msg.get("more_body"):
                break
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    mw = BodySizeLimitMiddleware(app, max_bytes=10)
    sent = asyncio.run(_run(mw, [], [b"12345", b"67890", b"X", b"never"]))
    assert _status(sent) == 413
    assert b"ok" not in b"".join(m.get("body", b"") for m in sent)
    # Body delivery stopped at the limit: the app saw a disconnect, not "never".
    assert reads[-1]["type"] == "http.disconnect"
    assert all(m.get("body") != b"never" for m in reads)


def test_overflow_after_response_started_does_not_send_second_start():
    from middleware.body_limit import BodySizeLimitMiddleware

    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        while True:
            msg = await receive()
            if msg["type"] != "http.request" or not msg.get("more_body"):
                break
        await send({"type": "http.response.body", "body": b""})

    mw = BodySizeLimitMiddleware(app, max_bytes=4)
    sent = asyncio.run(_run(mw, [], [b"abc", b"def", b"ghi"]))
    assert _status(sent) == 200


@pytest.mark.parametrize("value", ["-1", "1.5", "10, 10", ""])
def test_malformed_content_length_is_400(value):
    from middleware.body_limit import BodySizeLimitMiddleware

    async def app(scope, receive, send):  # pragma: no cover - must not run
        raise AssertionError("app reached")

    mw = BodySizeLimitMiddleware(app, max_bytes=10)
    sent = asyncio.run(_run(mw, [("content-length", value)], [b""]))
    assert _status(sent) == 400


def test_non_http_scope_passes_through():
    from middleware.body_limit import BodySizeLimitMiddleware

    seen = []

    async def app(scope, receive, send):
        seen.append(scope["type"])

    mw = BodySizeLimitMiddleware(app)
    asyncio.run(mw({"type": "lifespan"}, None, None))
    assert seen == ["lifespan"]


# --- rate limit and audit carry the trace ID ---------------------------------


def test_429_and_audit_carry_trace_id(client, caplog, monkeypatch):
    from middleware import rate_limiter

    monkeypatch.delenv("STORYFORGE_DISABLE_RATE_LIMIT", raising=False)
    monkeypatch.setitem(rate_limiter._LIMITS, "default", 1)
    with rate_limiter._lock:
        for key in [k for k in rate_limiter._state if k[0] == "testclient"]:
            del rate_limiter._state[key]

    with caplog.at_level(logging.INFO, logger="audit"):
        first = client.get("/api/session")
        second = client.get("/api/session")

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.headers["x-request-id"]

    audit = [r for r in caplog.records if getattr(r, "event", "") == "http_request"]
    assert audit, "no audit record"
    assert audit[0].trace_id == first.headers["x-request-id"]


# --- API docs gating ----------------------------------------------------------


def test_docs_off_by_default(client):
    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_docs_on_with_debug(monkeypatch):
    from app import create_app

    monkeypatch.setenv("STORYFORGE_DEBUG", "1")
    c = TestClient(create_app())
    assert c.get("/docs").status_code == 200
    assert c.get("/redoc").status_code == 200
    assert c.get("/openapi.json").status_code == 200


def test_csrf_docs_exemption_only_under_debug():
    from middleware.csrf import CSRFMiddleware

    async def app(scope, receive, send):  # pragma: no cover
        pass

    assert not any(
        p.startswith(("/docs", "/redoc", "/openapi"))
        for p in CSRFMiddleware(app).exempt_prefixes
    )
    debug = CSRFMiddleware(app, exempt_docs=True).exempt_prefixes
    assert {"/docs", "/redoc", "/openapi.json"} <= set(debug)


# --- CSP ---------------------------------------------------------------------


def test_csp_has_no_unsafe_eval(client):
    csp = client.get("/api/health").headers["content-security-policy"]
    assert "unsafe-eval" not in csp
    script_src = next(d for d in csp.split("; ") if d.startswith("script-src"))
    assert script_src == "script-src 'self' 'unsafe-inline'"
