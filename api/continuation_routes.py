"""Continuation API routes — continue an existing story with new chapters via SSE."""

import asyncio
import json
import logging
import os
import pathlib
import queue as _queue
import shutil
import time
import uuid

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field

from api.pipeline_output_builder import build_output_summary
from models.schemas import ArcDirective, ChapterOutline
from api.pipeline_routes import (
    _active_tasks,
    _orchestrators_lock,
    _sanitize_summary,
    _sessions,
    _MAX_SESSIONS_PER_IP,
)
from pipeline.orchestrator import PipelineOrchestrator
from services.text_utils import sanitize_story_html

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/pipeline", tags=["continuation"])

_CHECKPOINT_DIR = pathlib.Path(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
).resolve() / "output" / "checkpoints"


class ContinueRequest(BaseModel):
    """Request body for continuing an existing story."""
    checkpoint: str
    additional_chapters: int = Field(5, ge=1, le=50)
    word_count: int = Field(2000, ge=100, le=20000)
    style: str = Field("", max_length=100)
    run_enhancement: bool = False
    num_sim_rounds: int = Field(3, ge=1, le=10)
    arc_directives: list[ArcDirective] = Field(default_factory=list, description="Character arc steering directives")


class RegenerateChapterRequest(BaseModel):
    """Request body for regenerating a specific chapter."""
    checkpoint: str
    chapter_number: int = Field(..., ge=1, description="Chapter to regenerate")
    word_count: int = Field(2000, ge=100, le=20000)
    style: str = Field("", max_length=100)
    preserve_outline: bool = Field(True, description="Keep original outline or regenerate")


class OutlinePreviewRequest(BaseModel):
    """Request body for generating continuation outlines without writing chapters."""
    checkpoint: str
    additional_chapters: int = Field(5, ge=1, le=50)
    arc_directives: list[ArcDirective] = Field(default_factory=list, description="Character arc steering directives")


class OutlineWriteRequest(BaseModel):
    """Request body for writing chapters from user-edited outlines."""
    checkpoint: str
    outlines: list[dict] = Field(..., description="User-edited ChapterOutline dicts")
    word_count: int = Field(2000, ge=100, le=20000)
    style: str = Field("", max_length=100)
    arc_directives: list[ArcDirective] = Field(default_factory=list, description="Character arc steering directives")


class InsertChapterRequest(BaseModel):
    """Request body for inserting a chapter between existing chapters."""
    checkpoint: str
    insert_after: int = Field(..., ge=0, description="Insert after this chapter (0 = insert at beginning)")
    title: str = Field("", max_length=200, description="Optional title for inserted chapter")
    summary: str = Field("", max_length=2000, description="Optional summary/direction for inserted chapter")
    word_count: int = Field(2000, ge=100, le=20000)
    style: str = Field("", max_length=100)


class MultiPathRequest(BaseModel):
    """Request body for generating multiple continuation paths."""
    checkpoint: str
    additional_chapters: int = Field(5, ge=1, le=20)
    num_paths: int = Field(3, ge=2, le=5, description="Number of alternative paths (2-5)")
    arc_directives: list[ArcDirective] = Field(default_factory=list)


class SelectPathRequest(BaseModel):
    """Request body for selecting a path and writing chapters."""
    checkpoint: str
    path_id: str = Field(..., description="ID of the selected path")
    outlines: list[dict] = Field(..., description="ChapterOutline dicts from selected path")
    word_count: int = Field(2000, ge=100, le=20000)
    style: str = Field("", max_length=100)
    arc_directives: list[ArcDirective] = Field(default_factory=list)


class CollaborativeChapterRequest(BaseModel):
    """Request body for collaborative chapter polishing."""
    checkpoint: str
    chapter_number: int = Field(..., ge=1, description="Which chapter this replaces/adds")
    user_text: str = Field(..., min_length=100, max_length=50000, description="User-written chapter text")
    title: str = Field("", max_length=200, description="Chapter title")
    polish_level: str = Field("light", description="'light' (grammar/flow), 'medium' (+ consistency), 'heavy' (+ style)")


class ConsistencyCheckRequest(BaseModel):
    """Request body for consistency check."""
    checkpoint: str
    chapter_numbers: list[int] = Field(default_factory=list, description="Chapters to check (empty = full story)")


