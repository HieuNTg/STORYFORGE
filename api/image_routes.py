"""Image generation API routes — wraps services.handlers.handle_generate_images.

Exposes the existing image-generation handler that was previously only callable
from internal code. Provider is read from PipelineConfig (or override via body).
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.pipeline_routes import _orchestrators

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
def generate_images(session_id: str, body: GenerateImagesRequest = GenerateImagesRequest()):
    """Generate one image per chapter for the given orchestrator session.

    Reads provider from request body when set, otherwise from
    config.pipeline.image_provider (default "none" which short-circuits).
    """
    orch = _orchestrators.get(session_id)
    if not orch or not orch.output:
        raise HTTPException(status_code=404, detail="Session not found")

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
