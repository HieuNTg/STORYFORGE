"""Pipeline API routes — run pipeline via SSE, get genres/templates/checkpoints."""

import asyncio
import inspect
import json
import logging
import queue as _queue
import os
import time
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from models.schemas import normalize_drama as _normalize_drama

from middleware.rbac import Permission, require_permission_if_enabled
from services.i18n import I18n
from services.text_utils import sanitize_story_html
from pipeline.orchestrator import PipelineOrchestrator
from api import pipeline_job_registry as _jobs

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/pipeline", tags=["pipeline"])
_READ_STORIES = Depends(require_permission_if_enabled(Permission.READ_STORIES))
_CREATE_STORIES = Depends(require_permission_if_enabled(Permission.CREATE_STORIES))
_DELETE_ANY_STORIES = Depends(require_permission_if_enabled(Permission.DELETE_ANY_STORIES))


def _sanitize_summary(summary: dict) -> dict:
    """Sanitize story chapter content fields in pipeline output summary."""
    for key in ("draft", "enhanced"):
        section = summary.get(key)
        if section and isinstance(section.get("chapters"), list):
            for ch in section["chapters"]:
                if isinstance(ch.get("content"), str):
                    ch["content"] = sanitize_story_html(ch["content"])
    return summary


def _drain_and_coalesce(progress_queue: "_queue.Queue", first):
    """Collect `first` plus everything currently queued, then collapse runs of
    consecutive ``stream`` frames down to the latest one in each run.

    ``stream`` payloads are cumulative snapshots of the partial text (see
    ``on_stream`` -> ``sanitize_story_html(partial_text)``), so an older snapshot
    is fully superseded by a newer one and can be dropped losslessly. ``log`` and
    ``error`` frames are ALWAYS preserved in order — the live progress UX (and
    the chapter/phase counters) ride entirely on ``log`` events, so they must
    never be discarded during draining.
    """
    batch = [first]
    while True:
        try:
            batch.append(progress_queue.get_nowait())
        except _queue.Empty:
            break
    out = []
    for idx, item in enumerate(batch):
        # Skip a stream frame only when an immediately-following frame is also a
        # stream frame (it carries the newer, superseding snapshot).
        if item[0] == "stream" and idx + 1 < len(batch) and batch[idx + 1][0] == "stream":
            continue
        out.append(item)
    return out


def _error_reason_from_logs(logs, fallback: str = "Pipeline thất bại. Vui lòng thử lại.") -> str:
    """Best-effort extraction of the failure reason an orchestrator logged right
    before aborting with ``status="error"``.

    The orchestrator records the cause through its progress callback (e.g.
    ``"Không kết nối được LLM: ..."``) and then returns immediately, so the most
    recent non-empty log line is the reason in the abort paths. Falls back to a
    clear generic message when no log is available.
    """
    for line in reversed(logs or []):
        if isinstance(line, str) and line.strip():
            return line.strip()
    return fallback


# Shared orchestrator instance per session.
# asyncio.Lock: concurrent SSE requests (different sessions) may interleave
# within the same event loop when awaiting.
# Single dict merges orchestrator + timestamp to eliminate race conditions in reaper.
_sessions: dict[str, tuple[PipelineOrchestrator, float, str]] = {}  # (orch, ts, client_ip)
_orchestrators_lock = asyncio.Lock()
_SESSION_TTL = 3600  # 1 hour
_REAPER_INTERVAL = 300  # check every 5 minutes
_MAX_SESSIONS_PER_IP = 3


class _OrchestratorView:
    """Read-only dict-like view over _sessions exposing only the orchestrator.

    Provides backward-compatible `.get()` so external modules (e.g. export_routes)
    can look up an orchestrator by session_id without knowing the internal tuple layout.
    """

    def get(self, key: str, default=None):
        entry = _sessions.get(key)
        return entry[0] if entry is not None else default

    def __contains__(self, key: str) -> bool:
        return key in _sessions


# Backward-compatible alias used by api/export_routes.py
_orchestrators = _OrchestratorView()


async def _try_reserve_session(session_id: str, orch: "PipelineOrchestrator", client_ip: str) -> bool:
    """Atomically enforce the per-IP session cap and reserve a slot.

    The count and the insert MUST happen under a single lock acquire. The old
    code counted under the lock, released it, built the orchestrator, then
    re-acquired to insert — a TOCTOU window in which N concurrent same-IP
    requests each saw a count below the cap and then all inserted, blowing past
    ``_MAX_SESSIONS_PER_IP``. Returns True if a slot was reserved, False if the
    caller is already at the cap (no await/yield inside the critical section).
    """
    async with _orchestrators_lock:
        ip_count = sum(1 for (_, _, ip) in _sessions.values() if ip == client_ip)
        if ip_count >= _MAX_SESSIONS_PER_IP:
            return False
        _sessions[session_id] = (orch, time.time(), client_ip)
        return True

# Active pipeline tasks — tracked for graceful shutdown.
_active_tasks: set[asyncio.Task] = set()


async def _session_reaper():
    while True:
        await asyncio.sleep(_REAPER_INTERVAL)
        now = time.time()
        async with _orchestrators_lock:
            expired = [k for k, (_, ts, _ip) in _sessions.items() if now - ts > _SESSION_TTL]
            for k in expired:
                _sessions.pop(k, None)
        if expired:
            logger.debug(f"Session reaper evicted {len(expired)} expired orchestrator(s)")


# Strong reference to the session reaper so asyncio's weak task ref doesn't let
# it get garbage-collected mid-flight (H1).
_session_reaper_task: Optional[asyncio.Task] = None


def start_session_reaper():
    """Launch the session reaper background task. Call from app lifespan startup."""
    global _session_reaper_task
    _session_reaper_task = asyncio.create_task(_session_reaper())
    return _session_reaper_task


