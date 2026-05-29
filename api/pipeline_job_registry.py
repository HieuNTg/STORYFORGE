"""Process-level registry of long-running pipeline jobs.

Decouples pipeline execution from SSE connection lifecycle. When the SSE
client disconnects, the underlying job keeps running and persists its
final result into the registry. The frontend can then recover the draft
via `GET /api/pipeline/run/{session_id}` even if the live stream was lost.

Why this exists: `asyncio.to_thread(generate_full_story, ...)` cannot be
cancelled — the worker thread keeps running after `task.cancel()`. If the
SSE drop also cancelled the task, the L1 worker would still complete ~9
minutes later, return a draft, and the result would be silently dropped
because the awaiting coroutine no longer exists. With this registry, the
task survives SSE drops; only the SSE viewer closes.
"""

from __future__ import annotations

import asyncio
import logging
import queue as _queue
import time
from dataclasses import dataclass, field
from typing import Any, Literal, Optional

logger = logging.getLogger(__name__)

JobStatus = Literal["pending", "running", "done", "error", "cancelled"]


@dataclass
class PipelineJob:
    """Long-lived record of a single pipeline execution.

    Lives in the module-level JOBS dict, keyed by `session_id`. Held until
    `JOB_RETENTION_SECONDS` after completion so the FE has a window to poll
    the final result after losing its SSE connection.
    """

    session_id: str
    progress_queue: _queue.Queue = field(default_factory=_queue.Queue)
    logs: list[str] = field(default_factory=list)
    status: JobStatus = "pending"
    summary: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    task: Optional[asyncio.Task] = None
    # Held loosely (Any) to avoid importing pipeline.* into api.* and risking
    # circular imports. Cast at the call site if you need the methods.
    orchestrator: Optional[Any] = None
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    # 'run' for fresh pipeline, 'resume' for continuation. Lets reaper /
    # observers tell the two apart if needed.
    kind: str = "run"
    # Set True by the SSE streamer when the client disconnects. The worker's
    # progress callbacks check it and stop enqueueing into progress_queue so an
    # abandoned job (which keeps running ~9 min) cannot grow the queue without
    # bound (H4). `logs` keeps accumulating regardless, so recovery via the poll
    # endpoint still sees the full progress history.
    disconnected: bool = False


JOBS: dict[str, PipelineJob] = {}
_JOBS_LOCK = asyncio.Lock()

JOB_RETENTION_SECONDS = 3600  # keep completed jobs available 1h for polling
_JOB_REAPER_INTERVAL = 300


async def register(session_id: str, kind: str = "run") -> PipelineJob:
    """Create and store a new job record. Returns the registered PipelineJob."""
    async with _JOBS_LOCK:
        job = PipelineJob(session_id=session_id, kind=kind, status="running")
        JOBS[session_id] = job
        return job


def get(session_id: str) -> Optional[PipelineJob]:
    """Read-only lookup; safe to call from any context."""
    return JOBS.get(session_id)


async def mark_done(
    session_id: str,
    summary: Optional[dict] = None,
    error: Optional[str] = None,
    status: Optional[JobStatus] = None,
) -> None:
    """Persist the final state of a job.

    `status` lets callers set a terminal state explicitly (e.g. "cancelled");
    when omitted it is inferred from `error` ("error" if present, else "done").

    Field-write order matters: `summary`/`error`/`completed_at` are written
    BEFORE the `status` flip. `get_run_status` reads job fields without the
    lock, so a reader must never observe a terminal status while `summary` is
    still None. Writing status last makes the transition atomic from the
    reader's point of view (it sees either the old non-terminal state or the
    fully-populated terminal state — never a torn in-between).
    """
    async with _JOBS_LOCK:
        job = JOBS.get(session_id)
        if job is None:
            return
        resolved: JobStatus = status or ("error" if error else "done")
        job.summary = summary
        job.error = error
        job.completed_at = time.time()
        job.status = resolved  # flip last — see docstring


def mark_terminal_sync(
    session_id: str,
    error: Optional[str] = "Worker exited without reporting a result.",
    status: JobStatus = "error",
) -> None:
    """Best-effort sync fallback for a `task.add_done_callback`.

    If a worker task finishes (or is GC'd) without its `finally` ever calling
    `mark_done`, the job would otherwise stay `running` forever. Done-callbacks
    run synchronously on the event-loop thread where the async `_JOBS_LOCK`
    cannot be awaited, so this mutates the record directly. It is a last-resort
    write on a single field set; it NO-OPS if the job is already terminal — so
    in the normal path (where `_run_async`'s finally already called mark_done)
    this does nothing.
    """
    job = JOBS.get(session_id)
    if job is None or job.status in ("done", "error", "cancelled"):
        return
    job.error = error
    job.completed_at = time.time()
    job.status = status  # flip last (torn-read discipline)


def _should_evict(job: "PipelineJob", now: float) -> bool:
    """Whether the reaper should drop this job (pure predicate — unit-testable).

    Two cases:
    * Normal retention — a terminal job kept past its polling window.
    * Stuck-running guard (H2) — a job whose worker exited without ever calling
      mark_done leaves completed_at=None, so the retention rule never fires and
      it would leak as `running` forever. Evict once it is older than the
      retention window AND its task is no longer alive (done, or never attached).
    """
    if (
        job.completed_at is not None
        and (now - job.completed_at) > JOB_RETENTION_SECONDS
    ):
        return True
    if (
        job.completed_at is None
        and (now - job.created_at) > JOB_RETENTION_SECONDS
        and (job.task is None or job.task.done())
    ):
        return True
    return False


async def _job_reaper():
    while True:
        await asyncio.sleep(_JOB_REAPER_INTERVAL)
        now = time.time()
        async with _JOBS_LOCK:
            expired = [sid for sid, j in JOBS.items() if _should_evict(j, now)]
            for sid in expired:
                JOBS.pop(sid, None)
        if expired:
            logger.debug("Job reaper evicted %d job(s)", len(expired))


# Strong reference to the reaper task so it isn't garbage-collected mid-flight
# (asyncio only holds a weak ref to fire-and-forget tasks — H1).
_reaper_task: Optional[asyncio.Task] = None


def start_job_reaper() -> "asyncio.Task":
    """Launch the retention reaper. Call from app lifespan startup."""
    global _reaper_task
    _reaper_task = asyncio.create_task(_job_reaper())
    return _reaper_task


async def shutdown_job_reaper() -> None:
    """Cancel and await the reaper task for a clean shutdown (no pending-task
    warnings). Safe to call when the reaper was never started."""
    global _reaper_task
    task = _reaper_task
    if task is None:
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    except Exception:
        logger.exception("Job reaper raised during shutdown (ignored)")
    finally:
        _reaper_task = None
