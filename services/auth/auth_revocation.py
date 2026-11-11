"""Token revocation store for StoryForge JWT authentication.

Revocations are held in memory, keyed by the token's `jti` claim.

Note: In-memory revocation does not survive server restarts.
"""

from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)

# In-memory revocation set: {jti: expiry_timestamp}
_revoked: dict[str, float] = {}
_EVICT_INTERVAL = 100  # Prune every N checks instead of every call
_check_counter = 0

def revoke_token(jti: str, exp: float) -> None:
    """Mark a token as revoked.

    Args:
        jti: JWT ID claim value.
        exp: Token expiry timestamp (used for TTL / cleanup).
    """
    _revoked[jti] = exp


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

    return jti in _revoked


def clear_revocations() -> None:
    """Clear all in-memory revocations (test helper only)."""
    global _check_counter
    _revoked.clear()
    _check_counter = 0