async def shutdown_pipeline_tasks(timeout: int = 30):
    """Cancel and await active pipeline tasks for graceful shutdown."""
    global _session_reaper_task
    # Cancel the long-lived session reaper first so it doesn't outlive the app
    # and emit a "Task was destroyed but it is pending" warning.
    if _session_reaper_task is not None:
        _session_reaper_task.cancel()
        try:
            await _session_reaper_task
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Session reaper raised during shutdown (ignored)")
        finally:
            _session_reaper_task = None

    tasks = list(_active_tasks)
    for task in tasks:
        task.cancel()
    if tasks:
        done, pending = await asyncio.wait(tasks, timeout=timeout)
        # L1 workers run inside asyncio.to_thread and cannot be hard-cancelled —
        # the thread keeps running until the blocking LLM call returns. Log what
        # is still pending after the grace period so operators know the process
        # exit may drop in-flight work (the job registry lets the FE recover the
        # result after restart only if the worker persisted before exit).
        if pending:
            logger.warning(
                "Shutdown: %d pipeline task(s) still pending after %ds grace — "
                "their to_thread workers cannot be force-killed and may be dropped "
                "on process exit.",
                len(pending),
                timeout,
            )


# ─────────────────────────────────────────────────────────────────────────────
# Shared SSE-over-job-registry helpers
#
# The canonical pattern (job registry + heartbeat + drain/coalesce + no cancel
# on disconnect) was first written inline in `/run`. These helpers extract it so
# the continuation generators (`/continue`, `/regenerate`, `/insert`,
# `/write-from-outlines`) converge on the SAME correct behaviour instead of each
# re-deriving it (and re-introducing the dropped-log / cancel-on-disconnect
# bugs). `/run` and `/resume` keep their inline loops — they are already shipped
# and tested; these are a faithful copy for the endpoints being migrated.
# ─────────────────────────────────────────────────────────────────────────────

def make_progress_callbacks(job: "_jobs.PipelineJob", stream_interval: float = 0.3):
    """Build `(on_progress, on_stream)` callbacks bound to a job.

    `on_progress` always appends to `job.logs` (so recovery sees every line) but
    only enqueues onto `job.progress_queue` while the client is connected — once
    the SSE streamer flips `job.disconnected`, enqueueing stops so an abandoned
    long-running worker can't grow the queue without bound (H4).

    `on_stream` throttles cumulative-snapshot frames to at most one per
    `stream_interval` seconds and likewise stops after disconnect.
    """
    last_stream_time = [0.0]

    def on_progress(msg: str) -> None:
        job.logs.append(msg)
        if not job.disconnected:
            job.progress_queue.put_nowait(("log", msg))

    def on_stream(partial_text: str) -> None:
        if job.disconnected:
            return
        now = time.time()
        if now - last_stream_time[0] > stream_interval:
            job.progress_queue.put_nowait(("stream", sanitize_story_html(partial_text)))
            last_stream_time[0] = now

    return on_progress, on_stream


def launch_job_task(
    session_id: str,
    job: "_jobs.PipelineJob",
    coro,
    *,
    cancelled_msg: str = "Run was cancelled.",
) -> asyncio.Task:
    """Create the worker task, track it for shutdown, and attach the
    belt-and-suspenders done-callback that force-marks the job terminal if the
    worker's own `finally` never ran (H2). No-ops when already terminal, so the
    normal path (worker finally → mark_done) is unaffected."""
    task = asyncio.create_task(coro)
    job.task = task
    _active_tasks.add(task)

    def _on_task_done(t: asyncio.Task, sid: str = session_id) -> None:
        _active_tasks.discard(t)
        if t.cancelled():
            _jobs.mark_terminal_sync(sid, error=cancelled_msg, status="cancelled")
        elif t.exception() is not None:
            _jobs.mark_terminal_sync(sid, error="Worker crashed unexpectedly.")
        else:
            _jobs.mark_terminal_sync(sid)

    task.add_done_callback(_on_task_done)
    return task


async def finalize_job(
    session_id: str,
    job: "_jobs.PipelineJob",
    output,
    *,
    caught_error: Optional[str],
    was_cancelled: bool,
    cancelled_msg: str = "Run was cancelled.",
) -> None:
    """Persist a worker's terminal state into the registry. Call from the
    worker's `finally`. Mirrors `/run`'s finalisation: build a summary from a
    successful output, surface the real reason for an error-status output, or
    record the captured exception message — writing `cancelled` when the task
    was cancelled rather than mislabelling it `error`."""
    final_summary = None
    final_error = None
    output_status = getattr(output, "status", None) if output is not None else None
    if output is not None and output_status != "error":
        try:
            from api.pipeline_output_builder import build_output_summary
            safe_output = output.model_copy(deep=True)
            final_summary = build_output_summary(safe_output)
            final_summary["session_id"] = session_id
            final_summary["logs"] = list(job.logs)
            _sanitize_summary(final_summary)
        except Exception as exc:
            logger.exception(
                "Failed to build final summary (session=%s): %s", session_id, exc
            )
            final_error = "Failed to assemble pipeline result."
    elif output is not None:
        err_logs = getattr(output, "logs", None) or job.logs
        final_error = caught_error or _error_reason_from_logs(err_logs)
    else:
        final_error = caught_error or "Pipeline produced no output."

    if was_cancelled:
        await _jobs.mark_done(session_id, status="cancelled", error=cancelled_msg)
    else:
        await _jobs.mark_done(session_id, summary=final_summary, error=final_error)


