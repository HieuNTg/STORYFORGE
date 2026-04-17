"""Pipeline API routes — run pipeline via SSE, get genres/templates/checkpoints."""

import asyncio
import json
import logging
import queue as _queue
import os
import time
import uuid
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from services.i18n import I18n
from services.text_utils import sanitize_story_html
from pipeline.orchestrator import PipelineOrchestrator

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/pipeline", tags=["pipeline"])


def _sanitize_summary(summary: dict) -> dict:
    """Sanitize story chapter content fields in pipeline output summary."""
    for key in ("draft", "enhanced"):
        section = summary.get(key)
        if section and isinstance(section.get("chapters"), list):
            for ch in section["chapters"]:
                if isinstance(ch.get("content"), str):
                    ch["content"] = sanitize_story_html(ch["content"])
    return summary

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


@router.on_event("startup")
async def _start_session_reaper():
    asyncio.create_task(_session_reaper())


async def shutdown_pipeline_tasks(timeout: int = 30):
    """Cancel and await active pipeline tasks for graceful shutdown."""
    tasks = list(_active_tasks)
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.wait(tasks, timeout=timeout)

i18n = I18n()


def _t(key, **kw):
    return i18n.t(key, **kw)


class PipelineRequest(BaseModel):
    """Request body for running the pipeline."""
    idea: str = Field("", max_length=5000)
    title: str = Field("", max_length=200)
    genre: str = Field("Tiên Hiệp", max_length=100)
    style: str = Field("Miêu tả chi tiết", max_length=100)
    num_chapters: int = Field(5, ge=1, le=50)
    num_characters: int = Field(5, ge=1, le=30)
    word_count: int = Field(2000, ge=100, le=20000)
    num_sim_rounds: int = Field(3, ge=1, le=10)
    drama_level: str = Field("cao", max_length=50)
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
    enable_sensory_polish: bool = False  # L3 sensory details
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
    """Return genre, style, drama level choices."""
    return {
        "genres": [_t(k) for k in _genre_keys()],
        "styles": [_t(k) for k in [
            "style.descriptive", "style.dialogue", "style.action",
            "style.romance", "style.dark",
        ]],
        "drama_levels": [_t(k) for k in ["drama.low", "drama.medium", "drama.high"]],
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


@router.get("/checkpoints")
def get_checkpoints():
    """List available checkpoints with metadata for library."""
    from pipeline.orchestrator import PipelineOrchestrator
    ckpts = PipelineOrchestrator.list_checkpoints()
    return {"checkpoints": [
        {
            "label": f"{c['file']} ({c['modified']}, {c['size_kb']}KB)",
            "path": c['file'],
            "title": c.get('title', ''),
            "genre": c.get('genre', ''),
            "chapter_count": c.get('chapter_count', 0),
            "current_layer": c.get('current_layer', 0),
            "size_kb": c['size_kb'],
            "modified": c['modified'],
        }
        for c in ckpts
    ]}


@router.get("/checkpoints/{filename}")
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


@router.delete("/checkpoints/{filename}")
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


@router.get("/stories")
def list_stories(limit: int = 20, offset: int = 0):
    """List saved stories (checkpoints) with pagination.

    Args:
        limit: Maximum number of items to return (default 20).
        offset: Number of items to skip (default 0).

    Returns paginated story list with total count for client-side pagination.
    """
    from pipeline.orchestrator import PipelineOrchestrator
    all_checkpoints = PipelineOrchestrator.list_checkpoints()
    total = len(all_checkpoints)
    page = all_checkpoints[offset: offset + limit]
    items = [
        {
            "filename": c["file"],
            "title": c.get("title", ""),
            "genre": c.get("genre", ""),
            "chapter_count": c.get("chapter_count", 0),
            "current_layer": c.get("current_layer", 0),
            "size_kb": c["size_kb"],
            "modified": c["modified"],
        }
        for c in page
    ]
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.post("/run")
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
        async with _orchestrators_lock:
            ip_count = sum(1 for (_, _, ip) in _sessions.values() if ip == client_ip)
            if ip_count >= _MAX_SESSIONS_PER_IP:
                yield f"data: {json.dumps({'type': 'error', 'data': f'Too many concurrent sessions (max {_MAX_SESSIONS_PER_IP}). Please wait for current stories to finish.'})}\n\n"
                return

        orch = PipelineOrchestrator()
        session_id = str(uuid.uuid4())
        async with _orchestrators_lock:
            _sessions[session_id] = (orch, time.time(), client_ip)

        logs = []
        progress_queue: _queue.Queue = _queue.Queue()
        stream_text = [""]

        def on_progress(msg):
            logs.append(msg)
            # put_nowait is safe: called from asyncio.to_thread workers (thread pool)
            # but the queue itself is asyncio-safe for cross-thread puts.
            progress_queue.put_nowait(("log", msg))

        last_stream_time = [0.0]

        def on_stream(partial_text):
            stream_text[0] = partial_text
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

        result: list = [None]

        async def _run_async():
            try:
                result[0] = await orch.run_full_pipeline(
                    title=body.title or f"Truyện {body.genre}",
                    genre=body.genre,
                    idea=idea,
                    style=body.style,
                    num_chapters=body.num_chapters,
                    num_characters=body.num_characters,
                    word_count=body.word_count,
                    num_sim_rounds=body.num_sim_rounds,
                    progress_callback=on_progress,
                    stream_callback=on_stream,
                    enable_agents=body.enable_agents,
                    enable_scoring=body.enable_scoring,
                    enable_media=body.enable_media,
                )
            except asyncio.CancelledError:
                logger.info(f"Pipeline task cancelled (session={session_id})")
                raise
            except (ValueError, TypeError) as e:
                logger.warning(f"Pipeline input error (session={session_id}): {e}")
                progress_queue.put_nowait(("error", "Invalid pipeline input. Please check your settings."))
            except (TimeoutError, ConnectionError) as e:
                logger.error(f"Pipeline network error (session={session_id}): {e}")
                progress_queue.put_nowait(("error", "Network error during pipeline. Please try again."))
            except Exception as e:
                logger.exception(f"Pipeline error (session={session_id}): {e}")
                progress_queue.put_nowait(("error", "An unexpected error occurred. Please try again."))

        task = asyncio.create_task(_run_async())
        _active_tasks.add(task)
        task.add_done_callback(_active_tasks.discard)

        try:
            # Send session_id first
            yield f"data: {json.dumps({'type': 'session', 'session_id': session_id})}\n\n"

            while not task.done():
                # Check for client disconnect
                if await request.is_disconnected():
                    logger.info(f"Client disconnected from /run stream (session={session_id})")
                    task.cancel()
                    return
                try:
                    msg_type, msg_data = await asyncio.to_thread(progress_queue.get, timeout=0.2)
                    # Drain queue for latest stream event
                    while True:
                        try:
                            t, d = progress_queue.get_nowait()
                            if t == "stream":
                                msg_type, msg_data = t, d
                            elif t == "error":
                                msg_type, msg_data = t, d
                        except _queue.Empty:
                            break
                    event = {"type": msg_type, "data": msg_data}
                    if msg_type == "log":
                        event["logs_count"] = len(logs)
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                except _queue.Empty:
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

            # Send final result
            output = result[0]
            if output:
                from api.pipeline_output_builder import build_output_summary
                safe_output = output.model_copy(deep=True)
                summary = build_output_summary(safe_output)
                summary["session_id"] = session_id
                summary["logs"] = logs
                _sanitize_summary(summary)
                yield f"data: {json.dumps({'type': 'done', 'data': summary}, ensure_ascii=False, default=str)}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'error', 'data': 'Pipeline thất bại'})}\n\n"
        except asyncio.CancelledError:
            logger.info(f"SSE /run stream cancelled (session={session_id})")
            if not task.done():
                task.cancel()
        except (ConnectionError, ConnectionResetError):
            logger.info(f"SSE /run client connection lost (session={session_id})")
            if not task.done():
                task.cancel()
        except (ValueError, TypeError) as e:
            logger.warning(f"SSE /run serialization error (session={session_id}): {e}")
            if not task.done():
                task.cancel()
        except Exception:
            logger.exception(f"SSE /run unexpected error (session={session_id})")
            if not task.done():
                task.cancel()
            raise
        finally:
            async with _orchestrators_lock:
                _sessions.pop(session_id, None)
            logger.debug(f"SSE /run stream closed (session={session_id})")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/resume")
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
        async with _orchestrators_lock:
            ip_count = sum(1 for (_, _, ip) in _sessions.values() if ip == client_ip)
            if ip_count >= _MAX_SESSIONS_PER_IP:
                yield f"data: {json.dumps({'type': 'error', 'data': f'Too many concurrent sessions (max {_MAX_SESSIONS_PER_IP}). Please wait for current stories to finish.'})}\n\n"
                return

        orch = PipelineOrchestrator()
        session_id = str(uuid.uuid4())
        async with _orchestrators_lock:
            _sessions[session_id] = (orch, time.time(), client_ip)

        logs = []
        progress_queue: _queue.Queue = _queue.Queue()

        def on_progress(msg):
            logs.append(msg)
            progress_queue.put_nowait(("log", msg))

        result: list = [None]

        async def _run_async():
            try:
                result[0] = await asyncio.to_thread(
                    orch.resume_from_checkpoint,
                    checkpoint_path=str(checkpoint_path),
                    progress_callback=on_progress,
                )
            except asyncio.CancelledError:
                logger.info(f"Resume task cancelled (session={session_id})")
                raise
            except (ValueError, TypeError) as e:
                logger.warning(f"Resume input error (session={session_id}): {e}")
                progress_queue.put_nowait(("error", "Invalid checkpoint data. The file may be corrupted."))
            except (TimeoutError, ConnectionError) as e:
                logger.error(f"Resume network error (session={session_id}): {e}")
                progress_queue.put_nowait(("error", "Network error during resume. Please try again."))
            except Exception as e:
                logger.exception(f"Resume error (session={session_id}): {e}")
                progress_queue.put_nowait(("error", "An unexpected error occurred. Please try again."))

        task = asyncio.create_task(_run_async())
        _active_tasks.add(task)
        task.add_done_callback(_active_tasks.discard)

        try:
            yield f"data: {json.dumps({'type': 'session', 'session_id': session_id})}\n\n"

            while not task.done():
                # Check for client disconnect
                if await request.is_disconnected():
                    logger.info(f"Client disconnected from /resume stream (session={session_id})")
                    task.cancel()
                    return
                try:
                    msg_type, msg_data = await asyncio.to_thread(progress_queue.get, timeout=0.2)
                    while True:
                        try:
                            t, d = progress_queue.get_nowait()
                            if t == "error":
                                msg_type, msg_data = t, d
                        except _queue.Empty:
                            break
                    event = {"type": msg_type, "data": msg_data}
                    if msg_type == "log":
                        event["logs_count"] = len(logs)
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                except _queue.Empty:
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

            output = result[0]
            if output:
                from api.pipeline_output_builder import build_output_summary
                safe_output = output.model_copy(deep=True)
                summary = build_output_summary(safe_output)
                summary["session_id"] = session_id
                summary["logs"] = logs
                _sanitize_summary(summary)
                yield f"data: {json.dumps({'type': 'done', 'data': summary}, ensure_ascii=False, default=str)}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'error', 'data': 'Resume failed'})}\n\n"
        except asyncio.CancelledError:
            logger.info(f"SSE /resume stream cancelled (session={session_id})")
            if not task.done():
                task.cancel()
        except (ConnectionError, ConnectionResetError):
            logger.info(f"SSE /resume client connection lost (session={session_id})")
            if not task.done():
                task.cancel()
        except (ValueError, TypeError) as e:
            logger.warning(f"SSE /resume serialization error (session={session_id}): {e}")
            if not task.done():
                task.cancel()
        except Exception:
            logger.exception(f"SSE /resume unexpected error (session={session_id})")
            if not task.done():
                task.cancel()
            raise
        finally:
            async with _orchestrators_lock:
                _sessions.pop(session_id, None)
            logger.debug(f"SSE /resume stream closed (session={session_id})")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
