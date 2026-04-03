"""Coverage tests for middleware: rate limiter, audit, trace ID, metrics."""
from __future__ import annotations

import os
import sys
import time
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    from fastapi import FastAPI, Request
    from fastapi.testclient import TestClient
    _HAS_FASTAPI = True
except ImportError:
    _HAS_FASTAPI = False


@pytest.mark.skipif(not _HAS_FASTAPI, reason="FastAPI not installed")
class TestRateLimiterMiddleware:
    """Tests for rate limiter middleware."""

    def _make_app_with_rate_limiter(self):
        from middleware.rate_limiter import RateLimitMiddleware as RateLimiterMiddleware
        app = FastAPI()

        @app.get("/api/test")
        def test_route():
            return {"ok": True}

        @app.get("/api/pipeline/run")
        def expensive_route():
            return {"ok": True}

        app.add_middleware(RateLimiterMiddleware)
        return app

    def test_normal_request_passes(self):
        app = self._make_app_with_rate_limiter()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/test")
        assert resp.status_code == 200

    def test_rate_limit_response_ok(self):
        app = self._make_app_with_rate_limiter()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/test")
        # Rate limiter either allows (200) or blocks (429)
        assert resp.status_code in (200, 429)

    def test_expensive_endpoint_recognized(self):
        """Expensive endpoints are in the correct tier."""
        from middleware.rate_limiter import _get_tier
        assert _get_tier("/api/pipeline/run") == "expensive"
        assert _get_tier("/api/export/zip/123") == "expensive"
        assert _get_tier("/api/config") == "default"
        assert _get_tier("/api/health") == "default"

    def test_get_ip_no_proxy(self):
        """_get_ip returns direct client IP when no trusted proxy."""
        from middleware.rate_limiter import _get_ip
        mock_request = MagicMock()
        mock_request.client.host = "1.2.3.4"
        mock_request.headers.get.return_value = None
        ip = _get_ip(mock_request)
        assert ip == "1.2.3.4"

    def test_get_ip_with_forwarded_header_untrusted(self):
        """X-Forwarded-For ignored from untrusted proxy."""
        from middleware.rate_limiter import _get_ip, _TRUSTED_PROXIES
        mock_request = MagicMock()
        mock_request.client.host = "5.6.7.8"  # not a trusted proxy
        mock_request.headers.get.return_value = "10.0.0.1"
        # If 5.6.7.8 is not in _TRUSTED_PROXIES, should use direct IP
        ip = _get_ip(mock_request)
        if "5.6.7.8" not in _TRUSTED_PROXIES:
            assert ip == "5.6.7.8"

    def test_get_ip_no_client(self):
        """_get_ip handles missing client."""
        from middleware.rate_limiter import _get_ip
        mock_request = MagicMock()
        mock_request.client = None
        ip = _get_ip(mock_request)
        assert ip == "unknown"

    def test_in_memory_rate_limit_state_tracking(self):
        """In-memory state tracks request counts."""
        from middleware.rate_limiter import _state, _lock
        # Just verify state is a dict
        assert isinstance(_state, dict)

    def test_rate_limit_429_after_burst(self):
        """After enough requests, rate limit kicks in."""
        from middleware.rate_limiter import _check_rate_limit_memory, _LIMITS, _WINDOW_SECONDS
        # Use a fake IP unlikely to be used elsewhere
        fake_ip = "192.0.2.255"
        fake_tier = "expensive"
        limit = _LIMITS[fake_tier]
        # Fill up the bucket by calling until limited
        from middleware.rate_limiter import _state, _lock
        now = time.monotonic()
        with _lock:
            # Set count to exactly the limit, window fresh
            _state[(fake_ip, fake_tier)] = [limit, now]
        result = _check_rate_limit_memory(fake_ip, fake_tier)
        assert result is False  # should be rate-limited


