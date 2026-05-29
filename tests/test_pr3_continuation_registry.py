"""PR-3 regression tests — continuation job-registry migration + C4 branch stream.

Guards the bugs the SSE re-review (2026-05-29) found in the continuation /
branch streaming paths:

* C3 — the 4 continuation generators ran their LLM work on a coroutine that was
        cancelled on SSE disconnect, silently discarding a ~minutes-long result.
        They now register in the job-registry and persist their terminal state
        via ``finalize_job`` so a disconnected client can recover the draft.
* C4 — ``/choose/stream`` ran the blocking LLM inline (no heartbeat, no
        disconnect detection) and abandoned the generation on disconnect. It now
        runs the LLM in a worker thread feeding a queue, heartbeats while idle,
        and STILL persists the generated node on disconnect (so a retry hits the
        cached path).
* H4 — after disconnect the worker kept enqueueing into an undrained queue,
        growing it without bound. ``make_progress_callbacks`` now stops
        enqueueing once ``job.disconnected`` is set (but keeps appending to
        ``job.logs`` for recovery).
* #15 — checkpoint writes were non-atomic: a crash mid-write left a torn JSON
        file. ``_atomic_write_text`` writes to a sibling tmp then ``os.replace``.
"""

import json
import os

import pytest

import api.pipeline_job_registry as reg
from api.pipeline_job_registry import PipelineJob


@pytest.fixture(autouse=True)
def _clean_jobs():
    reg.JOBS.clear()
    yield
    reg.JOBS.clear()


# --- H4: progress callbacks stop enqueueing after disconnect ----------------

def test_on_progress_enqueues_while_connected():
    from api.pipeline_routes import make_progress_callbacks

    job = PipelineJob(session_id="s")
    on_progress, _ = make_progress_callbacks(job)
    on_progress("line-1")
    on_progress("line-2")

    # Both logged AND enqueued while connected.
    assert job.logs == ["line-1", "line-2"]
    assert job.progress_queue.qsize() == 2


def test_on_progress_logs_but_does_not_enqueue_after_disconnect():
    """H4: the abandoned-job queue must not grow once the client is gone, but
    logs must keep accumulating so the poll endpoint can recover full progress."""
    from api.pipeline_routes import make_progress_callbacks

    job = PipelineJob(session_id="s")
    on_progress, _ = make_progress_callbacks(job)

    on_progress("before")
    job.disconnected = True
    on_progress("after-1")
    on_progress("after-2")

    # logs keep everything; queue froze at the pre-disconnect count.
    assert job.logs == ["before", "after-1", "after-2"]
    assert job.progress_queue.qsize() == 1


def test_on_stream_stops_after_disconnect():
    from api.pipeline_routes import make_progress_callbacks

    # stream_interval=0 so the first connected call is never throttled out.
    job = PipelineJob(session_id="s")
    _, on_stream = make_progress_callbacks(job, stream_interval=0.0)

    on_stream("<p>partial</p>")
    enqueued_connected = job.progress_queue.qsize()
    job.disconnected = True
    on_stream("<p>more</p>")

    assert enqueued_connected == 1
    # No additional frame enqueued after disconnect.
    assert job.progress_queue.qsize() == 1


# --- C3: finalize_job persists the terminal state for recovery --------------

@pytest.mark.asyncio
async def test_finalize_job_success_records_done_with_summary(monkeypatch):
    """A completed continuation must land as `done` with a recoverable summary
    carrying session_id + the full logs (this is what the poll endpoint serves)."""
    import api.pipeline_output_builder as builder
    from api.pipeline_routes import finalize_job

    monkeypatch.setattr(builder, "build_output_summary", lambda out: {"title": "T"})

    class _FakeOutput:
        status = "ok"

        def model_copy(self, deep=False):
            return self

    job = PipelineJob(session_id="s", status="running")
    job.logs = ["[OUTLINE] done", "[CHAPTER 1] done"]
    reg.JOBS["s"] = job

    await finalize_job(
        "s", job, _FakeOutput(), caught_error=None, was_cancelled=False
    )

    assert job.status == "done"
    assert job.summary["session_id"] == "s"
    assert job.summary["logs"] == ["[OUTLINE] done", "[CHAPTER 1] done"]
    assert job.error is None


