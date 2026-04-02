"""JsonFileConfigRepository — thread-safe JSON file backend.

Internal module; public API is via services.config_repository.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import tempfile
import threading
from pathlib import Path

from services._config_repo_base import ConfigRepository

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Platform-specific file locking
# ---------------------------------------------------------------------------

if sys.platform == "win32":
    import msvcrt as _lock_mod

    def _lock(fp) -> None:
        _lock_mod.locking(fp.fileno(), _lock_mod.LK_NBLCK, 1)  # type: ignore

    def _unlock(fp) -> None:
        _lock_mod.locking(fp.fileno(), _lock_mod.LK_UNLCK, 1)  # type: ignore

else:
    import fcntl as _lock_mod  # type: ignore[no-redef]

    def _lock(fp) -> None:
        _lock_mod.flock(fp.fileno(), _lock_mod.LOCK_EX)  # type: ignore

    def _unlock(fp) -> None:
        _lock_mod.flock(fp.fileno(), _lock_mod.LOCK_UN)  # type: ignore


# ---------------------------------------------------------------------------
# Implementation
# ---------------------------------------------------------------------------

class JsonFileConfigRepository(ConfigRepository):
    """Thread-safe, atomically-written JSON file backend.

    Writes go through write-to-temp + atomic rename to prevent partial writes.
    An in-process threading.Lock serialises async calls within one process.
    """

    def __init__(self, config_file: str = "data/config.json") -> None:
        self._path = Path(config_file)
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _read_raw(self) -> dict:
        if not self._path.exists():
            return {}
        try:
            with open(self._path, "r", encoding="utf-8") as fp:
                return json.load(fp)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("JsonFileConfigRepository: read error %s", exc)
            return {}

    def _write_raw(self, data: dict) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=str(self._path.parent),
            delete=False, suffix=".tmp"
        ) as tmp:
            json.dump(data, tmp, ensure_ascii=False, indent=2)
            tmp_name = tmp.name
        os.replace(tmp_name, str(self._path))

    @staticmethod
    def _get_nested(data: dict, key: str) -> dict:
        node = data
        for part in key.split("."):
            if not isinstance(node, dict) or part not in node:
                return {}
            node = node[part]
        return node if isinstance(node, dict) else {}

    @staticmethod
    def _set_nested(data: dict, key: str, value: dict) -> None:
        parts = key.split(".")
        node = data
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value

    @staticmethod
    def _delete_nested(data: dict, key: str) -> bool:
        parts = key.split(".")
        node = data
        for part in parts[:-1]:
            if not isinstance(node, dict) or part not in node:
                return False
            node = node[part]
        if not isinstance(node, dict) or parts[-1] not in node:
            return False
        del node[parts[-1]]
        return True

    # ------------------------------------------------------------------
    # Sync internals (run in executor)
    # ------------------------------------------------------------------

    def _sync_get(self, key: str) -> dict:
        with self._lock:
            return self._get_nested(self._read_raw(), key)

    def _sync_set(self, key: str, value: dict) -> bool:
        try:
            with self._lock:
                data = self._read_raw()
                self._set_nested(data, key, value)
                self._write_raw(data)
            return True
        except OSError as exc:
            logger.error("JsonFileConfigRepository: write error %s", exc)
            return False

    def _sync_get_all(self) -> dict:
        with self._lock:
            return self._read_raw()

    def _sync_delete(self, key: str) -> bool:
        with self._lock:
            data = self._read_raw()
            existed = self._delete_nested(data, key)
            if existed:
                self._write_raw(data)
            return existed

    # ------------------------------------------------------------------
    # Async public interface
    # ------------------------------------------------------------------

    async def get_config(self, key: str) -> dict:
        # Sync helpers use threading.Lock; offload to default executor to avoid blocking the event loop.
        # NOTE: ThreadPoolExecutor kept intentionally — underlying I/O uses threading.Lock which cannot
        # be replaced with aiofiles without removing the cross-process file lock semantics.
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._sync_get, key)

    async def set_config(self, key: str, value: dict) -> bool:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._sync_set, key, value)

    async def get_all(self) -> dict:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._sync_get_all)

    async def delete_config(self, key: str) -> bool:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._sync_delete, key)
