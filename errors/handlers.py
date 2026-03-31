"""FastAPI exception handlers for consistent error responses."""
import logging
from fastapi import Request
from fastapi.responses import JSONResponse
from errors.exceptions import StoryForgeError

logger = logging.getLogger(__name__)

async def storyforge_error_handler(request: Request, exc: StoryForgeError):
    logger.warning(f"{exc.code}: {exc.message}")
    status_map = {
        "CONFIG_ERROR": 400,
        "INPUT_BLOCKED": 422,
        "LLM_QUOTA_EXHAUSTED": 503,
        "LLM_MODEL_NOT_FOUND": 404,
        "LLM_ERROR": 502,
        "PIPELINE_ERROR": 500,
        "EXPORT_ERROR": 500,
        "STORAGE_ERROR": 500,
    }
    status = status_map.get(exc.code, 500)
    return JSONResponse(status_code=status, content={"error": {"code": exc.code, "message": exc.message}})
