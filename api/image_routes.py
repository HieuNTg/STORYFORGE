"""Image generation API routes — wraps services.handlers.handle_generate_images.

Accepts either an active in-memory session id OR a checkpoint filename
(*.json) so library/reader pages can trigger image generation post-hoc.
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.export_routes import _get_story_data

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/images", tags=["images"])


class GenerateImagesRequest(BaseModel):
    """Optional provider override; falls back to config.pipeline.image_provider."""
    provider: Optional[str] = None


class GenerateImagesResponse(BaseModel):
    image_paths: list[str]
    message: str
    count: int


@router.post("/{session_id}/generate", response_model=GenerateImagesResponse)
async def generate_images(session_id: str, body: GenerateImagesRequest = GenerateImagesRequest()):
    """Generate one image per chapter for the given session or checkpoint.

    `session_id` may be an active orchestrator session UUID or a checkpoint
    filename (e.g. ``story_<id>.json``). Provider falls back to
    ``config.pipeline.image_provider`` (default ``"none"`` short-circuits).
    """
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
    paths, msg = handle_generate_images(orch, provider=provider)

    return GenerateImagesResponse(
        image_paths=paths,
        message=msg,
        count=len(paths),
    )