@pytest.mark.asyncio
async def test_finalize_job_cancelled_records_cancelled():
    from api.pipeline_routes import finalize_job

    job = PipelineJob(session_id="s", status="running")
    reg.JOBS["s"] = job

    await finalize_job(
        "s", job, None, caught_error=None, was_cancelled=True,
        cancelled_msg="Continuation was cancelled.",
    )

    assert job.status == "cancelled"
    assert job.error == "Continuation was cancelled."


@pytest.mark.asyncio
async def test_finalize_job_no_output_records_error():
    from api.pipeline_routes import finalize_job

    job = PipelineJob(session_id="s", status="running")
    reg.JOBS["s"] = job

    await finalize_job(
        "s", job, None, caught_error="Network error. Please try again.",
        was_cancelled=False,
    )

    assert job.status == "error"
    assert job.error == "Network error. Please try again."


@pytest.mark.asyncio
async def test_finalize_job_error_output_surfaces_real_reason():
    """An output whose own status is 'error' must surface the logged cause, not a
    generic message (H3 contract, reused by the migrated continuation path)."""
    from api.pipeline_routes import finalize_job

    class _ErrOutput:
        status = "error"
        logs = ["[OUTLINE] ...", "LLM hết hạn mức: quota exceeded"]

    job = PipelineJob(session_id="s", status="running")
    reg.JOBS["s"] = job

    await finalize_job(
        "s", job, _ErrOutput(), caught_error=None, was_cancelled=False
    )

    assert job.status == "error"
    assert job.error == "LLM hết hạn mức: quota exceeded"


# --- #15: atomic checkpoint write -------------------------------------------

def test_atomic_write_creates_complete_file_and_no_tmp(tmp_path):
    from pipeline.orchestrator_checkpoint import _atomic_write_text

    target = os.path.join(str(tmp_path), "ckpt.json")
    _atomic_write_text(target, '{"a": 1}')

    with open(target, encoding="utf-8") as f:
        assert json.load(f) == {"a": 1}
    # No leftover tmp sibling.
    leftovers = [n for n in os.listdir(str(tmp_path)) if n.endswith(".tmp")]
    assert leftovers == []


def test_atomic_write_overwrites_existing_atomically(tmp_path):
    from pipeline.orchestrator_checkpoint import _atomic_write_text

    target = os.path.join(str(tmp_path), "ckpt.json")
    _atomic_write_text(target, '{"v": 1}')
    _atomic_write_text(target, '{"v": 2}')

    with open(target, encoding="utf-8") as f:
        assert json.load(f) == {"v": 2}


def test_atomic_write_cleans_tmp_on_failure(tmp_path, monkeypatch):
    """If the rename fails, the partial tmp must not be left behind and the error
    must propagate (so the caller's `Checkpoint save failed` log fires)."""
    import pipeline.orchestrator_checkpoint as ckpt

    target = os.path.join(str(tmp_path), "ckpt.json")

    def _boom(src, dst):
        raise OSError("rename failed")

    monkeypatch.setattr(ckpt.os, "replace", _boom)

    with pytest.raises(OSError):
        ckpt._atomic_write_text(target, '{"a": 1}')

    # tmp cleaned up, final never created.
    assert not os.path.exists(target)
    leftovers = [n for n in os.listdir(str(tmp_path)) if n.endswith(".tmp")]
    assert leftovers == []


def test_checkpoint_save_writes_atomically(tmp_path, monkeypatch):
    """End-to-end: CheckpointManager.save(background=False) yields a complete,
    readable JSON file and leaves no .tmp sibling."""
    import pipeline.orchestrator_checkpoint as ckpt
    from pipeline.orchestrator_checkpoint import CheckpointManager
    from models.schemas import PipelineOutput

    monkeypatch.setattr(ckpt, "CHECKPOINT_DIR", str(tmp_path))
    output = PipelineOutput()
    mgr = CheckpointManager(output, None, None, None)

    path = mgr.save(layer=1, background=False)

    assert os.path.exists(path)
    with open(path, encoding="utf-8") as f:
        json.load(f)  # parses → not torn
    leftovers = [n for n in os.listdir(str(tmp_path)) if n.endswith(".tmp")]
    assert leftovers == []


