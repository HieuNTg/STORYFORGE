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
import sys
import time
import warnings

warnings.filterwarnings(
    "ignore",
    message=r"Failed to find (cuobjdump|nvdisasm)\.exe",
    module=r"triton\..*",
)

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
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

logger = logging.getLogger(__name__)

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


def _preflight_check() -> bool:
    """Validate DB and Redis connectivity before starting the server.

    Returns True if all required services are reachable, False otherwise.

    DB failure is always fatal. Redis failure is fatal only when
    STORYFORGE_REDIS_REQUIRED=1, otherwise it is logged as a warning.
    """
    from api.health_routes import _check_database, _check_redis

    all_ok = True

    # --- Database (required) ---
    db_result = _check_database()
    db_status = db_result.get("status")
    if db_status == "ok":
        logger.info("Preflight: database OK")
    elif db_status == "not_configured":
        logger.info("Preflight: database not configured — skipping")
    else:
        logger.error(
            "Preflight: database UNREACHABLE (%s) — cannot start",
            db_result.get("detail", db_status),
        )
        all_ok = False

    # --- Redis (optional unless STORYFORGE_REDIS_REQUIRED=1) ---
    redis_result = _check_redis()
    redis_status = redis_result.get("status")
    redis_required = os.environ.get("STORYFORGE_REDIS_REQUIRED", "").lower() in ("1", "true")

    if redis_status == "ok":
        logger.info("Preflight: Redis OK")
    elif redis_status == "not_configured":
        logger.info("Preflight: Redis not configured — running without cache")
    elif redis_required:
        logger.error(
            "Preflight: Redis UNREACHABLE (%s) and STORYFORGE_REDIS_REQUIRED=1 — cannot start",
            redis_result.get("detail", redis_status),
        )
        all_ok = False
    else:
        logger.warning(
            "Preflight: Redis unavailable (%s) — continuing without cache (set "
            "STORYFORGE_REDIS_REQUIRED=1 to make this fatal)",
            redis_result.get("detail", redis_status),
        )

    return all_ok


