"""Tests for middleware/rate_limiter.py and related service classes.

Covers:
- IP extraction logic (_get_ip)
- Tier classification (_get_tier)
- In-memory rate limiting (_check_rate_limit_memory, _evict_expired_entries)
- Redis rate limiting (_check_rate_limit_redis) with graceful fallback
- RateLimitMiddleware.dispatch (429, Retry-After, exempt paths)
- InMemoryRateLimiter service class (is_allowed, get_remaining)
- RedisRateLimiter service class (fallback on unavailable)
"""
from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Request
from fastapi.responses import JSONResponse

# Reset module-level globals between tests that mutate them
import middleware.rate_limiter as rl_mod
from middleware.rate_limiter import (
    RateLimitMiddleware,
    _check_rate_limit_memory,
    _check_rate_limit_redis,
    _evict_expired_entries,
    _get_ip,
    _get_tier,
    _LIMITS,
    _WINDOW_SECONDS,
)
from services._rate_limiter_inmemory import InMemoryRateLimiter
from services._rate_limiter_redis_impl import RedisRateLimiter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_request(path: str = "/api/stories", client_ip: str = "1.2.3.4", headers: dict | None = None) -> Request:
    """Build a minimal mock Request."""
    req = MagicMock(spec=Request)
    req.client = MagicMock()
    req.client.host = client_ip
    req.url = MagicMock()
    req.url.path = path
    req.headers = headers or {}
    return req


def _clear_state():
    """Wipe in-memory rate-limit state between tests."""
    with rl_mod._lock:
        rl_mod._state.clear()


# ---------------------------------------------------------------------------
# TestGetIP
# ---------------------------------------------------------------------------

class TestGetIP:
    def setup_method(self):
        # Ensure _TRUSTED_PROXIES is empty unless explicitly set in a test
        self._original = rl_mod._TRUSTED_PROXIES.copy()
        rl_mod._TRUSTED_PROXIES.clear()

    def teardown_method(self):
        rl_mod._TRUSTED_PROXIES.clear()
        rl_mod._TRUSTED_PROXIES.update(self._original)

    def test_returns_direct_client_ip(self):
        req = _make_request(client_ip="5.6.7.8")
        assert _get_ip(req) == "5.6.7.8"

    def test_ignores_forwarded_for_without_trusted_proxy(self):
        """X-Forwarded-For must be ignored when no trusted proxies configured."""
        req = _make_request(client_ip="1.1.1.1", headers={"X-Forwarded-For": "9.9.9.9"})
        assert _get_ip(req) == "1.1.1.1"

    def test_uses_forwarded_for_from_trusted_proxy(self):
        rl_mod._TRUSTED_PROXIES.add("10.0.0.1")
        req = _make_request(client_ip="10.0.0.1", headers={"X-Forwarded-For": "203.0.113.5"})
        assert _get_ip(req) == "203.0.113.5"

    def test_uses_first_ip_in_forwarded_for_chain(self):
        rl_mod._TRUSTED_PROXIES.add("10.0.0.1")
        req = _make_request(
            client_ip="10.0.0.1",
            headers={"X-Forwarded-For": "203.0.113.5, 10.0.0.2, 10.0.0.1"},
        )
        assert _get_ip(req) == "203.0.113.5"

    def test_untrusted_proxy_ignored_even_with_trusted_list(self):
        rl_mod._TRUSTED_PROXIES.add("10.0.0.1")
        req = _make_request(client_ip="8.8.8.8", headers={"X-Forwarded-For": "9.9.9.9"})
        # 8.8.8.8 is NOT in trusted set → use direct IP
        assert _get_ip(req) == "8.8.8.8"

    def test_no_client_returns_unknown(self):
        req = MagicMock(spec=Request)
        req.client = None
        req.headers = {}
        result = _get_ip(req)
        assert result == "unknown"


# ---------------------------------------------------------------------------
# TestGetTier
# ---------------------------------------------------------------------------

class TestGetTier:
    def test_default_tier_for_normal_api(self):
        assert _get_tier("/api/stories") == "default"

    def test_expensive_tier_for_pipeline_run(self):
        assert _get_tier("/api/pipeline/run") == "expensive"

    def test_expensive_tier_for_export(self):
        assert _get_tier("/api/export/pdf") == "expensive"

    def test_expensive_tier_for_export_root(self):
        assert _get_tier("/api/export/") == "expensive"

    def test_default_tier_for_health(self):
        assert _get_tier("/api/health") == "default"

    def test_default_tier_for_non_api(self):
        assert _get_tier("/") == "default"

    def test_default_tier_for_pipeline_non_run(self):
        assert _get_tier("/api/pipeline/status") == "default"

    def test_limits_dict_has_correct_values(self):
        assert _LIMITS["expensive"] == 10
        assert _LIMITS["default"] == 60