# --- C4: /choose/stream threaded producer + disconnect-persist --------------

class _FakeRequest:
    def __init__(self, disconnected: bool = False):
        self._disconnected = disconnected

    async def is_disconnected(self) -> bool:
        return self._disconnected


class _FakeLLM:
    def __init__(self, chunks):
        self._chunks = chunks

    def generate_stream(self, system_prompt, user_prompt, temperature):
        for c in self._chunks:
            yield c


def _make_manager(monkeypatch):
    from unittest.mock import MagicMock

    mgr = MagicMock()
    mgr.choose_branch.return_value = None  # force generation
    mgr.get_current_node.return_value = {
        "choices": ["go left", "go right"],
        "text": "story so far",
        "depth": 0,
    }
    mgr.get_context.return_value = {"genre": "fantasy", "language": "vi"}
    mgr.get_node_states.return_value = {}
    mgr.get_path_summary.return_value = "path summary"
    mgr.add_generated_node.return_value = {"id": "n1", "text": "next part"}
    monkeypatch.setattr("api.branch_routes.manager", mgr)
    return mgr


async def _collect(resp):
    return [frame async for frame in resp.body_iterator]


@pytest.mark.asyncio
async def test_choose_stream_happy_path_streams_and_persists(monkeypatch):
    import api.branch_routes as br

    mgr = _make_manager(monkeypatch)
    payload = json.dumps(
        {"continuation": "next part", "choices": ["a", "b"], "character_states": {}}
    )
    # Split the JSON across chunks to exercise accumulation.
    monkeypatch.setattr(br, "llm", _FakeLLM([payload[:10], payload[10:]]))

    resp = await br.choose_branch_stream(
        _FakeRequest(disconnected=False), "sess", br.ChooseBody(choice_index=0)
    )
    frames = await _collect(resp)
    blob = "".join(frames)

    assert '"type": "chunk"' in blob
    assert '"type": "complete"' in blob
    assert '"generated": true' in blob
    mgr.add_generated_node.assert_called_once()


@pytest.mark.asyncio
async def test_choose_stream_persists_node_even_when_disconnected(monkeypatch):
    """C4 core guarantee: on disconnect we emit NO further frames but STILL
    persist the generated node, so a retry hits the cached path."""
    import api.branch_routes as br

    mgr = _make_manager(monkeypatch)
    payload = json.dumps(
        {"continuation": "next part", "choices": ["a", "b"], "character_states": {}}
    )
    monkeypatch.setattr(br, "llm", _FakeLLM([payload]))

    resp = await br.choose_branch_stream(
        _FakeRequest(disconnected=True), "sess", br.ChooseBody(choice_index=0)
    )
    frames = await _collect(resp)

    # Disconnected → no SSE frames delivered to the (gone) client …
    assert frames == []
    # … but the node was persisted anyway.
    mgr.add_generated_node.assert_called_once()


@pytest.mark.asyncio
async def test_choose_stream_cached_path_returns_without_generation(monkeypatch):
    """When the branch already exists, no LLM generation runs and a single
    `complete` frame with generated:false is returned."""
    import api.branch_routes as br
    from unittest.mock import MagicMock

    mgr = MagicMock()
    mgr.choose_branch.return_value = {"id": "cached", "text": "already here"}
    monkeypatch.setattr("api.branch_routes.manager", mgr)
    # If generation were attempted this would explode (no generate_stream set up).
    monkeypatch.setattr(br, "llm", object())

    resp = await br.choose_branch_stream(
        _FakeRequest(disconnected=False), "sess", br.ChooseBody(choice_index=0)
    )
    frames = await _collect(resp)
    blob = "".join(frames)

    assert '"generated": false' in blob
    mgr.add_generated_node.assert_not_called()
