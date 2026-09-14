"""Regression test: an absurd Retry-After must not stall the pipeline.

Observed on 2026-08-26: a free-tier provider answered a 429 with
`Retry-After: 67364`, `_should_retry` handed that straight to the retry loop,
and Layer 1 slept 18.7 hours in the middle of chapter 1 — no logs, no error,
indistinguishable from a hang. The fallback chain existed the whole time and
was never reached.
"""

import pytest

from services.llm.retry import MAX_HONORED_RETRY_AFTER, _should_retry


class _Headers(dict):
    """Minimal stand-in for an SDK response's headers mapping."""


class _Response:
    def __init__(self, retry_after):
        self.headers = _Headers({"retry-after": str(retry_after)})


class _RateLimited(Exception):
    def __init__(self, retry_after):
        super().__init__("Error code: 429 - free_rate_limited")
        self.response = _Response(retry_after)


class TestRetryAfterCap:
    def test_absurd_retry_after_skips_to_next_provider(self):
        should_retry, delay = _should_retry(_RateLimited(67364), "custom")
        assert should_retry is True
        # 0 == "not retryable here, move down the fallback chain" (see
        # LLMClient._retry_with_backoff).
        assert delay == 0

    def test_just_over_the_cap_also_skips(self):
        _, delay = _should_retry(_RateLimited(MAX_HONORED_RETRY_AFTER + 1), "custom")
        assert delay == 0

    @pytest.mark.parametrize("retry_after", [1, 5, 30, MAX_HONORED_RETRY_AFTER])
    def test_short_retry_after_is_still_honored(self, retry_after):
        should_retry, delay = _should_retry(_RateLimited(retry_after), "custom")
        assert should_retry is True
        assert delay == pytest.approx(float(retry_after))

    def test_429_without_a_header_uses_the_default_delay(self):
        should_retry, delay = _should_retry(Exception("Error code: 429"), "custom")
        assert should_retry is True
        assert delay == 5.0

    def test_daily_quota_providers_still_skip_immediately(self):
        # Unchanged behaviour: these can't recover within one request.
        for provider in ("openrouter", "google"):
            should_retry, delay = _should_retry(_RateLimited(5), provider)
            assert (should_retry, delay) == (True, 0)