# ---------------------------------------------------------------------------
# TestCheckRateLimitMemory
# ---------------------------------------------------------------------------

class TestCheckRateLimitMemory:
    def setup_method(self):
        _clear_state()

    def test_first_request_is_allowed(self):
        assert _check_rate_limit_memory("10.0.0.1", "default") is True

    def test_requests_within_limit_are_allowed(self):
        limit = _LIMITS["expensive"]  # 10
        for _ in range(limit):
            assert _check_rate_limit_memory("10.0.0.2", "expensive") is True

    def test_request_over_limit_is_blocked(self):
        limit = _LIMITS["expensive"]  # 10
        for _ in range(limit):
            _check_rate_limit_memory("10.0.0.3", "expensive")
        # 11th request must be blocked
        assert _check_rate_limit_memory("10.0.0.3", "expensive") is False

    def test_different_ips_have_independent_counters(self):
        limit = _LIMITS["expensive"]
        for _ in range(limit):
            _check_rate_limit_memory("10.0.0.4", "expensive")
        # Different IP should still be allowed
        assert _check_rate_limit_memory("10.0.0.5", "expensive") is True

    def test_different_tiers_have_independent_counters(self):
        limit = _LIMITS["expensive"]
        for _ in range(limit):
            _check_rate_limit_memory("10.0.0.6", "expensive")
        # same IP on default tier must still be allowed
        assert _check_rate_limit_memory("10.0.0.6", "default") is True

    def test_counter_resets_after_window(self):
        limit = _LIMITS["expensive"]
        for _ in range(limit):
            _check_rate_limit_memory("10.0.0.7", "expensive")
        # Simulate window expiry by rewinding window_start
        key = ("10.0.0.7", "expensive")
        with rl_mod._lock:
            rl_mod._state[key][1] -= _WINDOW_SECONDS + 1
        assert _check_rate_limit_memory("10.0.0.7", "expensive") is True


# ---------------------------------------------------------------------------
# TestEvictExpiredEntries
# ---------------------------------------------------------------------------

class TestEvictExpiredEntries:
    def setup_method(self):
        _clear_state()

    def test_evicts_expired_entries(self):
        now = time.monotonic()
        with rl_mod._lock:
            rl_mod._state[("old-ip", "default")] = [5, now - _WINDOW_SECONDS - 1]
            rl_mod._state[("new-ip", "default")] = [5, now]
            _evict_expired_entries()
            assert ("old-ip", "default") not in rl_mod._state
            assert ("new-ip", "default") in rl_mod._state

    def test_keeps_active_entries(self):
        now = time.monotonic()
        with rl_mod._lock:
            rl_mod._state[("active-ip", "default")] = [1, now]
            _evict_expired_entries()
            assert ("active-ip", "default") in rl_mod._state


# ---------------------------------------------------------------------------
# TestCheckRateLimitRedis
# ---------------------------------------------------------------------------

class TestCheckRateLimitRedis:
    def setup_method(self):
        _clear_state()
        # Reset Redis state so _get_redis() is re-evaluated
        rl_mod._redis_client = None
        rl_mod._redis_init_attempted = False

    def test_falls_back_to_memory_when_no_redis_url(self):
        """When REDIS_URL is absent, _get_redis returns None → memory fallback."""
        with patch.dict("os.environ", {}, clear=True):
            # First request should be allowed via memory fallback
            result = _check_rate_limit_redis("192.0.2.1", "default")
        assert result is True

    def test_falls_back_to_memory_on_redis_connection_error(self):
        rl_mod._redis_init_attempted = False
        with patch.dict("os.environ", {"REDIS_URL": "redis://localhost:6379"}):
            with patch("redis.from_url", side_effect=Exception("connection refused")):
                result = _check_rate_limit_redis("192.0.2.2", "default")
        assert result is True  # memory fallback allowed

    def test_uses_redis_when_available(self):
        mock_redis = MagicMock()
        mock_redis.ping.return_value = True
        mock_redis.eval.return_value = 1  # first request
        rl_mod._redis_client = mock_redis
        rl_mod._redis_init_attempted = True

        with patch.dict("os.environ", {"REDIS_URL": "redis://localhost:6379"}):
            result = _check_rate_limit_redis("192.0.2.3", "default")
        assert result is True
        mock_redis.eval.assert_called_once()

    def test_blocks_when_redis_returns_over_limit(self):
        mock_redis = MagicMock()
        mock_redis.ping.return_value = True
        mock_redis.eval.return_value = _LIMITS["default"] + 1
        rl_mod._redis_client = mock_redis
        rl_mod._redis_init_attempted = True

        with patch.dict("os.environ", {"REDIS_URL": "redis://localhost:6379"}):
            result = _check_rate_limit_redis("192.0.2.4", "default")
        assert result is False

    def test_falls_back_to_memory_on_redis_eval_error(self):
        mock_redis = MagicMock()
        mock_redis.ping.return_value = True
        mock_redis.eval.side_effect = Exception("NOSCRIPT")
        rl_mod._redis_client = mock_redis
        rl_mod._redis_init_attempted = True

        with patch.dict("os.environ", {"REDIS_URL": "redis://localhost:6379"}):
            result = _check_rate_limit_redis("192.0.2.5", "default")
        assert result is True  # memory fallback


