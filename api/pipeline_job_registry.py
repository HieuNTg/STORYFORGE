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
) -> None:
    """Flip status to 'done' or 'error' and stash the final summary."""
    async with _JOBS_LOCK:
        job = JOBS.get(session_id)
        if job is None:
            return
        job.status = "error" if error else "done"
        job.summary = summary
        job.error = error
        job.completed_at = time.time()


async def _job_reaper():
    while True:
        await asyncio.sleep(_JOB_REAPER_INTERVAL)
        now = time.time()
        async with _JOBS_LOCK:
            expired = [
                sid
                for sid, j in JOBS.items()
                if j.completed_at is not None
                and (now - j.completed_at) > JOB_RETENTION_SECONDS
            ]
            for sid in expired:
                JOBS.pop(sid, None)
        if expired:
            logger.debug("Job reaper evicted %d completed job(s)", len(expired))


def start_job_reaper():
    """Launch the retention reaper. Call from app lifespan startup."""
    asyncio.create_task(_job_reaper())
