"""Session endpoints for the optional access token.

- ``GET /api/session``    → ``{"required": bool, "valid": bool}`` (exempt)
- ``POST /api/session``   → exchange the token for the ``sf_session`` cookie (exempt)
- ``DELETE /api/session`` → clear the cookie

The POST stays behind the CSRF double-submit check like every other write.
"""

from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from middleware.access import (
    SESSION_COOKIE,
    access_token,
    has_access,
    issue_session,
    require_access,
)

router = APIRouter(
    prefix="/session",
    tags=["session"],
    dependencies=[Depends(require_access)],
)

# Browser session lifetime. The value is derived from the token, so rotating
# STORYFORGE_ACCESS_TOKEN revokes every cookie regardless of this.
_SESSION_MAX_AGE = 30 * 24 * 3600


class SessionRequest(BaseModel):
    token: str


def _is_https(request: Request) -> bool:
    return (
        request.url.scheme == "https"
        or request.headers.get("x-forwarded-proto") == "https"
    )


@router.get("")
async def get_session(request: Request) -> dict:
    """Whether a token is required, and whether this request already has access."""
    token = access_token()
    if token is None:
        return {"required": False, "valid": True}
    return {"required": True, "valid": has_access(request, token)}


@router.post("", status_code=204)
async def open_session(body: SessionRequest, request: Request) -> Response:
    """Set the session cookie when *body.token* matches; 401 otherwise."""
    token = access_token()
    response = Response(status_code=204)
    if token is None:
        return response  # nothing to unlock
    if not hmac.compare_digest(body.token.strip().encode(), token.encode()):
        raise HTTPException(status_code=401, detail={"code": "access_token_invalid"})
    response.set_cookie(
        key=SESSION_COOKIE,
        value=issue_session(token),
        max_age=_SESSION_MAX_AGE,
        httponly=True,
        samesite="strict",
        secure=_is_https(request),
        path="/",
    )
    return response


@router.delete("", status_code=204)
async def close_session(request: Request) -> Response:
    """Clear the session cookie."""
    response = Response(status_code=204)
    response.delete_cookie(
        key=SESSION_COOKIE,
        httponly=True,
        samesite="strict",
        secure=_is_https(request),
        path="/",
    )
    return response
