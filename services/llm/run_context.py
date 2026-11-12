"""Ambient per-run context that survives thread hops.

``current_run_id`` names the pipeline run that LLM costs are charged to. A
``ContextVar`` follows ``await`` and ``asyncio.gather`` for free, but a plain
``loop.run_in_executor`` worker or a fresh ``threading.Thread`` starts with an
empty context — the run id is lost and the charge would land nowhere (or, in
the past, on whichever run reset its wallet last). The helpers here are the
sanctioned ways to hop threads without dropping the run.
"""

from __future__ import annotations

import asyncio
import contextvars
import functools
import threading
from concurrent.futures import Executor, Future
from typing import Any, Callable

current_run_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "current_run_id", default=""
)


async def run_in_thread(fn: Callable[..., Any], /, *args: Any, **kwargs: Any) -> Any:
    """Run ``fn(*args, **kwargs)`` in the default thread pool with this context.

    Thin wrapper over ``asyncio.to_thread``, which copies the caller's context
    into the worker — unlike ``loop.run_in_executor(None, fn, *args)``.
    """
    if kwargs:
        fn = functools.partial(fn, **kwargs)
    return await asyncio.to_thread(fn, *args)


def spawn_with_context(target: Callable[..., Any], *args: Any) -> threading.Thread:
    """Start a daemon thread running ``target(*args)`` inside a copy of this context."""
    ctx = contextvars.copy_context()
    thread = threading.Thread(target=ctx.run, args=(target, *args), daemon=True)
    thread.start()
    return thread


def submit_with_context(
    executor: Executor, fn: Callable[..., Any], /, *args: Any, **kwargs: Any
) -> Future:
    """``executor.submit`` that runs ``fn`` inside a copy of this context.

    Each call takes its own copy: one ``Context`` cannot be entered by two
    threads at once.
    """
    return executor.submit(contextvars.copy_context().run, fn, *args, **kwargs)
