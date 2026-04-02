"""Abstract base class for rate limiters.

Split into its own module to avoid circular imports.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class RateLimiterBase(ABC):
    """Common interface for all rate limiter backends."""

    @abstractmethod
    def is_allowed(self, key: str, limit: int, window_seconds: int) -> bool:
        """Return True if the request is within the allowed rate.

        Args:
            key:            Unique identifier (e.g. "ip:1.2.3.4:tier:default").
            limit:          Max requests allowed in the window.
            window_seconds: Sliding window length in seconds.
        """

    @abstractmethod
    def get_remaining(self, key: str, limit: int, window_seconds: int) -> int:
        """Return requests remaining in the current window (>= 0)."""
