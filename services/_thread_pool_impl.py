"""ThreadPoolManager implementation — internal module.

Public API: services.thread_pool_manager.get_thread_pool_manager()
"""

from __future__ import annotations

import logging
import os
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Callable

logger = logging.getLogger(__name__)


def _optimal_workers(multiplier: float, cap: int) -> int:
    """Return min(cap, cpu_count * multiplier + 1).

    Falls back to 4 if os.cpu_count() is None (some container runtimes).
    """
    cpu = os.cpu_count() or 4
    return min(cap, int(cpu * multiplier) + 1)


# Pool specs: (name, workers_multiplier, worker_cap)
_POOL_SPECS: list[tuple[str, float, int]] = [
    ("pipeline_pool", 3.0, 32),
    ("scoring_pool",  2.0, 16),
    ("general_pool",  1.0,  8),
]


class ThreadPoolManager:
    """Singleton manager for named ThreadPoolExecutors.

    Each pool is auto-sized based on CPU count and tracks active tasks
    for utilisation logging/monitoring.
    """

    _instance: "ThreadPoolManager | None" = None
    _singleton_lock = threading.Lock()

    def __new__(cls) -> "ThreadPoolManager":
        if cls._instance is not None:
            return cls._instance
        with cls._singleton_lock:
            if cls._instance is not None:
                return cls._instance
            inst = super().__new__(cls)
            inst._initialized = False
            cls._instance = inst
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        self._pools: dict[str, ThreadPoolExecutor] = {}
        self._active_counts: dict[str, int] = {}
        self._counts_lock = threading.Lock()
        self._shutdown_called = False
        self._build_pools()

    # ------------------------------------------------------------------
    # Pool lifecycle
    # ------------------------------------------------------------------

    def _build_pools(self) -> None:
        for name, multiplier, cap in _POOL_SPECS:
            workers = _optimal_workers(multiplier, cap)
            self._pools[name] = ThreadPoolExecutor(
                max_workers=workers, thread_name_prefix=name
            )
            self._active_counts[name] = 0
            logger.info("thread_pool: %r created — max_workers=%d", name, workers)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_pool(self, name: str) -> ThreadPoolExecutor:
        """Return the named ThreadPoolExecutor.

        Raises KeyError for unknown pool names.
        """
        try:
            return self._pools[name]
        except KeyError:
            raise KeyError(
                f"Unknown pool {name!r}. Available: {list(self._pools)}"
            ) from None

    def submit(self, pool_name: str, fn: Callable, *args: Any, **kwargs: Any) -> Future:
        """Submit callable to named pool; return its Future.

        Tracks active-task count; decrements via done callback.

        Raises:
            KeyError:     Pool name not recognised.
            RuntimeError: Manager has been shut down.
        """
        if self._shutdown_called:
            raise RuntimeError("ThreadPoolManager shut down; cannot submit new tasks.")

        pool = self.get_pool(pool_name)
        with self._counts_lock:
            self._active_counts[pool_name] += 1

        future = pool.submit(fn, *args, **kwargs)
        future.add_done_callback(self._make_done_cb(pool_name))
        self._log_utilisation(pool_name)
        return future

    def _make_done_cb(self, pool_name: str) -> Callable[[Future], None]:
        def _cb(f: Future) -> None:
            with self._counts_lock:
                self._active_counts[pool_name] = max(0, self._active_counts[pool_name] - 1)
            if f.exception():
                logger.debug("thread_pool: task in %r raised %s", pool_name, f.exception())
            logger.debug(
                "thread_pool: %r active=%d after task complete",
                pool_name, self._active_counts[pool_name]
            )
        return _cb

    def active_count(self, pool_name: str) -> int:
        """Return count of running/pending tasks for the named pool."""
        with self._counts_lock:
            return self._active_counts.get(pool_name, 0)

    def utilisation_summary(self) -> dict[str, dict]:
        """Snapshot of all pools: max_workers + active_tasks."""
        with self._counts_lock:
            return {
                name: {
                    "max_workers": pool._max_workers,  # type: ignore[attr-defined]
                    "active_tasks": self._active_counts[name],
                }
                for name, pool in self._pools.items()
            }

    def shutdown_all(self, wait: bool = True) -> None:
        """Gracefully shut down all pools."""
        if self._shutdown_called:
            return
        self._shutdown_called = True
        logger.info("thread_pool: shutting down all pools (wait=%s)", wait)
        for name, pool in self._pools.items():
            try:
                pool.shutdown(wait=wait)
                logger.info("thread_pool: %r shut down", name)
            except Exception as exc:
                logger.warning("thread_pool: error shutting down %r — %s", name, exc)

    def _log_utilisation(self, pool_name: str) -> None:
        with self._counts_lock:
            active = self._active_counts[pool_name]
        max_w = self._pools[pool_name]._max_workers  # type: ignore[attr-defined]
        pct = (active / max_w * 100) if max_w else 0
        logger.debug("thread_pool: %r util=%d/%d (%.0f%%)", pool_name, active, max_w, pct)

    def __repr__(self) -> str:
        with self._counts_lock:
            active = dict(self._active_counts)
        return f"<ThreadPoolManager pools={list(self._pools)} active={active}>"
