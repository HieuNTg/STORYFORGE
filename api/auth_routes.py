"""Auth endpoints: register, login, me."""
import logging
import re
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, field_validator

from middleware.auth_middleware import get_current_user
from services.auth import create_token
from services.user_store import get_user_store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]{3,32}$")


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class AuthRequest(BaseModel):
    username: str
    password: str

    @field_validator("username")
    @classmethod
    def username_valid(cls, v: str) -> str:
        if not _USERNAME_RE.match(v):
            raise ValueError("Username must be 3-32 chars, alphanumeric or underscore")
        return v

    @field_validator("password")
    @classmethod
    def password_valid(cls, v: str) -> str:
        if not (8 <= len(v) <= 128):
            raise ValueError("Password must be 8-128 characters")
        return v


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    user_id: str


class UserResponse(BaseModel):
    user_id: str
    username: str
    created_at: Optional[str] = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/register", response_model=TokenResponse, status_code=201)
def register(body: AuthRequest):
    """Create a new account. Returns JWT on success."""
    store = get_user_store()
    try:
        user_id = store.create_user(body.username, body.password)
    except ValueError as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=409, detail=str(exc))
    token = create_token(user_id, body.username)
    logger.info(f"New user registered: {body.username}")
    return TokenResponse(access_token=token, username=body.username, user_id=user_id)


@router.post("/login", response_model=TokenResponse)
def login(body: AuthRequest):
    """Authenticate existing user. Returns JWT on success."""
    store = get_user_store()
    user_id = store.authenticate(body.username, body.password)
    if not user_id:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = create_token(user_id, body.username)
    return TokenResponse(access_token=token, username=body.username, user_id=user_id)


@router.get("/me", response_model=UserResponse)
def me(current_user: dict = Depends(get_current_user)):
    """Return profile of the authenticated user."""
    store = get_user_store()
    user = store.get_user(current_user["user_id"])
    if not user:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="User not found")
    return UserResponse(**user)
