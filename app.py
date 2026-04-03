"""StoryForge — thin entry point.

Starts FastAPI, mounts API routes and static files.
The UI is served from web/ as a static Alpine.js SPA.

CORS policy:
  Allowed origins are read from the STORYFORGE_ALLOWED_ORIGINS env var
  (comma-separated list). Defaults to localhost:7860 only.
  Wildcard "*" is intentionally NOT used — set explicit origins for production.
"""

import logging
import logging.handlers
import os
import shutil
import time

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from config import ConfigManager

# Logging
from services.structured_logger import configure_logging
configure_logging()

# Replace the plain FileHandler with a RotatingFileHandler
# so log files never grow unbounded (D4: log rotation).
_root_logger = logging.getLogger()
for _h in list(_root_logger.handlers):
    if isinstance(_h, logging.FileHandler) and not isinstance(
        _h, logging.handlers.RotatingFileHandler
    ):
        _fmt = _h.formatter
        _root_logger.removeHandler(_h)
        _h.close()
        _rotating = logging.handlers.RotatingFileHandler(
            "storyforge.log",
            maxBytes=10 * 1024 * 1024,  # 10 MB per file
            backupCount=5,
            encoding="utf-8",
        )
        _rotating.setFormatter(_fmt)
        _root_logger.addHandler(_rotating)
        break

# FFmpeg availability check (D6: clear dependency status)
_FFMPEG_AVAILABLE: bool = shutil.which("ffmpeg") is not None

logger = logging.getLogger(__name__)

if not _FFMPEG_AVAILABLE:
    logger.warning("FFmpeg not found — video features disabled")

# Uptime tracking
_START_TIME = time.time()

# ---------------------------------------------------------------------------
# CORS configuration helpers
# ---------------------------------------------------------------------------
#
# SEC-5 CORS Audit (Sprint 15) — verified safe:
#   - No wildcard '*' is used in production. Wildcard entries in
#     STORYFORGE_ALLOWED_ORIGINS are detected and rejected with a warning.
#   - Default fallback is localhost:7860 only (safe for development).
#   - Production deployments MUST set STORYFORGE_ALLOWED_ORIGINS to the
#     explicit list of frontend origins, e.g.:
#       STORYFORGE_ALLOWED_ORIGINS=https://app.storyforge.io,https://www.storyforge.io
#   - Credentials are allowed (allow_credentials=True), requiring explicit
#     origins — this is incompatible with '*' by the CORS spec.
#   - Allowed methods: GET, POST, PUT, DELETE, OPTIONS (no TRACE/CONNECT).
#   - Allowed headers: Authorization, Content-Type, Accept (minimal set).
#
_DEFAULT_ORIGINS = ["http://localhost:7860", "http://127.0.0.1:7860"]


def _get_allowed_origins() -> list[str]:
    """Read allowed CORS origins from STORYFORGE_ALLOWED_ORIGINS env var.

    Falls back to localhost:7860 defaults. Rejects wildcard '*' with a warning.

    Production usage:
        export STORYFORGE_ALLOWED_ORIGINS="https://app.storyforge.io,https://cdn.storyforge.io"
    """
    raw = os.environ.get("STORYFORGE_ALLOWED_ORIGINS", "")
    if raw.strip():
        origins = [o.strip() for o in raw.split(",") if o.strip()]
        if "*" in origins:
            logger.warning(
                "STORYFORGE_ALLOWED_ORIGINS contains '*' — ignoring and using "
                "safe defaults instead. Set explicit origins for production."
            )
            return _DEFAULT_ORIGINS
        return origins
    return _DEFAULT_ORIGINS


def main():
    """Launch StoryForge — Alpine.js Web UI at /."""
    from api import api_router

    main_app = FastAPI(
        title="StoryForge",
        description=(
            "AI-powered story generation platform. "
            "Generate long-form Vietnamese stories with multi-layer pipeline: "
            "story generation, drama simulation, and video storyboarding."
        ),
        version="3.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_tags=[
            {"name": "pipeline", "description": "Run and manage story generation pipelines"},
            {"name": "config", "description": "Manage application configuration and model presets"},
            {"name": "export", "description": "Export stories to PDF, EPUB, and other formats"},
            {"name": "analytics", "description": "Usage analytics and story statistics"},
            {"name": "metrics", "description": "System performance metrics"},
            {"name": "dashboard", "description": "Dashboard summary data"},
            {"name": "auth", "description": "Authentication and user management"},
            {"name": "ab", "description": "A/B testing for pipeline variants"},
            {"name": "branch", "description": "Story branching and alternate paths"},
            {"name": "audio", "description": "Text-to-speech and audio generation"},
        ],
    )

    # --- CORS middleware (restrictive: explicit origins only, no wildcard) ---
    allowed_origins = _get_allowed_origins()
    logger.info(f"CORS allowed origins: {allowed_origins}")
    main_app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Accept", "X-CSRF-Token"],
    )

    # --- CSRF protection middleware (double-submit cookie) ---
    from middleware.csrf import CSRFMiddleware
    main_app.add_middleware(CSRFMiddleware)

    # --- Request trace ID middleware (must be outermost so all downstream layers see it) ---
    from middleware.trace_id import TraceIDMiddleware
    main_app.add_middleware(TraceIDMiddleware)

    # --- Security headers middleware (CSP, X-Frame-Options, etc.) ---
    from middleware.security_headers import SecurityHeadersMiddleware
    main_app.add_middleware(SecurityHeadersMiddleware)

    # --- Rate limiting middleware (Redis or in-memory, per-IP) ---
    from middleware.rate_limiter import RateLimitMiddleware
    main_app.add_middleware(RateLimitMiddleware)

    # --- Audit logging middleware ---
    from middleware.audit_middleware import AuditMiddleware
    main_app.add_middleware(AuditMiddleware)

    # --- Request metrics middleware ---
    from middleware.metrics_middleware import MetricsMiddleware
    main_app.add_middleware(MetricsMiddleware)

    from errors.exceptions import StoryForgeError
    from errors.handlers import storyforge_error_handler
    main_app.add_exception_handler(StoryForgeError, storyforge_error_handler)

    from fastapi.responses import JSONResponse
    from services.input_sanitizer import InjectionBlockedError

    @main_app.exception_handler(InjectionBlockedError)
    async def injection_blocked_handler(request, exc):
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    # API routes
    main_app.include_router(api_router)

    # --- API v1 versioned routes (mirrors /api/ with version header) ---
    from api.v1 import v1_router, DeprecationMiddleware
    main_app.include_router(v1_router)
    main_app.add_middleware(DeprecationMiddleware)

    # Static files (web/)
    web_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
    main_app.mount("/static", StaticFiles(directory=web_dir), name="static")

    # Serve index.html at root
    @main_app.get("/")
    async def serve_index():
        return FileResponse(os.path.join(web_dir, "index.html"))

    # Health check
    @main_app.get("/api/health")
    async def health():
        cfg = ConfigManager()
        llm_ok = bool(cfg.llm.api_key)
        return {
            "status": "ok",
            "version": "3.0",
            "uptime_seconds": round(time.time() - _START_TIME, 1),
            "services": {
                "llm": llm_ok,
                "ffmpeg": _FFMPEG_AVAILABLE,
            },
        }

    logger.info("StoryForge starting — Web UI at http://localhost:7860")
    uvicorn.run(main_app, host="0.0.0.0", port=7860, log_level="info")


if __name__ == "__main__":
    main()
