"""PostgresConfigRepository — Sprint 7 stub.

Internal module; public API is via services.config_repository.

When DATABASE_URL is set the factory returns this implementation,
which raises NotImplementedError on every call with an actionable message.
Full implementation (asyncpg / SQLAlchemy async) is scheduled for Sprint 7.
"""

from __future__ import annotations

import logging
import os

from services._config_repo_base import ConfigRepository

logger = logging.getLogger(__name__)


class PostgresConfigRepository(ConfigRepository):
    """Postgres-backed config repository — stub for Sprint 7.

    To activate: set DATABASE_URL=postgresql+asyncpg://user:pass@host/db
    and implement the schema + asyncpg pool in Sprint 7.
    """

    def __init__(self) -> None:
        url = os.environ.get("DATABASE_URL", "")
        logger.info(
            "PostgresConfigRepository: stub active (DATABASE_URL=%s…). "
            "Full implementation scheduled for Sprint 7.",
            url[:30] if url else "<unset>",
        )

    def _not_implemented(self, operation: str, key: str = "") -> None:
        detail = f" (key={key!r})" if key else ""
        raise NotImplementedError(
            f"PostgresConfigRepository.{operation} is a Sprint 7 stub{detail}. "
            "Install asyncpg, create the config table, and wire the async pool "
            "before enabling this backend."
        )

    async def get_config(self, key: str) -> dict:
        self._not_implemented("get_config", key)
        return {}

    async def set_config(self, key: str, value: dict) -> bool:
        self._not_implemented("set_config", key)
        return False

    async def get_all(self) -> dict:
        self._not_implemented("get_all")
        return {}

    async def delete_config(self, key: str) -> bool:
        self._not_implemented("delete_config", key)
        return False
