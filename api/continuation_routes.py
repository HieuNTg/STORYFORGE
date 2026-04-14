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

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from api.pipeline_output_builder import build_output_summary
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


class OutlineWriteRequest(BaseModel):
    """Request body for writing chapters from user-edited outlines."""
    checkpoint: str
    outlines: list[dict] = Field(..., description="User-edited ChapterOutline dicts")
    word_count: int = Field(2000, ge=100, le=20000)
    style: str = Field("", max_length=100)


class InsertChapterRequest(BaseModel):
    """Request body for inserting a chapter between existing chapters."""
    checkpoint: str
    insert_after: int = Field(..., ge=0, description="Insert after this chapter (0 = insert at beginning)")
    title: str = Field("", max_length=200, description="Optional title for inserted chapter")
    summary: str = Field("", max_length=2000, description="Optional summary/direction for inserted chapter")
    word_count: int = Field(2000, ge=100, le=20000)
    style: str = Field("", max_length=100)


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
    from models.schemas import ChapterOutline

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
        async def _err():
            yield f"data: {json.dumps({'type': 'error', 'data': f'Invalid outlines: {e}'})}\n\n"
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
