"""StoryForge — thin entry point.

Starts FastAPI, mounts API routes and static files.
The UI is served by Next.js from frontend/ (run separately on :3000).

CORS policy:
  Allowed origins are the local frontend (:3001) and API (:7860) plus any
  listed in the STORYFORGE_ALLOWED_ORIGINS env var (comma-separated).
  Wildcard "*" is intentionally NOT used — set explicit origins for production.
"""

import logging
import os
import sys
import time
import warnings
from pathlib import Path

warnings.filterwarnings(
    "ignore",
    message=r"Failed to find (cuobjdump|nvdisasm)\.exe",
    module=r"triton\..*",
)

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

from config import ConfigManager
from services.gzipped_static_files import GzippedStaticFiles

# Logging: stdout plus a rotating file under data/logs (in Docker that is the
# storyforge-data volume; the working directory itself is read-only there).
from services.structured_logger import configure_logging

LOG_FILE = Path(__file__).resolve().parent / "data" / "logs" / "storyforge.log"
configure_logging(log_file=LOG_FILE)

logger = logging.getLogger(__name__)

# Uptime tracking
_START_TIME = time.time()

# ---------------------------------------------------------------------------
# CORS configuration helpers
# ---------------------------------------------------------------------------
#
# The allow list lives in middleware/hosts.py (the branch WebSocket checks
# Origin against the same list); re-exported here for callers of app.py.
#   - No wildcard '*': wildcard entries in STORYFORGE_ALLOWED_ORIGINS are
#     dropped with a warning (credentials are allowed, which '*' forbids).
#   - Defaults: the frontend on :3001 and the API on :7860, by name and IP;
#     STORYFORGE_ALLOWED_ORIGINS adds to them.
#   - Allowed methods: GET, POST, PUT, DELETE, OPTIONS (no TRACE/CONNECT).
#
from middleware.hosts import _DEFAULT_ORIGINS, _get_allowed_origins  # noqa: F401

# Keep in step with pyproject.toml and CHANGELOG.md (tests/test_version.py).
APP_VERSION = "2.0.0"

# ---------------------------------------------------------------------------
# Bind address and exposure guard
# ---------------------------------------------------------------------------

_LOOPBACK_BIND_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}


def resolve_bind() -> tuple[str, int]:
    """(host, port) from STORYFORGE_HOST / STORYFORGE_PORT; loopback:7860 by default."""
    host = os.environ.get("STORYFORGE_HOST", "").strip() or "127.0.0.1"
    raw_port = os.environ.get("STORYFORGE_PORT", "").strip() or "7860"
    try:
        port = int(raw_port)
    except ValueError:
        logger.error("STORYFORGE_PORT=%r is not a port number", raw_port)
        raise SystemExit(2) from None
    return host, port


def check_exposure(host: str, token: str | None, in_container: bool) -> None:
    """Refuse to serve a non-loopback address without an access token.

    Binding 0.0.0.0 (or a LAN IP) with no STORYFORGE_ACCESS_TOKEN would hand
    every API route, provider keys included, to the whole network, so that
    exits with code 2. Inside a container the bind is always 0.0.0.0 and the
    real exposure is decided by the published port (compose publishes on
    127.0.0.1), so there it is only a warning.
    """
    if host.strip().lower() in _LOOPBACK_BIND_HOSTS or token:
        return
    if in_container:
        logger.warning(
            "Listening on %s without STORYFORGE_ACCESS_TOKEN. This is safe only "
            "while the container port is published on 127.0.0.1. Set "
            "STORYFORGE_ACCESS_TOKEN before publishing it to a network.",
            host,
        )
        return
    logger.error(
        "Refusing to start: STORYFORGE_HOST=%s is reachable from other machines "
        "and STORYFORGE_ACCESS_TOKEN is not set. Set STORYFORGE_ACCESS_TOKEN, or "
        "bind to 127.0.0.1.",
        host,
    )
    raise SystemExit(2)


def _preflight_check() -> bool:
    """Check that the SQLite database is reachable before starting the server.

    Returns True when the database answers, False otherwise (fatal).
    """
    from api.health_routes import _check_database

    db_result = _check_database()
    if db_result.get("status") == "ok":
        logger.info("Preflight: database OK")
        return True
    logger.error(
        "Preflight: database UNREACHABLE (%s) — cannot start",
        db_result.get("detail", db_result.get("status")),
    )
    return False