def _resolve_checkpoint(filename: str) -> pathlib.Path | None:
    """Validate and resolve checkpoint path, preventing traversal."""
    safe_name = pathlib.Path(filename).name
    if not safe_name or ".." in filename:
        return None
    resolved = (_CHECKPOINT_DIR / safe_name).resolve()
    if not str(resolved).startswith(str(_CHECKPOINT_DIR)):
        return None
    if not resolved.exists():
        return None
    return resolved


def _backup_checkpoint(checkpoint_path: pathlib.Path) -> None:
    """Copy checkpoint to .bak before overwriting."""
    bak_path = checkpoint_path.with_suffix(checkpoint_path.suffix + ".bak")
    try:
        shutil.copy2(str(checkpoint_path), str(bak_path))
        logger.info("Backed up checkpoint to %s", bak_path.name)
    except OSError as e:
        logger.warning("Failed to backup checkpoint: %s", e)


@router.post("/continue")
async def continue_story(request: Request, body: ContinueRequest):
    """Continue a story from checkpoint, streaming progress via SSE."""
    checkpoint_path = _resolve_checkpoint(body.checkpoint)
    if checkpoint_path is None:
        async def _err():
            yield f"data: {json.dumps({'type': 'error', 'data': 'Checkpoint not found.'})}\n\n"
        return StreamingResponse(
            _err(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    client_ip = request.client.host if request.client else "unknown"

    async def event_generator():
        async with _orchestrators_lock:
            ip_count = sum(1 for (_, _, ip) in _sessions.values() if ip == client_ip)
            if ip_count >= _MAX_SESSIONS_PER_IP:
                yield f"data: {json.dumps({'type': 'error', 'data': f'Too many concurrent sessions (max {_MAX_SESSIONS_PER_IP}).'})}\n\n"
                return

        orch = PipelineOrchestrator()
        session_id = str(uuid.uuid4())

        logs: list[str] = []
        progress_queue: _queue.Queue = _queue.Queue()
        last_stream_time = [0.0]

        def on_progress(msg):
            logs.append(msg)
            progress_queue.put_nowait(("log", msg))

        def on_stream(partial_text):
            now = time.time()
            if now - last_stream_time[0] > 0.3:
                progress_queue.put_nowait(("stream", sanitize_story_html(partial_text)))
                last_stream_time[0] = now

        result: list = [None]

        async def _run_async():
            try:
                await asyncio.to_thread(_backup_checkpoint, checkpoint_path)

                draft = await asyncio.to_thread(
                    orch.load_from_checkpoint, str(checkpoint_path)
                )
                if draft is None:
                    progress_queue.put_nowait(("error", "Failed to load checkpoint data."))
                    return

                on_progress(f"Loaded checkpoint: {checkpoint_path.name}")
                on_progress(f"Existing chapters: {len(draft.chapters)}")
                on_progress(f"Continuing with {body.additional_chapters} new chapters...")

                await asyncio.to_thread(
                    orch.continue_story,
                    additional_chapters=body.additional_chapters,
                    word_count=body.word_count,
                    style=body.style,
                    progress_callback=on_progress,
                    stream_callback=on_stream,
                    arc_directives=body.arc_directives,
                )

                if body.run_enhancement:
                    on_progress("Running Layer 2 enhancement on entire story...")
                    await asyncio.to_thread(
                        orch.enhance_chapters,
                        num_sim_rounds=body.num_sim_rounds,
                        word_count=body.word_count,
                        progress_callback=on_progress,
                    )

                result[0] = orch.output
            except asyncio.CancelledError:
                logger.info("Continue task cancelled (session=%s)", session_id)
                raise
            except (ValueError, TypeError) as e:
                logger.warning("Continue input error (session=%s): %s", session_id, e)
                progress_queue.put_nowait(("error", f"Invalid data: {e}"))
            except (TimeoutError, ConnectionError) as e:
                logger.error("Continue network error (session=%s): %s", session_id, e)
                progress_queue.put_nowait(("error", "Network error. Please try again."))
            except Exception as e:
                logger.exception("Continue error (session=%s): %s", session_id, e)
                progress_queue.put_nowait(("error", "An unexpected error occurred."))

        # Session registration + task creation + SSE streaming all inside try/finally
        # so the finally block always cleans up the session.
        try:
            async with _orchestrators_lock:
                _sessions[session_id] = (orch, time.time(), client_ip)

            task = asyncio.create_task(_run_async())
            _active_tasks.add(task)
            task.add_done_callback(_active_tasks.discard)

            yield f"data: {json.dumps({'type': 'session', 'session_id': session_id})}\n\n"

            while not task.done():
                if await request.is_disconnected():
                    logger.info("Client disconnected from /continue (session=%s)", session_id)
                    task.cancel()
                    return
                try:
                    msg_type, msg_data = await asyncio.to_thread(
                        progress_queue.get, timeout=0.2
                    )
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

            # Drain remaining
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
                safe_output = output.model_copy(deep=True)
                summary = build_output_summary(safe_output)
                summary["session_id"] = session_id
                summary["logs"] = logs
                _sanitize_summary(summary)
                yield f"data: {json.dumps({'type': 'done', 'data': summary}, ensure_ascii=False, default=str)}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'error', 'data': 'Continuation failed'})}\n\n"
        except asyncio.CancelledError:
            logger.info("SSE /continue cancelled (session=%s)", session_id)
            if not task.done():
                task.cancel()
        except (ConnectionError, ConnectionResetError):
            logger.info("SSE /continue connection lost (session=%s)", session_id)
            if not task.done():
                task.cancel()
        except Exception:
            logger.exception("SSE /continue unexpected error (session=%s)", session_id)
            if not task.done():
                task.cancel()
            raise
        finally:
            async with _orchestrators_lock:
                _sessions.pop(session_id, None)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/regenerate-chapter")
async def regenerate_chapter(request: Request, body: RegenerateChapterRequest):
    """Regenerate a specific chapter, streaming progress via SSE."""
    checkpoint_path = _resolve_checkpoint(body.checkpoint)
    if checkpoint_path is None:
        async def _err():
            yield f"data: {json.dumps({'type': 'error', 'data': 'Checkpoint not found.'})}\n\n"
        return StreamingResponse(
            _err(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    client_ip = request.client.host if request.client else "unknown"

    async def event_generator():
        async with _orchestrators_lock:
            ip_count = sum(1 for (_, _, ip) in _sessions.values() if ip == client_ip)
            if ip_count >= _MAX_SESSIONS_PER_IP:
                yield f"data: {json.dumps({'type': 'error', 'data': f'Too many concurrent sessions (max {_MAX_SESSIONS_PER_IP}).'})}\n\n"
                return

        orch = PipelineOrchestrator()
        session_id = str(uuid.uuid4())

        logs: list[str] = []
        progress_queue: _queue.Queue = _queue.Queue()
        last_stream_time = [0.0]

        def on_progress(msg):
            logs.append(msg)
            progress_queue.put_nowait(("log", msg))

        def on_stream(partial_text):
            now = time.time()
            if now - last_stream_time[0] > 0.3:
                progress_queue.put_nowait(("stream", sanitize_story_html(partial_text)))
                last_stream_time[0] = now

        result: list = [None]

        async def _run_async():
            try:
                await asyncio.to_thread(_backup_checkpoint, checkpoint_path)

                draft = await asyncio.to_thread(
                    orch.load_from_checkpoint, str(checkpoint_path)
                )
                if draft is None:
                    progress_queue.put_nowait(("error", "Failed to load checkpoint data."))
                    return

                on_progress(f"Loaded checkpoint: {checkpoint_path.name}")
                on_progress(f"Total chapters: {len(draft.chapters)}")
                on_progress(f"Regenerating chapter {body.chapter_number}...")

                await asyncio.to_thread(
                    orch.regenerate_chapter,
                    chapter_number=body.chapter_number,
                    word_count=body.word_count,
                    style=body.style,
                    preserve_outline=body.preserve_outline,
                    progress_callback=on_progress,
                    stream_callback=on_stream,
                )

                result[0] = orch.output
            except asyncio.CancelledError:
                logger.info("Regenerate task cancelled (session=%s)", session_id)
                raise
            except (ValueError, TypeError) as e:
                logger.warning("Regenerate input error (session=%s): %s", session_id, e)
                progress_queue.put_nowait(("error", f"Invalid data: {e}"))
            except (TimeoutError, ConnectionError) as e:
                logger.error("Regenerate network error (session=%s): %s", session_id, e)
                progress_queue.put_nowait(("error", "Network error. Please try again."))
            except Exception as e:
                logger.exception("Regenerate error (session=%s): %s", session_id, e)
                progress_queue.put_nowait(("error", "An unexpected error occurred."))

        try:
            async with _orchestrators_lock:
                _sessions[session_id] = (orch, time.time(), client_ip)

            task = asyncio.create_task(_run_async())
            _active_tasks.add(task)
            task.add_done_callback(_active_tasks.discard)

            yield f"data: {json.dumps({'type': 'session', 'session_id': session_id})}\n\n"

            while not task.done():
                if await request.is_disconnected():
                    logger.info("Client disconnected from /regenerate-chapter (session=%s)", session_id)
                    task.cancel()
                    return
                try:
                    msg_type, msg_data = await asyncio.to_thread(
                        progress_queue.get, timeout=0.2
                    )
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

            # Drain remaining
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
                safe_output = output.model_copy(deep=True)
                summary = build_output_summary(safe_output)
                summary["session_id"] = session_id
                summary["logs"] = logs
                _sanitize_summary(summary)
                yield f"data: {json.dumps({'type': 'done', 'data': summary}, ensure_ascii=False, default=str)}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'error', 'data': 'Regeneration failed'})}\n\n"
        except asyncio.CancelledError:
            logger.info("SSE /regenerate-chapter cancelled (session=%s)", session_id)
            if not task.done():
                task.cancel()
        except (ConnectionError, ConnectionResetError):
            logger.info("SSE /regenerate-chapter connection lost (session=%s)", session_id)
            if not task.done():
                task.cancel()
        except Exception:
            logger.exception("SSE /regenerate-chapter unexpected error (session=%s)", session_id)
            if not task.done():
                task.cancel()
            raise
        finally:
            async with _orchestrators_lock:
                _sessions.pop(session_id, None)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/continue/outlines")
async def generate_outlines(body: OutlinePreviewRequest):
    """Generate continuation outlines for preview/editing (fast JSON response)."""
    from fastapi.responses import JSONResponse

    checkpoint_path = _resolve_checkpoint(body.checkpoint)
    if checkpoint_path is None:
        return JSONResponse(
            status_code=404,
            content={"error": "Checkpoint not found."},
        )

    orch = PipelineOrchestrator()
    draft = orch.load_from_checkpoint(str(checkpoint_path))
    if draft is None:
        return JSONResponse(
            status_code=400,
            content={"error": "Failed to load checkpoint data."},
        )

    try:
        outlines = orch.generate_continuation_outlines(
            additional_chapters=body.additional_chapters,
            arc_directives=body.arc_directives,
        )
        return {
            "checkpoint": body.checkpoint,
            "existing_chapters": len(draft.chapters),
            "outlines": [o.model_dump() for o in outlines],
        }
    except Exception as e:
        logger.exception("Error generating outlines: %s", e)
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to generate outlines: {e}"},
        )


@router.post("/continue/write")
async def write_from_outlines_endpoint(request: Request, body: OutlineWriteRequest):
    """Write chapters from user-edited outlines, streaming progress via SSE."""
    from models.schemas import ChapterOutline

    checkpoint_path = _resolve_checkpoint(body.checkpoint)
    if checkpoint_path is None:
        async def _err():
            yield f"data: {json.dumps({'type': 'error', 'data': 'Checkpoint not found.'})}\n\n"
        return StreamingResponse(
            _err(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # Parse outlines from dicts
    try:
        outlines = [ChapterOutline(**o) for o in body.outlines]
    except Exception as e:
        err_msg = str(e)  # Capture error message before closure
        async def _err():
            yield f"data: {json.dumps({'type': 'error', 'data': f'Invalid outlines: {err_msg}'})}\n\n"
        return StreamingResponse(
            _err(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    client_ip = request.client.host if request.client else "unknown"

    async def event_generator():
        async with _orchestrators_lock:
            ip_count = sum(1 for (_, _, ip) in _sessions.values() if ip == client_ip)
            if ip_count >= _MAX_SESSIONS_PER_IP:
                yield f"data: {json.dumps({'type': 'error', 'data': f'Too many concurrent sessions (max {_MAX_SESSIONS_PER_IP}).'})}\n\n"
                return

        orch = PipelineOrchestrator()
        session_id = str(uuid.uuid4())

        logs: list[str] = []
        progress_queue: _queue.Queue = _queue.Queue()
        last_stream_time = [0.0]

        def on_progress(msg):
            logs.append(msg)
            progress_queue.put_nowait(("log", msg))

        def on_stream(partial_text):
            now = time.time()
            if now - last_stream_time[0] > 0.3:
                progress_queue.put_nowait(("stream", sanitize_story_html(partial_text)))
                last_stream_time[0] = now

        result: list = [None]

        async def _run_async():
            try:
                await asyncio.to_thread(_backup_checkpoint, checkpoint_path)

                draft = await asyncio.to_thread(
                    orch.load_from_checkpoint, str(checkpoint_path)
                )
                if draft is None:
                    progress_queue.put_nowait(("error", "Failed to load checkpoint data."))
                    return

                on_progress(f"Loaded checkpoint: {checkpoint_path.name}")
                on_progress(f"Existing chapters: {len(draft.chapters)}")
                on_progress(f"Writing {len(outlines)} chapters from edited outlines...")

                await asyncio.to_thread(
                    orch.write_from_outlines,
                    outlines=outlines,
                    word_count=body.word_count,
                    style=body.style,
                    progress_callback=on_progress,
                    stream_callback=on_stream,
                    arc_directives=body.arc_directives,
                )

                result[0] = orch.output
            except asyncio.CancelledError:
                logger.info("Write task cancelled (session=%s)", session_id)
                raise
            except (ValueError, TypeError) as e:
                logger.warning("Write input error (session=%s): %s", session_id, e)
                progress_queue.put_nowait(("error", f"Invalid data: {e}"))
            except (TimeoutError, ConnectionError) as e:
                logger.error("Write network error (session=%s): %s", session_id, e)
                progress_queue.put_nowait(("error", "Network error. Please try again."))
            except Exception as e:
                logger.exception("Write error (session=%s): %s", session_id, e)
                progress_queue.put_nowait(("error", "An unexpected error occurred."))

        try:
            async with _orchestrators_lock:
                _sessions[session_id] = (orch, time.time(), client_ip)

            task = asyncio.create_task(_run_async())
            _active_tasks.add(task)
            task.add_done_callback(_active_tasks.discard)

            yield f"data: {json.dumps({'type': 'session', 'session_id': session_id})}\n\n"

            while not task.done():
                if await request.is_disconnected():
                    logger.info("Client disconnected from /continue/write (session=%s)", session_id)
                    task.cancel()
                    return
                try:
                    msg_type, msg_data = await asyncio.to_thread(
                        progress_queue.get, timeout=0.2
                    )
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

            # Drain remaining
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
                safe_output = output.model_copy(deep=True)
                summary = build_output_summary(safe_output)
                summary["session_id"] = session_id
                summary["logs"] = logs
                _sanitize_summary(summary)
                yield f"data: {json.dumps({'type': 'done', 'data': summary}, ensure_ascii=False, default=str)}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'error', 'data': 'Write from outlines failed'})}\n\n"
        except asyncio.CancelledError:
            logger.info("SSE /continue/write cancelled (session=%s)", session_id)
            if not task.done():
                task.cancel()
        except (ConnectionError, ConnectionResetError):
            logger.info("SSE /continue/write connection lost (session=%s)", session_id)
            if not task.done():
                task.cancel()
        except Exception:
            logger.exception("SSE /continue/write unexpected error (session=%s)", session_id)
            if not task.done():
                task.cancel()
            raise
        finally:
            async with _orchestrators_lock:
                _sessions.pop(session_id, None)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/insert-chapter")
async def insert_chapter(request: Request, body: InsertChapterRequest):
    """Insert a new chapter between existing chapters, streaming progress via SSE."""
    checkpoint_path = _resolve_checkpoint(body.checkpoint)
    if checkpoint_path is None:
        async def _err():
            yield f"data: {json.dumps({'type': 'error', 'data': 'Checkpoint not found.'})}\n\n"
        return StreamingResponse(
            _err(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    client_ip = request.client.host if request.client else "unknown"

    async def event_generator():
        async with _orchestrators_lock:
            ip_count = sum(1 for (_, _, ip) in _sessions.values() if ip == client_ip)
            if ip_count >= _MAX_SESSIONS_PER_IP:
                yield f"data: {json.dumps({'type': 'error', 'data': f'Too many concurrent sessions (max {_MAX_SESSIONS_PER_IP}).'})}\n\n"
                return

        orch = PipelineOrchestrator()
        session_id = str(uuid.uuid4())

        logs: list[str] = []
        progress_queue: _queue.Queue = _queue.Queue()
        last_stream_time = [0.0]

        def on_progress(msg):
            logs.append(msg)
            progress_queue.put_nowait(("log", msg))

        def on_stream(partial_text):
            now = time.time()
            if now - last_stream_time[0] > 0.3:
                progress_queue.put_nowait(("stream", sanitize_story_html(partial_text)))
                last_stream_time[0] = now

        result: list = [None]

        async def _run_async():
            try:
                await asyncio.to_thread(_backup_checkpoint, checkpoint_path)

                draft = await asyncio.to_thread(
                    orch.load_from_checkpoint, str(checkpoint_path)
                )
                if draft is None:
                    progress_queue.put_nowait(("error", "Failed to load checkpoint data."))
                    return

                on_progress(f"Loaded checkpoint: {checkpoint_path.name}")
                on_progress(f"Current chapters: {len(draft.chapters)}")
                on_progress(f"Inserting chapter after position {body.insert_after}...")

                await asyncio.to_thread(
                    orch.insert_chapter,
                    insert_after=body.insert_after,
                    title=body.title,
                    summary=body.summary,
                    word_count=body.word_count,
                    style=body.style,
                    progress_callback=on_progress,
                    stream_callback=on_stream,
                )

                result[0] = orch.output
            except asyncio.CancelledError:
                logger.info("Insert task cancelled (session=%s)", session_id)
                raise
            except (ValueError, TypeError) as e:
                logger.warning("Insert input error (session=%s): %s", session_id, e)
                progress_queue.put_nowait(("error", f"Invalid data: {e}"))
            except (TimeoutError, ConnectionError) as e:
                logger.error("Insert network error (session=%s): %s", session_id, e)
                progress_queue.put_nowait(("error", "Network error. Please try again."))
            except Exception as e:
                logger.exception("Insert error (session=%s): %s", session_id, e)
                progress_queue.put_nowait(("error", "An unexpected error occurred."))

        try:
            async with _orchestrators_lock:
                _sessions[session_id] = (orch, time.time(), client_ip)

            task = asyncio.create_task(_run_async())
            _active_tasks.add(task)
            task.add_done_callback(_active_tasks.discard)

            yield f"data: {json.dumps({'type': 'session', 'session_id': session_id})}\n\n"

            while not task.done():
                if await request.is_disconnected():
                    logger.info("Client disconnected from /insert-chapter (session=%s)", session_id)
                    task.cancel()
                    return
                try:
                    msg_type, msg_data = await asyncio.to_thread(
                        progress_queue.get, timeout=0.2
                    )
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

            # Drain remaining
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
                safe_output = output.model_copy(deep=True)
                summary = build_output_summary(safe_output)
                summary["session_id"] = session_id
                summary["logs"] = logs
                _sanitize_summary(summary)
                yield f"data: {json.dumps({'type': 'done', 'data': summary}, ensure_ascii=False, default=str)}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'error', 'data': 'Chapter insertion failed'})}\n\n"
        except asyncio.CancelledError:
            logger.info("SSE /insert-chapter cancelled (session=%s)", session_id)
            if not task.done():
                task.cancel()
        except (ConnectionError, ConnectionResetError):
            logger.info("SSE /insert-chapter connection lost (session=%s)", session_id)
            if not task.done():
                task.cancel()
        except Exception:
            logger.exception("SSE /insert-chapter unexpected error (session=%s)", session_id)
            if not task.done():
                task.cancel()
            raise
        finally:
            async with _orchestrators_lock:
                _sessions.pop(session_id, None)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ══════════════════════════════════════════════════════════════════════════════
# Multi-path Preview Endpoints
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/continue/paths")
async def generate_continuation_paths(body: MultiPathRequest):
    """Generate multiple alternative continuation paths (outlines only).

    Returns 2-5 different narrative directions, each with outlines.
    User selects preferred path, then calls /continue/select-path to write chapters.
    """
    checkpoint_path = _resolve_checkpoint(body.checkpoint)
    if not checkpoint_path:
        return JSONResponse(
            status_code=404,
            content={"error": f"Checkpoint not found: {body.checkpoint}"},
        )

    orch = PipelineOrchestrator()
    draft = orch.continuation.load_from_checkpoint(str(checkpoint_path))
    if not draft:
        return JSONResponse(
            status_code=500,
            content={"error": "Failed to load checkpoint"},
        )

    try:
        paths = orch.continuation.generate_continuation_paths(
            additional_chapters=body.additional_chapters,
            num_paths=body.num_paths,
            arc_directives=body.arc_directives,
        )
        return {
            "checkpoint": body.checkpoint,
            "existing_chapters": len(draft.chapters),
            "paths": paths,
        }
    except Exception as e:
        logger.exception("Error generating continuation paths: %s", e)
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to generate paths: {e}"},
        )


@router.post("/continue/select-path")
async def select_path_and_write(request: Request, body: SelectPathRequest):
    """Select a path and write chapters from its outlines via SSE.

    After reviewing paths from /continue/paths, user selects one and
    calls this endpoint to write the actual chapters.
    """
    checkpoint_path = _resolve_checkpoint(body.checkpoint)
    session_id = str(uuid.uuid4())

    async def event_generator():
        if not checkpoint_path:
            yield f"data: {json.dumps({'type': 'error', 'data': f'Checkpoint not found: {body.checkpoint}'})}\n\n"
            return

        orch = PipelineOrchestrator()
        draft = orch.continuation.load_from_checkpoint(str(checkpoint_path))
        if not draft:
            yield f"data: {json.dumps({'type': 'error', 'data': 'Failed to load checkpoint'})}\n\n"
            return

        # Parse outlines
        try:
            outlines = [ChapterOutline(**o) for o in body.outlines]
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'data': f'Invalid outlines: {e}'})}\n\n"
            return

        yield f"data: {json.dumps({'type': 'start', 'data': f'Writing {len(outlines)} chapters from path {body.path_id}'})}\n\n"

        msg_queue = _queue.Queue()
        stream_queue = _queue.Queue()
        result = [None]

        def on_progress(msg):
            msg_queue.put(msg)

        def on_stream(chunk):
            stream_queue.put(chunk)

        async def run_write():
            try:
                await asyncio.to_thread(
                    orch.continuation.write_from_outlines,
                    outlines=outlines,
                    word_count=body.word_count,
                    style=body.style,
                    progress_callback=on_progress,
                    stream_callback=on_stream,
                    arc_directives=body.arc_directives,
                )
                result[0] = orch.output
            except asyncio.CancelledError:
                logger.info("Select-path write cancelled (session=%s)", session_id)
            except Exception as e:
                logger.exception("Select-path write error (session=%s): %s", session_id, e)
                msg_queue.put(f"Error: {e}")

        task = asyncio.create_task(run_write())

        try:
            while not task.done():
                if await request.is_disconnected():
                    logger.info("Client disconnected from /select-path (session=%s)", session_id)
                    task.cancel()
                    break
                while not msg_queue.empty():
                    msg = msg_queue.get_nowait()
                    yield f"data: {json.dumps({'type': 'progress', 'data': msg})}\n\n"
                while not stream_queue.empty():
                    chunk = stream_queue.get_nowait()
                    yield f"data: {json.dumps({'type': 'stream', 'data': chunk})}\n\n"
                await asyncio.sleep(0.1)

            # Drain remaining
            while not msg_queue.empty():
                msg = msg_queue.get_nowait()
                yield f"data: {json.dumps({'type': 'progress', 'data': msg})}\n\n"

            if result[0] and result[0].story_draft:
                summary = build_output_summary(result[0])
                summary["path_id"] = body.path_id
                _sanitize_summary(summary)
                yield f"data: {json.dumps({'type': 'done', 'data': summary}, ensure_ascii=False, default=str)}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'error', 'data': 'Failed to write chapters from selected path'})}\n\n"
        except asyncio.CancelledError:
            logger.info("SSE /select-path cancelled (session=%s)", session_id)
            if not task.done():
                task.cancel()
        except Exception:
            logger.exception("SSE /select-path unexpected error (session=%s)", session_id)
            if not task.done():
                task.cancel()
            raise

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ══════════════════════════════════════════════════════════════════════════════
# Phase 7: Collaborative Mode - User writes, pipeline polishes
# ══════════════════════════════════════════════════════════════════════════════


@router.post("/collaborative-chapter")
async def collaborative_chapter(body: CollaborativeChapterRequest):
    """Polish user-written chapter while preserving their voice.

    User provides raw chapter text; pipeline enhances for consistency
    and prose quality without rewriting the narrative.

    Polish levels:
    - light: Grammar, punctuation, minor flow improvements
    - medium: + Prose enhancement, pacing adjustments
    - heavy: + Scene expansion, deeper character voice (still preserves user intent)
    """
    checkpoint_path = _resolve_checkpoint(body.checkpoint)
    if checkpoint_path is None:
        raise HTTPException(status_code=404, detail="Checkpoint not found")

    orch = PipelineOrchestrator()
    draft = orch.continuation.load_from_checkpoint(str(checkpoint_path))
    if draft is None:
        raise HTTPException(status_code=404, detail="Failed to load checkpoint")

    session_id = str(uuid.uuid4())
    cont = orch.continuation

    if body.polish_level not in ("light", "medium", "heavy"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid polish_level '{body.polish_level}'. Must be 'light', 'medium', or 'heavy'",
        )

    msg_queue: _queue.Queue = _queue.Queue()

    def progress_cb(msg: str):
        msg_queue.put(msg)

    result: list = [None]

    def run_polish():
        try:
            draft = cont.polish_chapter(
                chapter_number=body.chapter_number,
                user_text=body.user_text,
                title=body.title,
                polish_level=body.polish_level,
                progress_callback=progress_cb,
            )
            result[0] = draft
        except Exception as e:
            logger.exception("polish_chapter failed")
            msg_queue.put(f"Error: {e}")

    loop = asyncio.get_event_loop()
    task = loop.run_in_executor(None, run_polish)

    async def event_generator():
        try:
            while not task.done():
                while not msg_queue.empty():
                    msg = msg_queue.get_nowait()
                    yield f"data: {json.dumps({'type': 'progress', 'data': msg})}\n\n"
                await asyncio.sleep(0.1)

            # Drain remaining messages
            while not msg_queue.empty():
                msg = msg_queue.get_nowait()
                yield f"data: {json.dumps({'type': 'progress', 'data': msg})}\n\n"

            if result[0]:
                # Return the polished chapter
                chapter = result[0].chapters[body.chapter_number - 1]
                output = {
                    "chapter_number": body.chapter_number,
                    "title": chapter.title,
                    "content": chapter.content,
                    "word_count": len(chapter.content.split()),
                    "polish_level": body.polish_level,
                }
                yield f"data: {json.dumps({'type': 'done', 'data': output}, ensure_ascii=False)}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'error', 'data': 'Failed to polish chapter'})}\n\n"
        except asyncio.CancelledError:
            logger.info("SSE /collaborative-chapter cancelled (session=%s)", session_id)
            if not task.done():
                task.cancel()
        except Exception:
            logger.exception("SSE /collaborative-chapter error (session=%s)", session_id)
            if not task.done():
                task.cancel()
            raise

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ══════════════════════════════════════════════════════════════════════════════
# Phase 8: Retroactive Consistency Fix
# ══════════════════════════════════════════════════════════════════════════════


@router.post("/check-consistency")
async def check_consistency(body: ConsistencyCheckRequest):
    """Check story for consistency issues.

    Scans chapters for contradictions in:
    - Character locations
    - Timeline/sequence
    - Facts and states
    - Object states

    Returns a ConsistencyReport with detected issues and suggested fixes.
    """
    checkpoint_path = _resolve_checkpoint(body.checkpoint)
    if checkpoint_path is None:
        raise HTTPException(status_code=404, detail="Checkpoint not found")

    orch = PipelineOrchestrator()
    draft = orch.continuation.load_from_checkpoint(str(checkpoint_path))
    if draft is None:
        raise HTTPException(status_code=404, detail="Failed to load checkpoint")

    session_id = str(uuid.uuid4())
    cont = orch.continuation

    msg_queue: _queue.Queue = _queue.Queue()

    def progress_cb(msg: str):
        msg_queue.put(msg)

    result: list = [None]

    def run_check():
        try:
            chapters_to_check = body.chapter_numbers if body.chapter_numbers else None
            report = cont.check_consistency(
                chapter_numbers=chapters_to_check,
                progress_callback=progress_cb,
            )
            result[0] = report
        except Exception as e:
            logger.exception("check_consistency failed")
            msg_queue.put(f"Error: {e}")

    loop = asyncio.get_event_loop()
    task = loop.run_in_executor(None, run_check)

    async def event_generator():
        try:
            while not task.done():
                while not msg_queue.empty():
                    msg = msg_queue.get_nowait()
                    yield f"data: {json.dumps({'type': 'progress', 'data': msg})}\n\n"
                await asyncio.sleep(0.1)

            # Drain remaining messages
            while not msg_queue.empty():
                msg = msg_queue.get_nowait()
                yield f"data: {json.dumps({'type': 'progress', 'data': msg})}\n\n"

            if result[0]:
                report = result[0]
                output = {
                    "checked_chapters": report.checked_chapters,
                    "issues": [issue.model_dump() for issue in report.issues],
                    "error_count": report.error_count,
                    "warning_count": report.warning_count,
                    "info_count": report.info_count,
                    "is_consistent": report.is_consistent,
                    "checked_at": report.checked_at,
                }
                yield f"data: {json.dumps({'type': 'done', 'data': output}, ensure_ascii=False)}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'error', 'data': 'Failed to check consistency'})}\n\n"
        except asyncio.CancelledError:
            logger.info("SSE /check-consistency cancelled (session=%s)", session_id)
            if not task.done():
                task.cancel()
        except Exception:
            logger.exception("SSE /check-consistency error (session=%s)", session_id)
            if not task.done():
                task.cancel()
            raise

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