def main():
    """Launch StoryForge — Alpine.js Web UI at /."""
    from api import api_router

    # STORYFORGE_ENABLE_DOCS defaults to "1" (enabled). Set to "0" in production
    # to hide /docs and /redoc from the public route inventory.
    _docs_enabled = os.environ.get("STORYFORGE_ENABLE_DOCS", "1") not in ("0", "false", "no")
    main_app = FastAPI(
        title="StoryForge",
        description=(
            "AI-powered story generation platform. "
            "Generate long-form Vietnamese stories with multi-layer pipeline: "
            "story generation, drama simulation, and video storyboarding."
        ),
        version="3.0.0",
        docs_url="/docs" if _docs_enabled else None,
        redoc_url="/redoc" if _docs_enabled else None,
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

    # --- GZip compression (≥1KB responses; HTML/JS/CSS shrink ~5–7×) ---
    main_app.add_middleware(GZipMiddleware, minimum_size=1024, compresslevel=6)

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

    # --- Input sanitization middleware (prompt injection detection) ---
    from middleware.sanitization import SanitizationMiddleware
    main_app.add_middleware(SanitizationMiddleware)

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

    # Global exception handler: log full traceback, return generic 500.
    # Must be registered AFTER domain-specific handlers so those still fire first.
    from api import register_exception_handlers
    register_exception_handlers(main_app)

    from fastapi.responses import JSONResponse
    from services.security.input_sanitizer import InjectionBlockedError

    @main_app.exception_handler(InjectionBlockedError)
    async def injection_blocked_handler(request, exc):
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    # Sprint 2 P2: wire embedding cache to service singleton (lazy — model not loaded here)
    @main_app.on_event("startup")
    async def on_startup():
        from services.infra.database import init_db
        await init_db()
        from services.embedding_service import get_embedding_service
        from services.embedding_cache import get_embedding_cache
        get_embedding_service().attach_cache(get_embedding_cache())
        logger.info("EmbeddingCache attached to EmbeddingService")
        from api.pipeline_routes import start_session_reaper
        start_session_reaper()
        logger.info("Session reaper started")

    # Graceful shutdown: cancel and await active pipeline tasks
    @main_app.on_event("shutdown")
    async def on_shutdown():
        from api.pipeline_routes import shutdown_pipeline_tasks
        await shutdown_pipeline_tasks(timeout=30)

    # API routes
    main_app.include_router(api_router)

    # --- API v1 versioned routes (mirrors /api/ with version header) ---
    from api.v1 import v1_router, DeprecationMiddleware
    main_app.include_router(v1_router)
    main_app.add_middleware(DeprecationMiddleware)

    # --- Body size limit (outermost — runs first, blocks oversized requests early) ---
    from starlette.middleware.base import BaseHTTPMiddleware
    from fastapi import Request
    from starlette.responses import JSONResponse as _SJSONResponse

    MAX_BODY_SIZE = 10 * 1024 * 1024  # 10 MB

    class BodySizeLimitMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            content_length = request.headers.get("content-length")
            if content_length and int(content_length) > MAX_BODY_SIZE:
                return _SJSONResponse(
                    status_code=413,
                    content={"detail": "Request body too large. Maximum size is 10MB."}
                )
            return await call_next(request)

    main_app.add_middleware(BodySizeLimitMiddleware)

    # Static files
    base_dir = os.path.dirname(os.path.abspath(__file__))
    web_dir = os.path.join(base_dir, "web")
    locales_dir = os.path.join(base_dir, "locales")

    # Mount locales FIRST (more specific path takes precedence)
    if os.path.isdir(locales_dir):
        main_app.mount("/static/locales", StaticFiles(directory=locales_dir), name="locales")
    # Then mount web/ for remaining static files
    main_app.mount("/static", StaticFiles(directory=web_dir), name="static")

    # Generated chapter images
    images_dir = os.path.join(base_dir, "output", "images")
    os.makedirs(images_dir, exist_ok=True)
    main_app.mount("/media", StaticFiles(directory=images_dir), name="media")

    # Serve index.html at root
    @main_app.get("/")
    async def serve_index():
        return FileResponse(os.path.join(web_dir, "index.html"))

    @main_app.get("/favicon.svg")
    async def serve_favicon():
        return FileResponse(os.path.join(web_dir, "favicon.svg"), media_type="image/svg+xml")

    # Redirect legacy /dashboard URL to the SPA analytics page (M4-B1).
    from fastapi.responses import RedirectResponse as _RedirectResponse

    @main_app.get("/dashboard")
    async def redirect_dashboard():
        return _RedirectResponse(url="/#/analytics", status_code=301)

    # Health check — lightweight with cached DB/Redis probes (30s TTL)
    from fastapi.responses import JSONResponse as _JSONResponse
    _health_cache: dict = {}
    _HEALTH_CACHE_TTL = 30

    def _cached_check(name: str, check_fn) -> dict:
        cached = _health_cache.get(name)
        now = time.time()
        if cached and now - cached["ts"] < _HEALTH_CACHE_TTL:
            return cached["result"]
        result = check_fn()
        _health_cache[name] = {"result": result, "ts": now}
        return result

    @main_app.get("/api/health")
    async def health():
        from api.health_routes import _check_database, _check_redis
        cfg = ConfigManager()
        llm_ok = bool(cfg.llm.api_key)

        db_status = _cached_check("database", _check_database)
        redis_status = _cached_check("redis", _check_redis)

        db_ok = db_status.get("status") == "ok"
        redis_str = redis_status.get("status", "unknown")
        # Redis is optional (Phase 3) — report "fallback" not "error" when not required
        if redis_str == "error" and os.environ.get(
            "STORYFORGE_REDIS_REQUIRED", ""
        ).lower() not in ("1", "true"):
            redis_str = "fallback"

        degraded = not db_ok and db_status.get("status") != "not_configured"
        status = "degraded" if degraded else "ok"

        return _JSONResponse(
            status_code=503 if degraded else 200,
            content={
                "status": status,
                "version": "3.0",
                "uptime_seconds": round(time.time() - _START_TIME, 1),
                "services": {
                    "llm": llm_ok,
                    "database": db_status.get("status", "unknown"),
                    "redis": redis_str,
                },
            },
        )

    _secret = os.environ.get("STORYFORGE_SECRET_KEY", "")
    if _secret in ("", "change-me-in-production"):
        logger.warning(
            "STORYFORGE_SECRET_KEY is not set or still default — "
            "secrets at rest will NOT be encrypted. "
            "Set a strong key for production use."
        )

    if not _preflight_check():
        logger.error("Preflight checks failed — aborting startup")
        sys.exit(1)

    logger.info("StoryForge starting — Web UI at http://localhost:7860")
    uvicorn.run(main_app, host="0.0.0.0", port=7860, log_level="info")


if __name__ == "__main__":
    main()