async def stream_job_events(request: Request, job: "_jobs.PipelineJob", *, label: str):
    """Canonical SSE generator shared by the continuation endpoints.

    Yields the `session` frame, then drains `job.progress_queue` (coalescing only
    consecutive `stream` snapshots — logs/errors preserved in order), heartbeats
    during idle gaps, and finally yields the terminal `done`/`error` frame from
    the job's persisted summary/error. On client disconnect it flips
    `job.disconnected` and returns WITHOUT cancelling the worker — the job keeps
    running and its result stays poll-able via GET /api/pipeline/run/{sid}.
    """
    task = job.task
    session_id = job.session_id
    try:
        yield f"data: {json.dumps({'type': 'session', 'session_id': session_id})}\n\n"

        last_yield = time.monotonic()
        while task is not None and not task.done():
            if await request.is_disconnected():
                job.disconnected = True
                logger.info(
                    "Client disconnected from /%s stream (session=%s) — job continues",
                    label,
                    session_id,
                )
                return
            try:
                first = await asyncio.to_thread(job.progress_queue.get, timeout=0.2)
                for msg_type, msg_data in _drain_and_coalesce(job.progress_queue, first):
                    event = {"type": msg_type, "data": msg_data}
                    if msg_type == "log":
                        event["logs_count"] = len(job.logs)
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                last_yield = time.monotonic()
            except _queue.Empty:
                if time.monotonic() - last_yield > 10:
                    yield ": ping\n\n"
                    last_yield = time.monotonic()
                continue

        # Drain anything queued after the task finished.
        while True:
            try:
                msg_type, msg_data = job.progress_queue.get_nowait()
                event = {"type": msg_type, "data": msg_data}
                if msg_type == "log":
                    event["logs_count"] = len(job.logs)
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            except _queue.Empty:
                break

        if job.summary is not None:
            yield (
                "data: "
                + json.dumps(
                    {"type": "done", "data": job.summary},
                    ensure_ascii=False,
                    default=str,
                )
                + "\n\n"
            )
        else:
            err_msg = job.error or "Pipeline thất bại"
            yield f"data: {json.dumps({'type': 'error', 'data': err_msg})}\n\n"
    except asyncio.CancelledError:
        logger.info("SSE /%s stream cancelled (session=%s)", label, session_id)
    except (ConnectionError, ConnectionResetError):
        logger.info("SSE /%s client connection lost (session=%s)", label, session_id)
    except Exception:
        logger.exception("SSE /%s unexpected error (session=%s)", label, session_id)
        raise
    finally:
        logger.debug("SSE /%s stream closed (session=%s)", label, session_id)


i18n = I18n()


def _t(key, **kw):
    return i18n.t(key, **kw)


class PipelineRequest(BaseModel):
    """Request body for running the pipeline."""
    idea: str = Field("", max_length=20000)
    title: str = Field("", max_length=200)
    genre: str = Field("Tiên Hiệp", max_length=100)
    style: str = Field("Miêu tả chi tiết", max_length=100)
    language: str = Field("vi", max_length=10)
    num_chapters: int = Field(5, ge=1, le=50, description="Chapters to write in this session (preview batch)")
    target_total_chapters: Optional[int] = Field(default=None, ge=1, le=500, description="Total chapters in the full story arc; if set, num_chapters must be <= this")
    num_characters: int = Field(5, ge=1, le=30)
    word_count: int = Field(2000, ge=100, le=20000)
    num_sim_rounds: int = Field(3, ge=1, le=10)
    drama_level: str = Field("cao", max_length=50)

    @field_validator("target_total_chapters")
    @classmethod
    def _validate_total_vs_session(cls, v, info):
        if v is None:
            return v
        session = info.data.get("num_chapters")
        if session is not None and v < session:
            raise ValueError("target_total_chapters must be >= num_chapters (preview batch fits inside the story arc)")
        return v

    @field_validator("drama_level")
    @classmethod
    def _validate_drama_level(cls, v: str) -> str:
        """Accept VN aliases (thấp/vừa/cao/đỉnh) and EN (low/medium/high/climax).
        Returns the original VN-or-EN string for backward compat with downstream
        consumers that branch on "cao"; the canonical Literal is exposed via
        ``normalize_drama()`` for routes that need it."""
        try:
            _normalize_drama(v)
        except ValueError:
            raise ValueError(
                "drama_level must be one of: thấp/vừa/cao/đỉnh, low/medium/high/climax"
            )
        # Gate "climax"/"đỉnh" behind feature flag.
        from config import ConfigManager
        if v.strip().lower() in {"climax", "đỉnh"}:
            cfg = ConfigManager()
            if not getattr(cfg.pipeline, "enable_drama_climax", False):
                raise ValueError("drama_level 'climax' requires enable_drama_climax=True")
        return v
    enable_agents: bool = True
    enable_scoring: bool = True
    enable_media: bool = False
    lite_mode: bool = False
    # L1 consistency flags (Phase 5)
    enable_l1_consistency: bool = False  # Master toggle for all L1 consistency features
    enable_emotional_memory: bool = True
    enable_proactive_constraints: bool = True
    enable_thread_enforcement: bool = True
    enable_emotional_bridge: bool = True
    enable_scene_beat_writing: bool = True
    enable_l1_causal_graph: bool = True
    enable_self_review: bool = True
    enable_agent_debate: bool = True
    # L2 drama settings
    l2_drama_threshold: float = Field(0.5, ge=0.0, le=1.0)
    l2_drama_target: float = Field(0.65, ge=0.0, le=1.0)
    # Quality settings
    enable_quality_gate: bool = True
    quality_gate_threshold: float = Field(2.5, ge=1.0, le=5.0)
    enable_smart_revision: bool = True
    smart_revision_threshold: float = Field(3.5, ge=1.0, le=5.0)
    # P-A/B/C: Post-enhancement features
    enable_sensory_polish: bool = True  # L3 sensory details — on by default
    enable_reader_simulation: bool = False  # Reader feedback
    enable_incremental_publish: bool = False  # Stream chapters as enhanced


