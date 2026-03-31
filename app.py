"""StoryForge — thin entry point.

Starts FastAPI, mounts API routes, static files, and Gradio UI.
All UI logic lives in ui/gradio_app.py.
"""

import logging
import os
import time

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from config import ConfigManager

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("storyforge.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

# Uptime tracking
_START_TIME = time.time()


def main():
    """Launch StoryForge — Web UI at / | Gradio fallback at /gradio."""
    from api import api_router
    from ui.gradio_app import create_ui, set_start_time

    set_start_time(_START_TIME)

    main_app = FastAPI(title="StoryForge")

    # API routes
    main_app.include_router(api_router)

    # Static files (web/)
    web_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
    main_app.mount("/static", StaticFiles(directory=web_dir), name="static")

    # Gradio UI at /gradio
    gradio_app = create_ui()
    gradio_app = gradio_app.queue()
    main_app.mount("/gradio", gradio_app.app)

    # Serve index.html at root
    @main_app.get("/")
    async def serve_index():
        return FileResponse(os.path.join(web_dir, "index.html"))

    # Health check
    @main_app.get("/api/health")
    async def health():
        cfg = ConfigManager()
        llm_ok = bool(cfg.llm.api_key) or cfg.llm.backend_type != "api"
        return {
            "status": "ok",
            "version": "3.0",
            "uptime_seconds": round(time.time() - _START_TIME, 1),
            "services": {"llm": llm_ok},
        }

    logger.info(
        "StoryForge starting — Web UI at http://localhost:7860 "
        "| Gradio at http://localhost:7860/gradio"
    )
    uvicorn.run(main_app, host="0.0.0.0", port=7860, log_level="info")


if __name__ == "__main__":
    main()
