"""Abstract base class for config repositories.

Split into its own module to avoid circular imports between
config_repository.py (factory) and the implementation modules.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class ConfigRepository(ABC):
    """Abstract interface for config key/value persistence.

    Keys are arbitrary strings; dotted notation (e.g. "llm.model") is
    supported by JsonFileConfigRepository for nested access.
    Values are arbitrary JSON-serialisable dicts.
    """

    @abstractmethod
    async def get_config(self, key: str) -> dict:
        """Return config section dict for the given key, or {} if not found."""

    @abstractmethod
    async def set_config(self, key: str, value: dict) -> bool:
        """Persist value under key. Returns True on success."""

    @abstractmethod
    async def get_all(self) -> dict:
        """Return the full config document."""

    @abstractmethod
    async def delete_config(self, key: str) -> bool:
        """Remove key from config. Returns True if key existed."""