class ResumeRequest(BaseModel):
    """Request body for resuming from checkpoint."""
    checkpoint: str


def _genre_keys():
    return [
        "genre.tien_hiep", "genre.huyen_huyen", "genre.kiem_hiep", "genre.do_thi",
        "genre.ngon_tinh", "genre.xuyen_khong", "genre.trong_sinh", "genre.he_thong",
        "genre.khoa_huyen", "genre.dong_nhan", "genre.lich_su", "genre.quan_su",
        "genre.linh_di", "genre.trinh_tham", "genre.hai_huoc", "genre.vong_du",
        "genre.di_gioi", "genre.mat_the", "genre.dien_van", "genre.cung_dau",
        "genre.kinh_di", "genre.the_thao",
    ]


@router.get("/genres")
def get_genres():
    """Return genre, style, drama level, and language choices."""
    return {
        "genres": [_t(k) for k in _genre_keys()],
        "styles": [_t(k) for k in [
            "style.descriptive", "style.dialogue", "style.action",
            "style.romance", "style.dark",
        ]],
        "drama_levels": [_t(k) for k in ["drama.low", "drama.medium", "drama.high"]],
        "languages": [
            {"code": "vi", "label": "Tiếng Việt"},
            {"code": "en", "label": "English"},
        ],
    }


