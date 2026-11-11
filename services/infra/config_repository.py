"""Config persistence abstraction for StoryForge.

Provides an abstract ConfigRepository interface and its one implementation,
JsonFileConfigRepository (thread-safe JSON file backend). Use the
get_config_repository() factory to get the shared instance.

Module layout:
  config_repository.py      — this file: base class + factory (public API)
  _config_repo_base.py      — ABC definition (avoids circular imports)
  _config_repo_json.py      — JsonFileConfigRepository
"""

from __future__ import annotations

import logging
import threading

from services._config_repo_base import ConfigRepository
from services._config_repo_json import JsonFileConfigRepository

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Factory (singleton)
# ---------------------------------------------------------------------------

_instance: ConfigRepository | None = None
_factory_lock = threading.Lock()


def get_config_repository(config_file: str = "data/config.json") -> ConfigRepository:
    """Return the ConfigRepository singleton (a JsonFileConfigRepository)."""
    global _instance
    if _instance is not None:
        return _instance
    with _factory_lock:
        if _instance is not None:
            return _instance
        logger.info(
            "config_repository: using JsonFileConfigRepository (%s)", config_file
        )
        _instance = JsonFileConfigRepository(config_file)
    return _instance


__all__ = [
    "ConfigRepository",
    "JsonFileConfigRepository",
    "get_config_repository",
]