def create_app() -> FastAPI:
    """Build the StoryForge FastAPI app: middleware, routes, static mounts."""
    from api import api_router

    # API docs (/docs, /redoc, /openapi.json) only under STORYFORGE_DEBUG=1
    # (scripts/dev.py sets it). Off by default: no public route inventory.
    _docs_enabled = os.environ.get("STORYFORGE_DEBUG", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    main_app = FastAPI(
        title="StoryForge",
        description=(
            "AI-powered story generation platform. "
            "Generate long-form Vietnamese stories with multi-layer pipeline: "
            "story generation, drama simulation, and video storyboarding."
        ),
        version=APP_VERSION,
        docs_url="/docs" if _docs_enabled else None,
        redoc_url="/redoc" if _docs_enabled else None,
        openapi_url="/openapi.json" if _docs_enabled else None,
        openapi_tags=[
            {
                "name": "pipeline",
                "description": "Run and manage story generation pipelines",
            },
            {
                "name": "config",
                "description": "Manage application configuration and model presets",
            },
            {
                "name": "export",
                "description": "Export stories to PDF, EPUB, and other formats",
            },
            {
                "name": "analytics",
                "description": "Usage analytics and story statistics",
            },
            {"name": "metrics", "description": "System performance metrics"},
            {"name": "dashboard", "description": "Dashboard summary data"},
            {
                "name": "session",
                "description": "Optional access token (STORYFORGE_ACCESS_TOKEN) session cookie",
            },
            {"name": "ab", "description": "A/B testing for pipeline variants"},
            {"name": "branch", "description": "Story branching and alternate paths"},
            {"name": "audio", "description": "Text-to-speech and audio generation"},
        ],
    )

    # --- Middleware. Starlette makes the LAST add_middleware() call the
    # outermost layer, so they are added innermost first. Effective order,
    # outer → inner (pinned by tests/test_middleware_order.py):
    #
    #   TrustedHosts → TraceID → CORS → BodySize → SecurityHeaders → CSRF
    #   → Access → RateLimit → Sanitization → Audit → Metrics → GZip
    #
    # - TrustedHosts first: DNS-rebinding requests (bad Host or, behind the
    #   Next proxy, bad X-Forwarded-Host) and writes with a foreign Origin
    #   are rejected before any other layer runs (middleware/hosts.py).
    # - TraceID next: every response past the Host check carries
    #   X-Request-ID (413/403/401/429 rejections included), and every inner
    #   log line can read it.
    # - CORS outside every layer that can reject, so rejections stay
    #   readable by the browser.
    # - BodySize before anything reads or answers on the body.
    # - Access after CSRF/before RateLimit: covers /media and WebSocket
    #   upgrades (API routers use the require_access dependency).
    from middleware.access import AccessMiddleware
    from middleware.audit_middleware import AuditMiddleware
    from middleware.body_limit import BodySizeLimitMiddleware
    from middleware.csrf import CSRFMiddleware
    from middleware.hosts import TrustedHostsMiddleware
    from middleware.metrics_middleware import MetricsMiddleware
    from middleware.rate_limiter import RateLimitMiddleware
    from middleware.sanitization import SanitizationMiddleware
    from middleware.security_headers import SecurityHeadersMiddleware
    from middleware.trace_id import TraceIDMiddleware

    allowed_origins = _get_allowed_origins()
    logger.info(f"CORS allowed origins: {allowed_origins}")

    # GZip (≥1KB responses; HTML/JS/CSS shrink ~5–7×) — innermost.
    main_app.add_middleware(GZipMiddleware, minimum_size=1024, compresslevel=6)
    main_app.add_middleware(MetricsMiddleware)
    main_app.add_middleware(AuditMiddleware)
    # Prompt-injection detection on JSON bodies.
    main_app.add_middleware(SanitizationMiddleware)
    # In-memory, per-IP.
    main_app.add_middleware(RateLimitMiddleware)
    # Optional access token for /media/* and WebSocket upgrades.
    main_app.add_middleware(AccessMiddleware)
    # Double-submit cookie; the docs routes are exempt only when they exist.
    main_app.add_middleware(CSRFMiddleware, exempt_docs=_docs_enabled)
    # CSP, X-Frame-Options, etc.
    main_app.add_middleware(SecurityHeadersMiddleware)
    # 10 MB request bodies; stream-safe (middleware/body_limit.py).
    main_app.add_middleware(BodySizeLimitMiddleware)
    # Explicit origins only, no wildcard.
    main_app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Accept", "X-CSRF-Token"],
    )
    main_app.add_middleware(TraceIDMiddleware)
    main_app.add_middleware(TrustedHostsMiddleware)  # outermost

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
        from api.pipeline_job_registry import start_job_reaper

        start_job_reaper()
        logger.info("Pipeline job reaper started")

        # One-shot: encrypt any plaintext secrets left in config.json.
        try:
            from config.persistence import CONFIG_FILE
            from services.secret_manager import migrate_plaintext_secrets

            if migrate_plaintext_secrets(CONFIG_FILE):
                logger.info("Migrated plaintext secrets in %s to encrypted", CONFIG_FILE)
        except Exception as e:
            logger.warning("Secret migration skipped: %s", e)

    # Graceful shutdown: cancel and await active pipeline tasks
    @main_app.on_event("shutdown")
    async def on_shutdown():
        from api.pipeline_routes import shutdown_pipeline_tasks

        await shutdown_pipeline_tasks(timeout=30)
        from api.pipeline_job_registry import shutdown_job_reaper

        await shutdown_job_reaper()

    # Plugins. Eleven hook call sites sit on the hot path — every score, every
    # genre-rule lookup, every export — and load_all() was never called, so the
    # plugin list was always empty and every one of them was a no-op. Either
    # this runs or the hooks are decoration; it runs. Failure is non-fatal: a
    # broken third-party plugin must not stop the server from booting.
    try:
        from plugins import plugin_manager

        plugin_manager.load_all()
    except Exception:
        logger.exception("Plugin loading failed; continuing without plugins")

    # API routes
    main_app.include_router(api_router)

    # The /api/v1 mirror is gone. It re-mounted nine routers under a second
    # prefix — doubling the route table — purely so a client could pin a
    # version, and no client ever did. Worse, it installed a BaseHTTPMiddleware
    # that ran on *every* request, wrapping each one in an extra task and
    # stream pair, only to set a Deprecation header on the paths nobody called.
    # (/api/v1/eval is unaffected: that prefix belongs to eval_routes itself.)

    # Static files (locales only — UI served by Next.js from frontend/)
    base_dir = os.path.dirname(os.path.abspath(__file__))
    locales_dir = os.path.join(base_dir, "locales")

    if os.path.isdir(locales_dir):
        main_app.mount(
            "/static/locales", GzippedStaticFiles(directory=locales_dir), name="locales"
        )

    # Generated media (per-story layout: output/<story-slug>/images/...,
    # .../images/avatars/..., exports, etc.). The /media mount serves the whole
    # output root so any per-story asset is reachable at /media/<path-rel-to-root>.
    # See services/output_paths.py for the single source of truth.
    from services.output_paths import OUTPUT_ROOT

    media_root = os.path.join(base_dir, OUTPUT_ROOT)
    os.makedirs(media_root, exist_ok=True)
    main_app.mount("/media", StaticFiles(directory=media_root), name="media")

    # Health check — lightweight with a cached DB probe (30s TTL)
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
        from api.health_routes import _check_database

        cfg = ConfigManager()
        llm_ok = bool(cfg.llm.api_key)

        db_status = _cached_check("database", _check_database)
        degraded = db_status.get("status") != "ok"
        status = "degraded" if degraded else "ok"

        return _JSONResponse(
            status_code=503 if degraded else 200,
            content={
                "status": status,
                "version": APP_VERSION,
                "uptime_seconds": round(time.time() - _START_TIME, 1),
                "services": {
                    "llm": llm_ok,
                    "database": db_status.get("status", "unknown"),
                },
            },
        )

    return main_app


def main():
    """Launch the StoryForge backend API."""
    from middleware.access import access_token

    # Before anything else: a non-loopback bind without a token never starts.
    host, port = resolve_bind()
    check_exposure(
        host, access_token(), os.environ.get("STORYFORGE_IN_CONTAINER") == "1"
    )

    # Fail at boot (not inside a request) if the encryption key is unusable.
    from services.secret_manager import ensure_secret_key

    ensure_secret_key()

    main_app = create_app()

    if not _preflight_check():
        logger.error("Preflight checks failed — aborting startup")
        sys.exit(1)

    logger.info(
        "StoryForge backend API at http://%s:%d — UI runs separately at "
        "http://localhost:3001 (cd frontend && npm run dev -- --port 3001)",
        host,
        port,
    )
    uvicorn.run(main_app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
