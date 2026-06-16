"""PR-2 regression tests — job-registry lifecycle.

Guards the registry-side bugs found in the SSE re-review (2026-05-29):

* H2  — a job whose worker exits without calling mark_done leaks as `running`
        forever because the reaper only evicted on completed_at age.
* M-cancelled — mark_done could not record a `cancelled` terminal state, so
        cancelled runs were mislabelled `error`.
* M-lock — torn read: status flipped to terminal before summary was written,
        so a lock-free reader could see `done` with summary=None.
* Belt — mark_terminal_sync force-marks a stuck job terminal from a
        done-callback and no-ops when the job is already terminal.
"""

import time

import pytest

import api.pipeline_job_registry as reg
from api.pipeline_job_registry import PipelineJob, JOB_RETENTION_SECONDS


@pytest.fixture(autouse=True)
def _clean_jobs():
    reg.JOBS.clear()
    yield
    reg.JOBS.clear()


class _DoneTask:
    """Minimal asyncio.Task stand-in for reaper predicate tests."""

    def __init__(self, done: bool):
        self._done = done

    def done(self) -> bool:
        return self._done


# --- H2: stuck-running eviction (pure predicate) ----------------------------


def test_should_evict_terminal_past_retention():
    now = time.time()
    job = PipelineJob(session_id="s", status="done")
    job.completed_at = now - JOB_RETENTION_SECONDS - 1
    assert reg._should_evict(job, now) is True


def test_should_keep_terminal_within_retention():
    now = time.time()
    job = PipelineJob(session_id="s", status="done")
    job.completed_at = now - 10
    assert reg._should_evict(job, now) is False


def test_should_evict_stuck_running_with_dead_task():
    """H2: completed_at never set, old, task finished -> evict."""
    now = time.time()
    job = PipelineJob(session_id="s", status="running")
    job.created_at = now - JOB_RETENTION_SECONDS - 1
    job.task = _DoneTask(done=True)
    assert reg._should_evict(job, now) is True


def test_should_keep_running_with_live_task_even_if_old():
    """A genuinely long-running job (task still alive) must NOT be evicted."""
    now = time.time()
    job = PipelineJob(session_id="s", status="running")
    job.created_at = now - JOB_RETENTION_SECONDS - 1
    job.task = _DoneTask(done=False)
    assert reg._should_evict(job, now) is False


def test_should_keep_recent_stuck_running():
    """Young stuck job stays until it ages past the retention window."""
    now = time.time()
    job = PipelineJob(session_id="s", status="running")
    job.created_at = now - 10
    job.task = None
    assert reg._should_evict(job, now) is False


# --- M-cancelled + M-lock: mark_done -----------------------------------------


@pytest.mark.asyncio
async def test_mark_done_explicit_cancelled_status():
    reg.JOBS["s"] = PipelineJob(session_id="s", status="running")
    await reg.mark_done("s", status="cancelled", error="Run was cancelled.")
    job = reg.JOBS["s"]
    assert job.status == "cancelled"
    assert job.error == "Run was cancelled."
    assert job.completed_at is not None


@pytest.mark.asyncio
async def test_mark_done_infers_done_without_error():
    reg.JOBS["s"] = PipelineJob(session_id="s", status="running")
    await reg.mark_done("s", summary={"title": "x"})
    job = reg.JOBS["s"]
    assert job.status == "done"
    assert job.summary == {"title": "x"}
    assert job.error is None


@pytest.mark.asyncio
async def test_mark_done_infers_error_when_error_present():
    reg.JOBS["s"] = PipelineJob(session_id="s", status="running")
    await reg.mark_done("s", error="boom")
    assert reg.JOBS["s"].status == "error"


@pytest.mark.asyncio
async def test_mark_done_writes_status_last(monkeypatch):
    """M-lock: the status flip must happen AFTER summary/error/completed_at are
    written, so a lock-free reader never sees a terminal status with no summary.

    We prove the write order by recording the job's field values at the moment
    `status` is assigned — via a recording subclass that intercepts `status`.
    """
    snapshots: list[dict] = []

    class _RecordingJob(PipelineJob):
        @property
        def status(self):
            return self.__dict__.get("_status", "pending")

        @status.setter
        def status(self, value):
            # Snapshot the sibling fields at the instant status is written.
            snapshots.append(
                {
                    "status": value,
                    "summary": self.__dict__.get("summary"),
                    "completed_at": self.__dict__.get("completed_at"),
                }
            )
            self.__dict__["_status"] = value

    job = _RecordingJob(session_id="s")
    job.status = "running"  # initial (recorded, ignored below)
    snapshots.clear()
    reg.JOBS["s"] = job

    await reg.mark_done("s", summary={"k": "v"})

    # The terminal flip must carry a populated summary + completed_at.
    terminal = [s for s in snapshots if s["status"] == "done"]
    assert terminal, "status was never flipped to done"
    assert terminal[0]["summary"] == {"k": "v"}
    assert terminal[0]["completed_at"] is not None


@pytest.mark.asyncio
async def test_mark_done_missing_job_is_noop():
    await reg.mark_done("nope", summary={"x": 1})  # must not raise
    assert "nope" not in reg.JOBS


# --- Belt: mark_terminal_sync ------------------------------------------------


def test_mark_terminal_sync_forces_running_job_terminal():
    reg.JOBS["s"] = PipelineJob(session_id="s", status="running")
    reg.mark_terminal_sync("s", error="Worker crashed unexpectedly.")
    job = reg.JOBS["s"]
    assert job.status == "error"
    assert job.error == "Worker crashed unexpectedly."
    assert job.completed_at is not None


def test_mark_terminal_sync_cancelled_status():
    reg.JOBS["s"] = PipelineJob(session_id="s", status="running")
    reg.mark_terminal_sync("s", error="Run was cancelled.", status="cancelled")
    assert reg.JOBS["s"].status == "cancelled"


def test_mark_terminal_sync_noop_when_already_terminal():
    """Normal path: finally already marked the job done — belt must not clobber."""
    reg.JOBS["s"] = PipelineJob(session_id="s", status="done", summary={"title": "ok"})
    reg.mark_terminal_sync("s", error="should be ignored")
    job = reg.JOBS["s"]
    assert job.status == "done"
    assert job.summary == {"title": "ok"}
    assert job.error is None


def test_mark_terminal_sync_missing_job_is_noop():
    reg.mark_terminal_sync("nope")  # must not raise
    assert "nope" not in reg.JOBS
