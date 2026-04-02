"""Auto-scaling ThreadPoolExecutor manager for StoryForge.

Provides a singleton ThreadPoolManager with named pools tuned for
different workloads:
  - pipeline_pool:  IO-bound chapter writing (3× CPU, max 32 workers)
  - scoring_pool:   IO-bound quality scoring  (2× CPU, max 16 workers)
  - general_pool:   Miscellaneous tasks       (1× CPU, max  8 workers)

Usage:
    from services.thread_pool_manager import get_thread_pool_manager

    mgr = get_thread_pool_manager()
    future = mgr.submit("pipeline_pool", my_function, arg1, arg2)
    result = future.result()

    # Or access the executor directly:
    pool = mgr.get_pool("pipeline_pool")
    pool.submit(fn, arg)

Implementation details in _thread_pool_impl.py.
"""

from __future__ import annotations

from services._thread_pool_impl import ThreadPoolManager


def get_thread_pool_manager() -> ThreadPoolManager:
    """Return the singleton ThreadPoolManager instance.

    Safe to call from any thread; initialisation is idempotent.
    """
    return ThreadPoolManager()


__all__ = ["ThreadPoolManager", "get_thread_pool_manager"]
