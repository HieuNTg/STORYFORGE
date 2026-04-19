"""Retry logic, error classification, and credential-redaction utilities for LLM calls."""

import re
import time
import logging

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
BASE_DELAY = 1.0

# OpenRouter embeds X-RateLimit-Reset (ms since epoch) in 429 error bodies.
_OPENROUTER_RESET_RE = re.compile(r"['\"]X-RateLimit-Reset['\"]\s*:\s*['\"]?(\d{10,})['\"]?", re.IGNORECASE)

# Patterns that may expose credentials in error messages
_REDACT_PATTERNS = re.compile(
    r'((?:Authorization|Bearer|api[_-]?key|x-api-key)\s*[:=]\s*)'
    r'([A-Za-z0-9\-_.~+/]{8,})',
    re.IGNORECASE,
)


def _redact(message: str) -> str:
    """Strip API keys, bearer tokens, and auth headers from a string before logging."""
    return _REDACT_PATTERNS.sub(r'\1[REDACTED]', str(message))


# Transient error indicators
_TRANSIENT_CODES = {429, 500, 502, 503, 504}

# Auth errors - not model health issues, just credential problems
_AUTH_ERROR_CODES = {401, 403}


def _is_auth_error(exc: Exception) -> bool:
    """Check if exception is an auth/credential error (not a model health issue)."""
    exc_str = str(exc).lower()
    return any(str(code) in exc_str for code in _AUTH_ERROR_CODES) or "no cookie" in exc_str


def _is_transient(exc: Exception) -> bool:
    """Check if exception is transient (worth retrying)."""
    import json
    if isinstance(exc, json.JSONDecodeError):
        return True
    if isinstance(exc, RuntimeError) and (
        "empty choices" in str(exc).lower() or "empty content" in str(exc).lower()
    ):
        return True
    exc_str = str(exc).lower()
    if any(str(code) in exc_str for code in _TRANSIENT_CODES):
        return True
    if any(kw in exc_str for kw in ("timeout", "connection", "reset", "broken pipe", "incomplete chunked")):
        return True
    return False


def _detect_provider(base_url: str) -> str:
    """Detect LLM provider from base URL."""
    if not base_url:
        return "openai"
    url = base_url.lower()
    if "openrouter" in url:
        return "openrouter"
    if "kymaapi.com" in url:
        return "kyma"
    if "localhost" in url or "127.0.0.1" in url or "ollama" in url:
        return "ollama"
    if "anthropic" in url:
        return "anthropic"
    if "gemini" in url or "googleapis" in url:
        return "google"
    if "api.openai.com" in url:
        return "openai"
    return "custom"


def _parse_retry_after(exc: Exception) -> float | None:
    """Extract Retry-After delay from HTTP error response, if available."""
    resp = getattr(exc, "response", None)
    if resp is not None:
        header = getattr(resp, "headers", {}).get("retry-after") or getattr(resp, "headers", {}).get("Retry-After")
        if header:
            try:
                return float(header)
            except ValueError:
                pass
    return None


def parse_openrouter_reset(err_str: str) -> float | None:
    """Seconds remaining until OpenRouter's X-RateLimit-Reset, or None if absent.

    OpenRouter returns reset time as ms-since-epoch embedded in 429 error metadata.
    Clamps to a 60s floor so we never mark a key as "ready" faster than sane.
    """
    match = _OPENROUTER_RESET_RE.search(err_str)
    if not match:
        return None
    try:
        reset_ms = int(match.group(1))
    except ValueError:
        return None
    # Heuristic: values < 1e12 are plain seconds; >= 1e12 are ms.
    reset_sec = reset_ms / 1000.0 if reset_ms >= 10**12 else float(reset_ms)
    delta = reset_sec - time.time()
    if delta <= 0:
        return None
    return max(delta, 60.0)


def _should_retry(exc: Exception, provider: str) -> tuple[bool, float]:
    """Decide if error is retryable and suggest delay.

    Returns: (should_retry, delay_seconds)
    """
    exc_str = str(exc).lower()

    # Ollama: model not loaded = unrecoverable
    if provider == "ollama" and ("model" in exc_str and ("not found" in exc_str or "not loaded" in exc_str)):
        return False, 0

    # OpenAI: org quota exceeded = unrecoverable
    if provider == "openai" and "quota" in exc_str and "exceeded" in exc_str:
        return False, 0

    # 429 rate limit — use Retry-After header if available, else provider defaults
    if "429" in exc_str:
        # Daily-quota exhaustion on these providers cannot recover within a single
        # request; skip to the next model/key instead of sleeping on the same one.
        if provider in ("openrouter", "kyma", "google"):
            return True, 0
        retry_after = _parse_retry_after(exc)
        if retry_after is not None:
            return True, retry_after
        return True, 5.0  # Default rate limit delay

    # Empty content on OpenRouter/Kyma — content filter or guardrail; skip to next model
    if provider in ("openrouter", "kyma") and "empty content" in exc_str:
        return True, 0

    # Model not found on OpenRouter/Kyma — not retryable on same provider, try next
    if provider in ("openrouter", "kyma") and "404" in exc_str:
        return True, 0

    # Auth errors — not retryable on same key, but should try next provider
    if "401" in exc_str or "403" in exc_str or "no cookie" in exc_str:
        return True, 0

    # Standard transient errors
    if _is_transient(exc):
        return True, BASE_DELAY

    return False, 0
