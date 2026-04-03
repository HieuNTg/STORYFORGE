"""Token revocation store for StoryForge JWT authentication.

Supports in-memory revocation (always active) plus optional Redis backing
when REDIS_URL env var is set. Tokens are stored by their `jti` claim.

Note: In-memory revocation does not survive server restarts.
Deploy with REDIS_URL for persistent revocation in production.
"""
from __future__ import annotations

import logging
import os
import time

logger = logging.getLogger(__name__)

# In-memory revocation set: {jti: expiry_timestamp}
_revoked: dict[str, float] = {}
_EVICT_INTERVAL = 100  # Prune every N checks instead of every call
_check_counter = 0

# Cached Redis client (singleton)
_redis_client = None
_redis_checked = False


def _get_redis():
    """Return a cached Redis client if REDIS_URL is configured, else None."""
    global _redis_client, _redis_checked
    if _redis_checked:
        return _redis_client
    _redis_checked = True
    url = os.environ.get("REDIS_URL", "")
    if not url:
        return None
    try:
        import redis  # type: ignore
        _redis_client = redis.from_url(url, decode_responses=True)
        return _redis_client
    except Exception as exc:
        logger.warning(f"Redis unavailable for token revocation: {exc}")
        return None


def revoke_token(jti: str, exp: float) -> None:
    """Mark a token as revoked.

    Args:
        jti: JWT ID claim value.
        exp: Token expiry timestamp (used for TTL / cleanup).
    """
    _revoked[jti] = exp
    r = _get_redis()
    if r:
        try:
            ttl = max(1, int(exp - time.time()))
            r.setex(f"revoked:{jti}", ttl, "1")
        except Exception as exc:
            logger.warning(f"Redis revoke failed, in-memory fallback used: {exc}")


def is_revoked(jti: str) -> bool:
    """Check whether a token JTI has been revoked.

    Args:
        jti: JWT ID claim to check.

    Returns:
        True if revoked, False otherwise.
    """
    global _check_counter
    _check_counter += 1

    # Prune expired in-memory entries periodically (not on every call)
    if _check_counter % _EVICT_INTERVAL == 0:
        now = time.time()
        expired_keys = [k for k, exp in _revoked.items() if exp < now]
        for k in expired_keys:
            del _revoked[k]

    if jti in _revoked:
        return True

    r = _get_redis()
    if r:
        try:
            return bool(r.exists(f"revoked:{jti}"))
        except Exception as exc:
            logger.warning(f"Redis revocation check failed, using in-memory: {exc}")

    return False


def clear_revocations() -> None:
    """Clear all in-memory revocations (test helper only)."""
    global _redis_client, _redis_checked, _check_counter
    _revoked.clear()
    _redis_client = None
    _redis_checked = False
    _check_counter = 0
