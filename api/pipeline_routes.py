"""Pipeline API routes — run pipeline via SSE, get genres/templates/checkpoints."""

import json
import logging
import os
import queue
import threading
import time
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional

from services.i18n import I18n
from pipeline.orchestrator import PipelineOrchestrator

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/pipeline", tags=["pipeline"])

# Shared orchestrator instance per session (simple global for now)
_orchestrators: dict[str, PipelineOrchestrator] = {}

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
    shots_per_chapter: int = 8
    enable_agents: bool = True
    enable_scoring: bool = True
    enable_media: bool = False


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
    """List available checkpoints."""
    from ui.handlers import get_checkpoint_choices
    return {"checkpoints": get_checkpoint_choices()}


@router.post("/run")
async def run_pipeline(body: PipelineRequest):
    """Run the full pipeline, streaming progress via SSE."""
    # Validate input
    idea = (body.idea or "").strip()
    if not idea or len(idea) < 10:
        return {"error": _t("error.idea_too_short")}

    def event_generator():
        orch = PipelineOrchestrator()
        session_id = str(id(orch))
        _orchestrators[session_id] = orch

        logs = []
        progress_queue = queue.Queue()
        stream_text = [""]

        def on_progress(msg):
            logs.append(msg)
            progress_queue.put(("log", msg))

        last_stream_time = [0.0]

        def on_stream(partial_text):
            stream_text[0] = partial_text
            now = time.time()
            if now - last_stream_time[0] > 0.3:
                progress_queue.put(("stream", partial_text))
                last_stream_time[0] = now

        result = [None]

        def _run():
            try:
                result[0] = orch.run_full_pipeline(
                    title=body.title or f"Truyện {body.genre}",
                    genre=body.genre,
                    idea=idea,
                    style=body.style,
                    num_chapters=body.num_chapters,
                    num_characters=body.num_characters,
                    word_count=body.word_count,
                    num_sim_rounds=body.num_sim_rounds,
                    shots_per_chapter=body.shots_per_chapter,
                    progress_callback=on_progress,
                    stream_callback=on_stream,
                    enable_agents=body.enable_agents,
                    enable_scoring=body.enable_scoring,
                    enable_media=body.enable_media,
                )
            except Exception as e:
                logger.error(f"Pipeline error: {e}")
                progress_queue.put(("error", str(e)))

        thread = threading.Thread(target=_run)
        thread.start()

        # Send session_id first
        yield f"data: {json.dumps({'type': 'session', 'session_id': session_id})}\n\n"

        while thread.is_alive():
            try:
                msg_type, msg_data = progress_queue.get(timeout=0.2)
                # Drain queue for latest stream
                while not progress_queue.empty():
                    try:
                        t, d = progress_queue.get_nowait()
                        if t == "stream":
                            msg_type, msg_data = t, d
                        elif t == "error":
                            msg_type, msg_data = t, d
                    except queue.Empty:
                        break
                event = {"type": msg_type, "data": msg_data}
                if msg_type == "log":
                    event["logs_count"] = len(logs)
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            except queue.Empty:
                continue

        thread.join()

        # Send final result
        output = result[0]
        if output:
            from api.pipeline_output_builder import build_output_summary
            summary = build_output_summary(output)
            summary["session_id"] = session_id
            summary["logs"] = logs
            yield f"data: {json.dumps({'type': 'done', 'data': summary}, ensure_ascii=False, default=str)}\n\n"
        else:
            yield f"data: {json.dumps({'type': 'error', 'data': 'Pipeline thất bại'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


