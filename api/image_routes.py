"""Image generation API routes — wraps services.handlers.handle_generate_images.

Accepts either an active in-memory session id OR a checkpoint filename
(*.json) so library/reader pages can trigger image generation post-hoc.

Image generation is sync + slow (per-chapter HTTP calls), so we run it
on a worker thread and guard against duplicate concurrent runs per
session_id with an in-memory in-flight set.
"""

import asyncio
import json
import logging
import pathlib
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.export_routes import _PROJECT_ROOT, _get_story_data

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/images", tags=["images"])

_in_flight: set[str] = set()
_in_flight_lock = asyncio.Lock()


class GenerateImagesRequest(BaseModel):
    provider: Optional[str] = None


class GenerateImagesResponse(BaseModel):
    image_paths: list[str]
    message: str
    count: int
    chapter_images: dict[int, list[str]] = {}


def _persist_to_checkpoint(session_id: str, output) -> None:
    """If session_id is a checkpoint filename, rewrite the file with updated chapter.images."""
    if not session_id.endswith(".json"):
        return
    checkpoint_dir = (_PROJECT_ROOT / "output" / "checkpoints").resolve()
    safe_name = pathlib.Path(session_id).name
    checkpoint_path = (checkpoint_dir / safe_name).resolve()
    try:
        checkpoint_path.relative_to(checkpoint_dir)
    except ValueError:
        logger.warning(f"Refusing to write outside checkpoint dir: {session_id}")
        return
    if not checkpoint_path.exists():
        return
    try:
        with open(checkpoint_path, "w", encoding="utf-8") as f:
            json.dump(output.model_dump(mode="json"), f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"Failed to persist images into checkpoint {safe_name}: {e}")


@router.post("/{session_id}/generate", response_model=GenerateImagesResponse)
async def generate_images(session_id: str, body: GenerateImagesRequest = GenerateImagesRequest()):
    """Generate one image per chapter for the given session or checkpoint.

    `session_id` may be an active orchestrator session UUID or a checkpoint
    filename (e.g. ``story_<id>.json``). Provider falls back to
    ``config.pipeline.image_provider`` (default ``"none"`` short-circuits).
    """
    async with _in_flight_lock:
        if session_id in _in_flight:
            raise HTTPException(status_code=409, detail="Image generation already in progress for this story")
        _in_flight.add(session_id)

    try:
        orch = await _get_story_data(session_id)
        if not orch or not orch.output:
            raise HTTPException(status_code=404, detail="Session or checkpoint not found")

        provider = body.provider
        if not provider:
            try:
                from config import ConfigManager
                provider = getattr(ConfigManager().load().pipeline, "image_provider", "none") or "none"
            except Exception:
                provider = "none"

        from services.handlers import handle_generate_images
        # handle_generate_images is sync + does N blocking HTTP calls — run off-loop
        paths, msg = await asyncio.to_thread(handle_generate_images, orch, provider)

        _persist_to_checkpoint(session_id, orch.output)

        story = orch.output.enhanced_story or orch.output.story_draft
        chapter_images: dict[int, list[str]] = {}
        if story and story.chapters:
            for ch in story.chapters:
                if getattr(ch, "images", None):
                    chapter_images[ch.chapter_number] = list(ch.images)

        return GenerateImagesResponse(
            image_paths=paths,
            message=msg,
            count=len(paths),
            chapter_images=chapter_images,
        )
    finally:
        async with _in_flight_lock:
            _in_flight.discard(session_id)
