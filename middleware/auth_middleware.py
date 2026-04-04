"""FastAPI dependencies for JWT auth. Use as Depends() on individual routes."""
import logging
from typing import Optional

from fastapi import Request
from fastapi.exceptions import HTTPException

from services.auth import verify_token
from services.user_store import get_user_store

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
        dict with user_id, username, and role (defaults to 'creator' if not stored)
    """
    token = _extract_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Missing authentication token")
    try:
        payload = verify_token(token)
    except ValueError as exc:
        logger.debug(f"Auth failed: {exc}")
        raise HTTPException(status_code=401, detail=str(exc))

    user_id = payload["sub"]
    username = payload["username"]

    # Fetch role from the user store; fall back gracefully so auth never breaks.
    try:
        store = get_user_store()
        user_record = store.get_user(user_id)
        role = user_record.get("role", "creator") if user_record else "creator"
    except Exception:
        logger.warning("Could not fetch role for user %r — defaulting to creator", user_id)
        role = "creator"

    return {"user_id": user_id, "username": username, "role": role}


def get_optional_user(request: Request) -> Optional[dict]:
    """FastAPI dependency — optional auth. Returns None if token absent/invalid."""
    token = _extract_token(request)
    if not token:
        return None
    try:
        payload = verify_token(token)
    except ValueError:
        return None

    user_id = payload["sub"]
    username = payload["username"]

    try:
        store = get_user_store()
        user_record = store.get_user(user_id)
        role = user_record.get("role", "creator") if user_record else "creator"
    except Exception:
        logger.warning("Could not fetch role for user %r — defaulting to creator", user_id)
        role = "creator"

    return {"user_id": user_id, "username": username, "role": role}
