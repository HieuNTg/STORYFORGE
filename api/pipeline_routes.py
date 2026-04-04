"""Pipeline API routes — run pipeline via SSE, get genres/templates/checkpoints."""

import asyncio
import json
import logging
import queue as _queue
import os
import time
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

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
_orchestrators: dict[str, PipelineOrchestrator] = {}
_orchestrators_lock = asyncio.Lock()

# Active pipeline tasks — tracked for graceful shutdown.
_active_tasks: set[asyncio.Task] = set()


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
    title: str = ""
    genre: str = "Tiên Hiệp"
    style: str = "Miêu tả chi tiết"
    idea: str = ""
    num_chapters: int = 5
    num_characters: int = 5
    word_count: int = 2000
    num_sim_rounds: int = 3
    drama_level: str = "cao"
    enable_agents: bool = True
    enable_scoring: bool = True
    enable_media: bool = False
    lite_mode: bool = False


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

    async def event_generator():
        orch = PipelineOrchestrator()
        session_id = str(id(orch))
        async with _orchestrators_lock:
            _orchestrators[session_id] = orch

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
            except Exception as e:
                logger.error(f"Pipeline error: {e}")
                progress_queue.put_nowait(("error", str(e)))

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
        except Exception as e:
            logger.error(f"SSE stream error (session={session_id}): {e}")
            if not task.done():
                task.cancel()
        finally:
            async with _orchestrators_lock:
                _orchestrators.pop(session_id, None)
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

    async def event_generator():
        orch = PipelineOrchestrator()
        session_id = str(id(orch))
        async with _orchestrators_lock:
            _orchestrators[session_id] = orch

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
            except Exception as e:
                logger.error(f"Resume error: {e}")
                progress_queue.put_nowait(("error", str(e)))

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
        except Exception as e:
            logger.error(f"SSE stream error (session={session_id}): {e}")
            if not task.done():
                task.cancel()
        finally:
            async with _orchestrators_lock:
                _orchestrators.pop(session_id, None)
            logger.debug(f"SSE /resume stream closed (session={session_id})")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
