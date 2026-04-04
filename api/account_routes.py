"""Account API routes — login, register, story library."""

import logging
from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/account", tags=["account"])


class AuthRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(body: AuthRequest):
    """Login and return user profile."""
    from services.user_manager import UserManager
    um = UserManager()
    profile = um.login(body.username, body.password)
    if profile:
        return {"ok": True, "profile": profile.dict()}
    return {"ok": False, "message": "Sai tên hoặc mật khẩu"}


@router.post("/register")
def register(body: AuthRequest):
    """Register a new account."""
    from services.user_manager import UserManager
    um = UserManager()
    profile = um.register(body.username, body.password)
    if profile:
        return {"ok": True, "profile": profile.dict()}
    return {"ok": False, "message": "Tên đăng nhập đã tồn tại"}