# ---------------------------------------------------------------------------
# TestRateLimitMiddlewareDispatch
# ---------------------------------------------------------------------------

class TestRateLimitMiddlewareDispatch:
    def setup_method(self):
        _clear_state()
        rl_mod._redis_client = None
        rl_mod._redis_init_attempted = False

    def _make_middleware(self):
        app = AsyncMock()
        mw = RateLimitMiddleware(app)
        return mw

    async def _dispatch(self, mw, path: str, client_ip: str = "1.2.3.4") -> object:
        req = _make_request(path=path, client_ip=client_ip)
        call_next = AsyncMock(return_value=MagicMock(status_code=200))
        return await mw.dispatch(req, call_next)

    @pytest.mark.asyncio
    async def test_passes_non_api_paths(self):
        mw = self._make_middleware()
        req = _make_request(path="/")
        call_next = AsyncMock(return_value=MagicMock(status_code=200))
        await mw.dispatch(req, call_next)
        call_next.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_passes_health_check(self):
        mw = self._make_middleware()
        req = _make_request(path="/api/health")
        call_next = AsyncMock(return_value=MagicMock(status_code=200))
        await mw.dispatch(req, call_next)
        call_next.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_passes_metrics_endpoint(self):
        mw = self._make_middleware()
        req = _make_request(path="/api/metrics")
        call_next = AsyncMock(return_value=MagicMock(status_code=200))
        await mw.dispatch(req, call_next)
        call_next.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_allows_request_within_limit(self):
        mw = self._make_middleware()
        req = _make_request(path="/api/stories", client_ip="2.2.2.2")
        call_next = AsyncMock(return_value=MagicMock(status_code=200))
        await mw.dispatch(req, call_next)
        call_next.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_429_when_over_limit(self):
        mw = self._make_middleware()
        ip = "3.3.3.3"
        # Exhaust expensive limit (10) on pipeline path
        limit = _LIMITS["expensive"]
        for _ in range(limit):
            _check_rate_limit_memory(ip, "expensive")

        req = _make_request(path="/api/pipeline/run", client_ip=ip)
        call_next = AsyncMock(return_value=MagicMock(status_code=200))
        resp = await mw.dispatch(req, call_next)

        assert isinstance(resp, JSONResponse)
        assert resp.status_code == 429

    @pytest.mark.asyncio
    async def test_429_response_has_retry_after_header(self):
        mw = self._make_middleware()
        ip = "4.4.4.4"
        limit = _LIMITS["expensive"]
        for _ in range(limit):
            _check_rate_limit_memory(ip, "expensive")

        req = _make_request(path="/api/pipeline/run", client_ip=ip)
        call_next = AsyncMock(return_value=MagicMock(status_code=200))
        resp = await mw.dispatch(req, call_next)

        assert "Retry-After" in resp.headers
        assert resp.headers["Retry-After"] == str(_WINDOW_SECONDS)

    @pytest.mark.asyncio
    async def test_429_body_contains_error_detail(self):
        mw = self._make_middleware()
        ip = "5.5.5.5"
        limit = _LIMITS["expensive"]
        for _ in range(limit):
            _check_rate_limit_memory(ip, "expensive")

        req = _make_request(path="/api/pipeline/run", client_ip=ip)
        call_next = AsyncMock(return_value=MagicMock(status_code=200))
        resp = await mw.dispatch(req, call_next)

        import json
        body = json.loads(resp.body)
        assert body["error"] == "Too Many Requests"
        assert "Rate limit exceeded" in body["detail"]

    @pytest.mark.asyncio
    async def test_call_next_not_called_when_rate_limited(self):
        mw = self._make_middleware()
        ip = "6.6.6.6"
        limit = _LIMITS["expensive"]
        for _ in range(limit):
            _check_rate_limit_memory(ip, "expensive")

        req = _make_request(path="/api/pipeline/run", client_ip=ip)
        call_next = AsyncMock()
        await mw.dispatch(req, call_next)
        call_next.assert_not_awaited()


