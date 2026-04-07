"""Retry logic, error classification, and credential-redaction utilities for LLM calls."""

import re
import logging

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
BASE_DELAY = 1.0

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


def _is_transient(exc: Exception) -> bool:
    """Check if exception is transient (worth retrying)."""
    import json
    if isinstance(exc, json.JSONDecodeError):
        return True
    if isinstance(exc, RuntimeError) and "empty choices" in str(exc).lower():
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
        if provider == "openrouter":
            return True, 0  # Skip immediately to next model in chain
        retry_after = _parse_retry_after(exc)
        if retry_after is not None:
            return True, retry_after
        return True, 5.0  # Default rate limit delay

    # Model not found on OpenRouter — not retryable on same provider, try next
    if provider == "openrouter" and "404" in exc_str:
        return True, 0

    # Auth errors — not retryable on same key, but should try next provider
    if "401" in exc_str or "403" in exc_str or "no cookie" in exc_str:
        return True, 0

    # Standard transient errors
    if _is_transient(exc):
        return True, BASE_DELAY

    return False, 0
