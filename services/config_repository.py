"""Config persistence abstraction for StoryForge.

Provides an abstract ConfigRepository interface with two implementations:
  - JsonFileConfigRepository: thread-safe JSON file backend (default)
  - PostgresConfigRepository: stub for Sprint 7 Postgres migration

Use get_config_repository() factory to get the appropriate implementation
based on the DATABASE_URL environment variable.

Module layout:
  config_repository.py      — this file: base class + factory (public API)
  _config_repo_base.py      — ABC definition (avoids circular imports)
  _config_repo_json.py      — JsonFileConfigRepository
  _config_repo_pg.py        — PostgresConfigRepository stub
"""

from __future__ import annotations

import logging
import os
import threading

from services._config_repo_base import ConfigRepository
from services._config_repo_json import JsonFileConfigRepository
from services._config_repo_pg import PostgresConfigRepository

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Factory (singleton)
# ---------------------------------------------------------------------------

_instance: ConfigRepository | None = None
_factory_lock = threading.Lock()


def get_config_repository(config_file: str = "data/config.json") -> ConfigRepository:
    """Return the appropriate ConfigRepository singleton.

    Selection:
      DATABASE_URL set → PostgresConfigRepository (Sprint 7 stub)
      Otherwise        → JsonFileConfigRepository
    """
    global _instance
    if _instance is not None:
        return _instance
    with _factory_lock:
        if _instance is not None:
            return _instance
        database_url = os.environ.get("DATABASE_URL", "").strip()
        if database_url:
            logger.info("config_repository: using PostgresConfigRepository (DATABASE_URL set)")
            _instance = PostgresConfigRepository()
        else:
            logger.info("config_repository: using JsonFileConfigRepository (%s)", config_file)
            _instance = JsonFileConfigRepository(config_file)
    return _instance


__all__ = [
    "ConfigRepository",
    "JsonFileConfigRepository",
    "PostgresConfigRepository",
    "get_config_repository",
]