# ---------------------------------------------------------------------------
# TestInMemoryRateLimiter (service class)
# ---------------------------------------------------------------------------

class TestInMemoryRateLimiter:
    def test_is_allowed_first_request(self):
        limiter = InMemoryRateLimiter()
        assert limiter.is_allowed("key1", limit=5, window_seconds=60) is True

    def test_is_allowed_up_to_limit(self):
        limiter = InMemoryRateLimiter()
        for _ in range(5):
            assert limiter.is_allowed("key2", limit=5, window_seconds=60) is True

    def test_is_blocked_over_limit(self):
        limiter = InMemoryRateLimiter()
        for _ in range(5):
            limiter.is_allowed("key3", limit=5, window_seconds=60)
        assert limiter.is_allowed("key3", limit=5, window_seconds=60) is False

    def test_get_remaining_full_at_start(self):
        limiter = InMemoryRateLimiter()
        assert limiter.get_remaining("fresh-key", limit=10, window_seconds=60) == 10

    def test_get_remaining_decrements(self):
        limiter = InMemoryRateLimiter()
        limiter.is_allowed("dec-key", limit=10, window_seconds=60)
        assert limiter.get_remaining("dec-key", limit=10, window_seconds=60) == 9

    def test_get_remaining_zero_when_exhausted(self):
        limiter = InMemoryRateLimiter()
        for _ in range(10):
            limiter.is_allowed("ex-key", limit=10, window_seconds=60)
        assert limiter.get_remaining("ex-key", limit=10, window_seconds=60) == 0

    def test_resets_after_window_expires(self):
        limiter = InMemoryRateLimiter()
        for _ in range(5):
            limiter.is_allowed("win-key", limit=5, window_seconds=60)
        # Backdate the window start
        with limiter._lock:
            limiter._state["win-key"][1] -= 61
        assert limiter.is_allowed("win-key", limit=5, window_seconds=60) is True

    def test_independent_keys_do_not_interfere(self):
        limiter = InMemoryRateLimiter()
        for _ in range(5):
            limiter.is_allowed("key-a", limit=5, window_seconds=60)
        assert limiter.is_allowed("key-b", limit=5, window_seconds=60) is True


# ---------------------------------------------------------------------------
# TestRedisRateLimiter (service class)
# ---------------------------------------------------------------------------

class TestRedisRateLimiter:
    def test_falls_back_to_inmemory_when_redis_unavailable(self):
        with patch("redis.from_url", side_effect=Exception("refused")):
            limiter = RedisRateLimiter("redis://localhost:6379")
        assert limiter._healthy is False
        # Should still work via in-memory fallback
        assert limiter.is_allowed("fallback-key", limit=5, window_seconds=60) is True

    def test_is_healthy_when_redis_connects(self):
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.script_load.return_value = "abc123"
        with patch("redis.from_url", return_value=mock_client):
            limiter = RedisRateLimiter("redis://localhost:6379")
        assert limiter._healthy is True

    def test_is_allowed_via_redis_within_limit(self):
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.script_load.return_value = "abc123"
        mock_client.evalsha.return_value = 1
        with patch("redis.from_url", return_value=mock_client):
            limiter = RedisRateLimiter("redis://localhost:6379")
            result = limiter.is_allowed("rkey", limit=10, window_seconds=60)
        assert result is True

    def test_is_blocked_when_redis_returns_over_limit(self):
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.script_load.return_value = "abc123"
        mock_client.evalsha.return_value = 11
        with patch("redis.from_url", return_value=mock_client):
            limiter = RedisRateLimiter("redis://localhost:6379")
            result = limiter.is_allowed("rkey2", limit=10, window_seconds=60)
        assert result is False

    def test_get_remaining_falls_back_when_unhealthy(self):
        with patch("redis.from_url", side_effect=Exception("refused")):
            limiter = RedisRateLimiter("redis://localhost:6379")
        remaining = limiter.get_remaining("rkey3", limit=10, window_seconds=60)
        # Fallback in-memory: no usage yet, so full limit remains
        assert remaining == 10

    def test_degrades_to_inmemory_on_evalsha_error(self):
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.script_load.return_value = "abc123"
        mock_client.evalsha.side_effect = Exception("NOSCRIPT")
        with patch("redis.from_url", return_value=mock_client):
            limiter = RedisRateLimiter("redis://localhost:6379")
            result = limiter.is_allowed("rkey4", limit=10, window_seconds=60)
        # After error, healthy=False → memory fallback used → allowed
        assert result is True
