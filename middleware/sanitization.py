"""Input sanitization middleware — intercepts POST/PUT requests and checks for injection.

Reads the request body JSON, runs string fields through the input sanitizer,
and returns 422 if a prompt injection pattern is detected.

Skips:
  - Non-JSON content types (file uploads, form data)
  - Health check and docs endpoints
  - GET/DELETE/HEAD/OPTIONS requests
"""

import json
import logging

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from services.security.input_sanitizer import InjectionBlockedError, sanitize_input

logger = logging.getLogger(__name__)

_MUTATING_METHODS = {"POST", "PUT", "PATCH"}

_SKIP_PREFIXES = (
    "/api/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/static/",
    "/favicon",
)


def _extract_strings(obj, depth: int = 0) -> list[str]:
    """Recursively collect all string values from a JSON-decoded object."""
    if depth > 10:
        return []
    if isinstance(obj, str):
        return [obj]
    if isinstance(obj, dict):
        result = []
        for v in obj.values():
            result.extend(_extract_strings(v, depth + 1))
        return result
    if isinstance(obj, list):
        result = []
        for item in obj:
            result.extend(_extract_strings(item, depth + 1))
        return result
    return []


class SanitizationMiddleware(BaseHTTPMiddleware):
    """Sanitize all POST/PUT/PATCH request bodies for prompt injection."""

    async def dispatch(self, request: Request, call_next):
        if request.method not in _MUTATING_METHODS:
            return await call_next(request)

        path = request.url.path
        if any(path.startswith(p) for p in _SKIP_PREFIXES):
            return await call_next(request)

        content_type = request.headers.get("content-type", "")
        if "application/json" not in content_type:
            return await call_next(request)

        try:
            body_bytes = await request.body()
            if not body_bytes:
                return await call_next(request)

            try:
                payload = json.loads(body_bytes)
            except (json.JSONDecodeError, ValueError):
                # Malformed JSON — let the route handler return a proper error
                return await call_next(request)

            strings = _extract_strings(payload)
            for text in strings:
                try:
                    sanitize_input(text)  # raises InjectionBlockedError if blocked
                except InjectionBlockedError:
                    # Log the matched string (truncated) before re-raising
                    preview = text[:120].replace("\n", " ")
                    logger.warning("Sanitization blocked string — path=%s preview=%r", path, preview)
                    raise

        except InjectionBlockedError as exc:
            logger.warning("Sanitization middleware blocked request: %s — path=%s", exc, path)
            return JSONResponse(
                status_code=422,
                content={"detail": str(exc)},
            )
        except Exception:
            logger.exception("Unexpected error in sanitization middleware — passing through")

        return await call_next(request)