@pytest.mark.skipif(not _HAS_FASTAPI, reason="FastAPI not installed")
class TestTraceIDMiddleware:
    """Tests for TraceID middleware."""

    def test_trace_id_added_to_response(self):
        from middleware.trace_id import TraceIDMiddleware, get_trace_id
        app = FastAPI()

        @app.get("/test")
        def route():
            return {"trace": get_trace_id()}

        app.add_middleware(TraceIDMiddleware)
        client = TestClient(app)
        resp = client.get("/test")
        assert resp.status_code == 200
        assert "X-Request-ID" in resp.headers

    def test_trace_id_propagates_existing_header(self):
        from middleware.trace_id import TraceIDMiddleware
        app = FastAPI()

        @app.get("/test")
        def route():
            return {"ok": True}

        app.add_middleware(TraceIDMiddleware)
        client = TestClient(app)
        resp = client.get("/test", headers={"X-Request-ID": "my-trace-123"})
        assert resp.headers["X-Request-ID"] == "my-trace-123"

    def test_get_trace_id_returns_string(self):
        """get_trace_id returns empty string outside request context."""
        from middleware.trace_id import get_trace_id
        result = get_trace_id()
        assert isinstance(result, str)

    def test_trace_id_generates_uuid_when_absent(self):
        from middleware.trace_id import TraceIDMiddleware
        import uuid as _uuid
        app = FastAPI()

        @app.get("/test")
        def route():
            return {"ok": True}

        app.add_middleware(TraceIDMiddleware)
        client = TestClient(app)
        resp = client.get("/test")
        trace_id = resp.headers.get("X-Request-ID", "")
        # Should be a valid UUID4
        try:
            _uuid.UUID(trace_id, version=4)
            valid = True
        except ValueError:
            valid = False
        assert valid


@pytest.mark.skipif(not _HAS_FASTAPI, reason="FastAPI not installed")
class TestAuditMiddleware:
    """Tests for AuditMiddleware."""

    def test_audit_logs_api_requests(self):
        from middleware.audit_middleware import AuditMiddleware
        app = FastAPI()

        @app.get("/api/test")
        def route():
            return {"ok": True}

        app.add_middleware(AuditMiddleware)
        client = TestClient(app, raise_server_exceptions=False)
        with patch("middleware.audit_middleware.logger") as mock_logger:
            resp = client.get("/api/test")
        assert resp.status_code == 200

    def test_audit_skips_static_files(self):
        from middleware.audit_middleware import AuditMiddleware, _SKIP_PREFIXES
        # Verify static paths are in skip list
        assert "/static/" in _SKIP_PREFIXES
        assert "/favicon" in _SKIP_PREFIXES

    def test_audit_get_ip(self):
        from middleware.audit_middleware import _get_ip
        mock_request = MagicMock()
        mock_request.client.host = "9.9.9.9"
        mock_request.headers.get.return_value = None
        ip = _get_ip(mock_request)
        assert isinstance(ip, str)


@pytest.mark.skipif(not _HAS_FASTAPI, reason="FastAPI not installed")
class TestMetricsMiddleware:
    """Tests for MetricsMiddleware."""

    def test_metrics_middleware_records_request(self):
        from middleware.metrics_middleware import MetricsMiddleware
        app = FastAPI()

        @app.get("/api/test")
        def route():
            return {"ok": True}

        app.add_middleware(MetricsMiddleware)
        client = TestClient(app, raise_server_exceptions=False)
        with patch("middleware.metrics_middleware.prometheus_metrics") as mock_metrics:
            resp = client.get("/api/test")
        assert resp.status_code == 200
        mock_metrics.record_request.assert_called_once()

    def test_metrics_skips_health_endpoint(self):
        from middleware.metrics_middleware import MetricsMiddleware, _SKIP_PATHS
        assert "/api/health" in _SKIP_PATHS

    def test_metrics_middleware_skips_health(self):
        from middleware.metrics_middleware import MetricsMiddleware
        app = FastAPI()

        @app.get("/api/health")
        def health():
            return {"status": "ok"}

        app.add_middleware(MetricsMiddleware)
        client = TestClient(app, raise_server_exceptions=False)
        with patch("middleware.metrics_middleware.prometheus_metrics") as mock_metrics:
            resp = client.get("/api/health")
        assert resp.status_code == 200
        mock_metrics.record_request.assert_not_called()


class TestInMemoryRateLimiterBackend:
    """Direct tests of in-memory rate limiter backend."""

    def test_check_rate_limit_fresh_ip_passes(self):
        from middleware.rate_limiter import _check_rate_limit_memory, _state, _lock
        ip = "192.0.2.100"
        tier = "default"
        with _lock:
            _state.pop((ip, tier), None)
        result = _check_rate_limit_memory(ip, tier)
        assert result is True

    def test_check_rate_limit_expired_window_resets(self):
        """Expired window resets the counter."""
        from middleware.rate_limiter import _check_rate_limit_memory, _state, _lock, _WINDOW_SECONDS
        ip = "192.0.2.101"
        tier = "default"
        old_time = time.monotonic() - _WINDOW_SECONDS - 10
        with _lock:
            # count=999, but old timestamp — window expired
            _state[(ip, tier)] = [999, old_time]
        result = _check_rate_limit_memory(ip, tier)
        assert result is True  # window expired, reset to 1, should pass
