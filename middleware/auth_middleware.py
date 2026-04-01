"""FastAPI dependencies for JWT auth. Use as Depends() on individual routes."""
import logging
from typing import Optional

from fastapi import Request
from fastapi.exceptions import HTTPException

from services.auth import verify_token

logger = logging.getLogger(__name__)


def _extract_token(request: Request) -> Optional[str]:
    """Pull Bearer token from Authorization header. Returns None if absent."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None


def get_current_user(request: Request) -> dict:
    """FastAPI dependency — require valid JWT. Raises 401 if missing/invalid.

    Returns:
        dict with user_id and username
    """
    token = _extract_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Missing authentication token")
    try:
        payload = verify_token(token)
        return {"user_id": payload["sub"], "username": payload["username"]}
    except ValueError as exc:
        logger.debug(f"Auth failed: {exc}")
        raise HTTPException(status_code=401, detail=str(exc))


def get_optional_user(request: Request) -> Optional[dict]:
    """FastAPI dependency — optional auth. Returns None if token absent/invalid."""
    token = _extract_token(request)
    if not token:
        return None
    try:
        payload = verify_token(token)
        return {"user_id": payload["sub"], "username": payload["username"]}
    except ValueError:
        return None