@router.get("/templates")
def get_templates():
    """Return story templates grouped by genre."""
    templates_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data", "templates", "story_templates.json",
    )
    if os.path.exists(templates_path):
        try:
            with open(templates_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            pass
    return {}


@router.get("/checkpoints", dependencies=[_READ_STORIES])
def get_checkpoints():
    """List available checkpoints with metadata for library."""
    from pipeline.orchestrator import PipelineOrchestrator
    from services.continuation_history import latest_event
    from services.resume_status import derive_resume_status
    from services.usage_history import usage_summary
    ckpts = PipelineOrchestrator.list_checkpoints()
    items = []
    for c in ckpts:
        resume = derive_resume_status(c)
        items.append({
            "label": f"{c['file']} ({c['modified']}, {c['size_kb']}KB)",
            "path": c['file'],
            "title": c.get('title', ''),
            "genre": c.get('genre', ''),
            "chapter_count": c.get('chapter_count', 0),
            "current_layer": c.get('current_layer', 0),
            "size_kb": c['size_kb'],
            "modified": c['modified'],
            "latest_continuation": latest_event(c['file']),
            "usage_summary": usage_summary(c['file']),
            # Piece N: resume-from-chapter affordance.
            "interrupted": resume["interrupted"],
            "resume_from_chapter": resume["resume_from_chapter"],
            "target_chapters": resume["target_chapters"],
        })
    return {"checkpoints": items}


@router.get("/checkpoints/{filename}", dependencies=[_READ_STORIES])
def get_checkpoint(filename: str):
    """Load a single checkpoint and return formatted data for the reader."""
    import pathlib
    checkpoint_dir = pathlib.Path(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ).resolve() / "output" / "checkpoints"
    safe_name = pathlib.Path(filename).name  # strips directory components
    if not safe_name or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    checkpoint_path = (checkpoint_dir / safe_name).resolve()
    # Verify resolved path is strictly inside checkpoint_dir (defence-in-depth)
    if not str(checkpoint_path).startswith(str(checkpoint_dir)):
        raise HTTPException(status_code=400, detail="Invalid filename")
    if not checkpoint_path.exists():
        raise HTTPException(status_code=404, detail="Checkpoint not found")

    _MAX_CHECKPOINT_BYTES = 50 * 1024 * 1024  # 50 MB
    if checkpoint_path.stat().st_size > _MAX_CHECKPOINT_BYTES:
        raise HTTPException(status_code=413, detail="Checkpoint file too large (max 50MB)")

    try:
        with open(str(checkpoint_path), "r", encoding="utf-8") as f:
            data = json.load(f)
        from models.schemas import PipelineOutput
        output = PipelineOutput(**data)
        from api.pipeline_output_builder import build_output_summary
        summary = build_output_summary(output)
        summary["source"] = "library"
        summary["filename"] = safe_name
        return summary
    except Exception as e:
        logger.error(f"Failed to load checkpoint {safe_name}: {e}")
        raise HTTPException(status_code=500, detail="Failed to load checkpoint")


@router.delete("/checkpoints/{filename}", dependencies=[_DELETE_ANY_STORIES])
def delete_checkpoint(filename: str):
    """Delete a checkpoint file."""
    import pathlib
    checkpoint_dir = pathlib.Path(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ).resolve() / "output" / "checkpoints"
    safe_name = pathlib.Path(filename).name
    if not safe_name or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    checkpoint_path = (checkpoint_dir / safe_name).resolve()
    if not str(checkpoint_path).startswith(str(checkpoint_dir)):
        raise HTTPException(status_code=400, detail="Invalid filename")
    if not checkpoint_path.exists():
        raise HTTPException(status_code=404, detail="Checkpoint not found")

    try:
        os.remove(str(checkpoint_path))
        logger.info(f"Deleted checkpoint: {safe_name}")
        return {"ok": True, "deleted": safe_name}
    except Exception as e:
        logger.error(f"Failed to delete checkpoint {safe_name}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete checkpoint")


@router.get("/stories", dependencies=[_READ_STORIES])
def list_stories(limit: int = 20, offset: int = 0, enhanced_only: bool = True):
    """List saved stories (checkpoints) with pagination.

    Args:
        limit: Maximum number of items to return (default 20).
        offset: Number of items to skip (default 0).
        enhanced_only: If True, only return layer2 (enhanced) checkpoints.

    Returns paginated story list with total count for client-side pagination.
    """
    from pipeline.orchestrator import PipelineOrchestrator
    all_checkpoints = PipelineOrchestrator.list_checkpoints()
    if enhanced_only:
        all_checkpoints = [c for c in all_checkpoints if "_layer2" in c.get("file", "")]
    total = len(all_checkpoints)
    page = all_checkpoints[offset: offset + limit]
    items = [
        {
            "filename": c.get("file", ""),
            "title": c.get("title", ""),
            "genre": c.get("genre", ""),
            "chapter_count": c.get("chapter_count", 0),
            "current_layer": c.get("current_layer", 0),
            "size_kb": c.get("size_kb", 0),
            "modified": c.get("modified", ""),
        }
        for c in page
    ]
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.post("/run", dependencies=[_CREATE_STORIES])
async def run_pipeline(request: Request, body: PipelineRequest):
    """Run the full pipeline, streaming progress via SSE."""
    # Validate input
    idea = (body.idea or "").strip()
    if not idea or len(idea) < 10:
        async def _error_stream():
            yield f"data: {json.dumps({'type': 'error', 'data': 'Story idea is too short. Please enter at least 10 characters.'})}\n\n"
        return StreamingResponse(
            _error_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    client_ip = request.client.host if request.client else "unknown"

    async def event_generator():
        orch = PipelineOrchestrator()
        session_id = str(uuid.uuid4())
        # Atomic count+reserve under one lock (TOCTOU fix) — see
        # _try_reserve_session.
        if not await _try_reserve_session(session_id, orch, client_ip):
            yield f"data: {json.dumps({'type': 'error', 'data': f'Too many concurrent sessions (max {_MAX_SESSIONS_PER_IP}). Please wait for current stories to finish.'})}\n\n"
            return

        # Register a long-lived job record so the pipeline survives if the
        # client disconnects. The job carries the progress_queue, logs and
        # final summary; FE can poll GET /api/pipeline/run/{session_id} to
        # recover the result after SSE drop. See pipeline_job_registry.py.
        job = await _jobs.register(session_id, kind="run")
        job.orchestrator = orch
        progress_queue: _queue.Queue = job.progress_queue
        logs = job.logs
        stream_text = [""]

        def on_progress(msg):
            logs.append(msg)
            # put_nowait is safe: called from asyncio.to_thread workers (thread pool)
            # but the queue itself is asyncio-safe for cross-thread puts. Stop
            # enqueueing once the client disconnects so an abandoned job can't
            # grow the queue without bound (H4); `logs` still records every line.
            if not job.disconnected:
                progress_queue.put_nowait(("log", msg))

        last_stream_time = [0.0]

        def on_stream(partial_text):
            stream_text[0] = partial_text
            if job.disconnected:
                return
            now = time.time()
            if now - last_stream_time[0] > 0.3:
                progress_queue.put_nowait(("stream", sanitize_story_html(partial_text)))
                last_stream_time[0] = now

        # Apply lite mode: switch debate to 3-agent fast path (~85% fewer API calls).
        # Enabled per-request via body.lite_mode, or globally via STORYFORGE_LITE_MODE=true.
        if body.lite_mode or os.environ.get("STORYFORGE_LITE_MODE", "").lower() in ("1", "true"):
            orch.config.pipeline.debate_mode = "lite"

        # Apply L1 consistency flags (Phase 5)
        # Master toggle enables all, individual flags can also be set
        if body.enable_l1_consistency:
            orch.config.pipeline.enable_emotional_memory = True
            orch.config.pipeline.enable_proactive_constraints = True
            orch.config.pipeline.enable_thread_enforcement = True
            orch.config.pipeline.enable_emotional_bridge = True
            orch.config.pipeline.enable_scene_beat_writing = True
            orch.config.pipeline.enable_l1_causal_graph = True
        else:
            # Individual flags (only if master toggle is off)
            if body.enable_emotional_memory:
                orch.config.pipeline.enable_emotional_memory = True
            if body.enable_proactive_constraints:
                orch.config.pipeline.enable_proactive_constraints = True
            if body.enable_thread_enforcement:
                orch.config.pipeline.enable_thread_enforcement = True
            if body.enable_emotional_bridge:
                orch.config.pipeline.enable_emotional_bridge = True
            if body.enable_scene_beat_writing:
                orch.config.pipeline.enable_scene_beat_writing = True
            if body.enable_l1_causal_graph:
                orch.config.pipeline.enable_l1_causal_graph = True

        # Apply additional advanced settings
        orch.config.pipeline.enable_self_review = body.enable_self_review
        orch.config.pipeline.enable_agent_debate = body.enable_agent_debate
        orch.config.pipeline.l2_drama_threshold = body.l2_drama_threshold
        orch.config.pipeline.l2_drama_target = body.l2_drama_target
        # Quality settings
        orch.config.pipeline.enable_quality_gate = body.enable_quality_gate
        orch.config.pipeline.quality_gate_threshold = body.quality_gate_threshold
        orch.config.pipeline.enable_smart_revision = body.enable_smart_revision
        orch.config.pipeline.smart_revision_threshold = body.smart_revision_threshold
        # P-A/B/C: Post-enhancement features
        orch.config.pipeline.enable_sensory_polish = body.enable_sensory_polish
        orch.config.pipeline.enable_reader_simulation = body.enable_reader_simulation
        orch.config.pipeline.enable_incremental_publish = body.enable_incremental_publish
        # Language setting
        orch.config.pipeline.language = body.language

        # Auto-generate title from idea if not provided
        story_title = body.title.strip() if body.title else ""
        if not story_title:
            try:
                from pipeline.layer1_story.outline_builder import generate_title_from_idea
                from services.llm_client import LLMClient
                llm = LLMClient()
                story_title = generate_title_from_idea(llm, body.genre, idea)
                logger.info(f"Auto-generated title: {story_title}")
            except Exception as e:
                logger.warning(f"Title generation failed, using fallback: {e}")
                story_title = f"Truyện {body.genre}"

        result: list = [None]
        # Specific, user-facing error captured by the except arms below so the
        # finally (and the recovery GET endpoint) can report the real cause
        # instead of the generic "Pipeline produced no output." fallback.
        caught_error: list = [None]
        # True if the task was cancelled (shutdown / explicit cancel). Lets the
        # finally record a `cancelled` terminal status instead of mislabelling
        # the run as `error`.
        was_cancelled: list = [False]

        async def _run_async():
            try:
                _pipeline_coro = orch.run_full_pipeline(
                    title=story_title,
                    genre=body.genre,
                    idea=idea,
                    style=body.style,
                    num_chapters=body.num_chapters,
                    target_total_chapters=body.target_total_chapters,
                    num_characters=body.num_characters,
                    word_count=body.word_count,
                    num_sim_rounds=body.num_sim_rounds,
                    progress_callback=on_progress,
                    stream_callback=on_stream,
                    enable_agents=body.enable_agents,
                    enable_scoring=body.enable_scoring,
                    enable_media=body.enable_media,
                )
                result[0] = await _pipeline_coro if inspect.isawaitable(_pipeline_coro) else _pipeline_coro
            except asyncio.CancelledError:
                logger.info(f"Pipeline task cancelled (session={session_id})")
                was_cancelled[0] = True
                raise
            except (ValueError, TypeError) as e:
                logger.warning(f"Pipeline input error (session={session_id}): {e}")
                caught_error[0] = "Invalid pipeline input. Please check your settings."
                progress_queue.put_nowait(("error", caught_error[0]))
            except (TimeoutError, ConnectionError) as e:
                logger.error(f"Pipeline network error (session={session_id}): {e}")
                caught_error[0] = "Network error during pipeline. Please try again."
                progress_queue.put_nowait(("error", caught_error[0]))
            except Exception as e:
                logger.exception(f"Pipeline error (session={session_id}): {e}")
                caught_error[0] = "An unexpected error occurred. Please try again."
                progress_queue.put_nowait(("error", caught_error[0]))
            finally:
                # Persist final state into the registry so FE can recover via
                # GET /api/pipeline/run/{session_id} even if SSE was lost.
                final_summary = None
                final_error = None
                output = result[0]
                output_status = getattr(output, "status", None) if output is not None else None
                if output is not None and output_status != "error":
                    try:
                        from api.pipeline_output_builder import build_output_summary
                        safe_output = output.model_copy(deep=True)
                        final_summary = build_output_summary(safe_output)
                        final_summary["session_id"] = session_id
                        final_summary["logs"] = list(job.logs)
                        _sanitize_summary(final_summary)
                    except Exception as exc:
                        logger.exception(
                            f"Failed to build final summary (session={session_id}): {exc}"
                        )
                        final_error = "Failed to assemble pipeline result."
                elif output is not None:
                    # Orchestrator returned an error-status output (e.g. LLM
                    # unreachable). Surface the real reason instead of
                    # masquerading as a successful, empty `done`. The canonical
                    # cause is appended to output.logs by the orchestrator;
                    # fall back to job.logs (progress mirror) if absent.
                    err_logs = getattr(output, "logs", None) or job.logs
                    final_error = caught_error[0] or _error_reason_from_logs(err_logs)
                else:
                    # No output at all (exception path) — prefer the specific
                    # message captured by the except arms.
                    final_error = caught_error[0] or "Pipeline produced no output."
                if was_cancelled[0]:
                    # Cancellation is not a failure — record it as such so the FE
                    # can distinguish "you stopped this" from "it crashed".
                    await _jobs.mark_done(
                        session_id,
                        status="cancelled",
                        error="Run was cancelled.",
                    )
                else:
                    await _jobs.mark_done(
                        session_id, summary=final_summary, error=final_error
                    )

        task = asyncio.create_task(_run_async())
        job.task = task
        _active_tasks.add(task)

        def _on_task_done(t: asyncio.Task, sid: str = session_id) -> None:
            # Belt-and-suspenders (H2): if _run_async's finally never ran (e.g.
            # the task was hard-cancelled before reaching it), the job would be
            # stuck `running`. mark_terminal_sync no-ops when already terminal,
            # so the normal path is unaffected.
            _active_tasks.discard(t)
            if t.cancelled():
                _jobs.mark_terminal_sync(sid, error="Run was cancelled.", status="cancelled")
            elif t.exception() is not None:
                _jobs.mark_terminal_sync(sid, error="Worker crashed unexpectedly.")
            else:
                _jobs.mark_terminal_sync(sid)

        task.add_done_callback(_on_task_done)

        try:
            # Send session_id first
            yield f"data: {json.dumps({'type': 'session', 'session_id': session_id})}\n\n"

            last_yield = time.monotonic()
            while not task.done():
                # Client disconnect: close THIS stream only. Do NOT cancel
                # the pipeline task — the worker thread cannot be killed
                # anyway, and discarding its output silently is the bug
                # this whole refactor fixes. The job keeps running; its
                # final state is poll-able via GET /api/pipeline/run/{sid}.
                if await request.is_disconnected():
                    logger.info(
                        f"Client disconnected from /run stream (session={session_id}) — "
                        f"job continues in background"
                    )
                    # H4: signal the worker callbacks to stop enqueueing into the
                    # now-abandoned queue. The job keeps running (~9 min) and keeps
                    # appending to job.logs for recovery, but the queue no longer
                    # grows without a consumer to drain it.
                    job.disconnected = True
                    return
                try:
                    first = await asyncio.to_thread(progress_queue.get, timeout=0.2)
                    # Drain everything queued, coalescing only consecutive stream
                    # snapshots; logs/errors are preserved in order (the progress
                    # UX depends on every log line being delivered).
                    for msg_type, msg_data in _drain_and_coalesce(progress_queue, first):
                        event = {"type": msg_type, "data": msg_data}
                        if msg_type == "log":
                            event["logs_count"] = len(logs)
                        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                    last_yield = time.monotonic()
                except _queue.Empty:
                    # Heartbeat: keep proxies + browsers from closing the idle socket
                    # during long LLM calls with no progress events. SSE comment
                    # frames are ignored by EventSource clients but reset proxy
                    # idle timers (Next dev proxy ~30s, Cloudflare 100s, etc.).
                    if time.monotonic() - last_yield > 10:
                        yield ": ping\n\n"
                        last_yield = time.monotonic()
                    continue

            # Drain any remaining messages after task completion
            while True:
                try:
                    msg_type, msg_data = progress_queue.get_nowait()
                    event = {"type": msg_type, "data": msg_data}
                    if msg_type == "log":
                        event["logs_count"] = len(logs)
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                except _queue.Empty:
                    break

            # Send final result — prefer the summary already persisted in
            # the job (built in `_run_async` finally) so the wire shape
            # matches what GET /api/pipeline/run/{sid} returns.
            if job.summary is not None:
                yield (
                    "data: "
                    + json.dumps(
                        {"type": "done", "data": job.summary},
                        ensure_ascii=False,
                        default=str,
                    )
                    + "\n\n"
                )
            else:
                err_msg = job.error or "Pipeline thất bại"
                yield f"data: {json.dumps({'type': 'error', 'data': err_msg})}\n\n"
        except asyncio.CancelledError:
            # SSE generator itself was cancelled (e.g. server shutdown).
            # Leave the background job alone — it'll finish on its own,
            # and the result will be available via the GET endpoint.
            logger.info(f"SSE /run stream cancelled (session={session_id})")
        except (ConnectionError, ConnectionResetError):
            logger.info(f"SSE /run client connection lost (session={session_id})")
        except (ValueError, TypeError) as e:
            logger.warning(f"SSE /run serialization error (session={session_id}): {e}")
        except Exception:
            logger.exception(f"SSE /run unexpected error (session={session_id})")
            raise
        finally:
            # Do NOT pop _sessions here — the orchestrator must remain
            # findable for the simulator and for follow-up requests within
            # the TTL window. _session_reaper handles eviction by age.
            logger.debug(f"SSE /run stream closed (session={session_id})")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/run/{session_id}", dependencies=[_READ_STORIES])
async def get_run_status(session_id: str):
    """Poll a pipeline job's current status + final summary.

    Lets the FE recover the result after a lost SSE stream. The job stays
    in the registry for `JOB_RETENTION_SECONDS` (default 1h) after it
    finishes, so a refresh inside that window returns the same payload the
    SSE `done` event would have sent.
    """
    job = _jobs.get(session_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Session không tồn tại hoặc đã hết hạn.")

    payload: dict[str, Any] = {
        "session_id": job.session_id,
        "status": job.status,
        "kind": job.kind,
        "logs_count": len(job.logs),
        "created_at": job.created_at,
        "completed_at": job.completed_at,
    }
    if job.status in ("done", "error", "cancelled"):
        payload["summary"] = job.summary
        payload["error"] = job.error
    return payload


@router.post("/resume", dependencies=[_CREATE_STORIES])
async def resume_pipeline(request: Request, body: ResumeRequest):
    """Resume pipeline from a checkpoint, streaming progress via SSE."""
    # Resolve checkpoint safely — accept filename only, prevent path traversal
    import pathlib
    checkpoint_dir = pathlib.Path(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ).resolve() / "output" / "checkpoints"
    safe_name = pathlib.Path(body.checkpoint).name  # strips any directory components
    checkpoint_path = (checkpoint_dir / safe_name).resolve() if safe_name else None
    # Verify resolved path stays inside checkpoint_dir
    if (
        not safe_name
        or checkpoint_path is None
        or not str(checkpoint_path).startswith(str(checkpoint_dir))
        or not checkpoint_path.exists()
    ):
        def _error_stream():
            yield f"data: {json.dumps({'type': 'error', 'data': 'Checkpoint not found.'})}\n\n"
        return StreamingResponse(
            _error_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    client_ip = request.client.host if request.client else "unknown"

    async def event_generator():
        orch = PipelineOrchestrator()
        session_id = str(uuid.uuid4())
        # Atomic count+reserve under one lock (TOCTOU fix) — see
        # _try_reserve_session.
        if not await _try_reserve_session(session_id, orch, client_ip):
            yield f"data: {json.dumps({'type': 'error', 'data': f'Too many concurrent sessions (max {_MAX_SESSIONS_PER_IP}). Please wait for current stories to finish.'})}\n\n"
            return

        # Register a long-lived job so the resume keeps running even if the
        # SSE client drops. FE recovers via GET /api/pipeline/run/{session_id}.
        job = await _jobs.register(session_id, kind="resume")
        job.orchestrator = orch
        progress_queue: _queue.Queue = job.progress_queue
        logs = job.logs

        def on_progress(msg):
            logs.append(msg)
            # H4: stop enqueueing once the SSE client disconnects so an abandoned
            # resume can't grow the queue without bound; `logs` still records
            # every line for recovery via the poll endpoint.
            if not job.disconnected:
                progress_queue.put_nowait(("log", msg))

        result: list = [None]
        # Specific, user-facing error captured by the except arms below so the
        # finally (and the recovery GET endpoint) can report the real cause
        # instead of the generic "Pipeline produced no output." fallback.
        caught_error: list = [None]
        was_cancelled: list = [False]

        async def _run_async():
            try:
                result[0] = await asyncio.to_thread(
                    orch.resume_from_checkpoint,
                    checkpoint_path=str(checkpoint_path),
                    progress_callback=on_progress,
                )
            except asyncio.CancelledError:
                logger.info(f"Resume task cancelled (session={session_id})")
                was_cancelled[0] = True
                raise
            except (ValueError, TypeError) as e:
                logger.warning(f"Resume input error (session={session_id}): {e}")
                caught_error[0] = "Invalid checkpoint data. The file may be corrupted."
                progress_queue.put_nowait(("error", caught_error[0]))
            except (TimeoutError, ConnectionError) as e:
                logger.error(f"Resume network error (session={session_id}): {e}")
                caught_error[0] = "Network error during resume. Please try again."
                progress_queue.put_nowait(("error", caught_error[0]))
            except Exception as e:
                logger.exception(f"Resume error (session={session_id}): {e}")
                caught_error[0] = "An unexpected error occurred. Please try again."
                progress_queue.put_nowait(("error", caught_error[0]))
            finally:
                final_summary = None
                final_error = None
                output = result[0]
                output_status = getattr(output, "status", None) if output is not None else None
                if output is not None and output_status != "error":
                    try:
                        from api.pipeline_output_builder import build_output_summary
                        safe_output = output.model_copy(deep=True)
                        final_summary = build_output_summary(safe_output)
                        final_summary["session_id"] = session_id
                        final_summary["logs"] = list(job.logs)
                        _sanitize_summary(final_summary)
                    except Exception as exc:
                        logger.exception(
                            f"Failed to build final resume summary (session={session_id}): {exc}"
                        )
                        final_error = "Failed to assemble resume result."
                elif output is not None:
                    # Resume returned an error-status output — surface the reason.
                    err_logs = getattr(output, "logs", None) or job.logs
                    final_error = caught_error[0] or _error_reason_from_logs(err_logs)
                else:
                    final_error = caught_error[0] or "Resume produced no output."
                if was_cancelled[0]:
                    await _jobs.mark_done(
                        session_id,
                        status="cancelled",
                        error="Resume was cancelled.",
                    )
                else:
                    await _jobs.mark_done(
                        session_id, summary=final_summary, error=final_error
                    )

        task = asyncio.create_task(_run_async())
        job.task = task
        _active_tasks.add(task)

        def _on_task_done(t: asyncio.Task, sid: str = session_id) -> None:
            # Belt-and-suspenders (H2): force a terminal status if _run_async's
            # finally never ran. No-ops when the job is already terminal.
            _active_tasks.discard(t)
            if t.cancelled():
                _jobs.mark_terminal_sync(sid, error="Resume was cancelled.", status="cancelled")
            elif t.exception() is not None:
                _jobs.mark_terminal_sync(sid, error="Worker crashed unexpectedly.")
            else:
                _jobs.mark_terminal_sync(sid)

        task.add_done_callback(_on_task_done)

        try:
            yield f"data: {json.dumps({'type': 'session', 'session_id': session_id})}\n\n"

            last_yield = time.monotonic()
            while not task.done():
                # Client disconnect: stop streaming but let the resume run
                # to completion — its result is recoverable via the GET endpoint.
                if await request.is_disconnected():
                    logger.info(
                        f"Client disconnected from /resume stream (session={session_id}) — "
                        f"job continues in background"
                    )
                    # H4: stop the worker callbacks enqueueing into the abandoned queue.
                    job.disconnected = True
                    return
                try:
                    first = await asyncio.to_thread(progress_queue.get, timeout=0.2)
                    # Same lossless drain as /run: coalesce consecutive stream
                    # snapshots, never drop log/error frames.
                    for msg_type, msg_data in _drain_and_coalesce(progress_queue, first):
                        event = {"type": msg_type, "data": msg_data}
                        if msg_type == "log":
                            event["logs_count"] = len(logs)
                        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                    last_yield = time.monotonic()
                except _queue.Empty:
                    if time.monotonic() - last_yield > 10:
                        yield ": ping\n\n"
                        last_yield = time.monotonic()
                    continue

            # Drain remaining messages after task completion
            while True:
                try:
                    msg_type, msg_data = progress_queue.get_nowait()
                    event = {"type": msg_type, "data": msg_data}
                    if msg_type == "log":
                        event["logs_count"] = len(logs)
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                except _queue.Empty:
                    break

            if job.summary is not None:
                yield (
                    "data: "
                    + json.dumps(
                        {"type": "done", "data": job.summary},
                        ensure_ascii=False,
                        default=str,
                    )
                    + "\n\n"
                )
            else:
                err_msg = job.error or "Resume failed"
                yield f"data: {json.dumps({'type': 'error', 'data': err_msg})}\n\n"
        except asyncio.CancelledError:
            logger.info(f"SSE /resume stream cancelled (session={session_id})")
        except (ConnectionError, ConnectionResetError):
            logger.info(f"SSE /resume client connection lost (session={session_id})")
        except (ValueError, TypeError) as e:
            logger.warning(f"SSE /resume serialization error (session={session_id}): {e}")
        except Exception:
            logger.exception(f"SSE /resume unexpected error (session={session_id})")
            raise
        finally:
            # Leave _sessions alone — the TTL reaper handles eviction so the
            # orchestrator stays findable for downstream lookups within TTL.
            logger.debug(f"SSE /resume stream closed (session={session_id})")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
