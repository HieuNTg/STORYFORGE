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
    try:
        from services.user_manager import UserManager
        um = UserManager()
        profile = um.login(body.username, body.password)
        if profile:
            return {"ok": True, "profile": profile.dict()}
        return {"ok": False, "message": "Sai tên hoặc mật khẩu"}
    except Exception as e:
        return {"ok": False, "message": str(e)}


@router.post("/register")
def register(body: AuthRequest):
    """Register a new account."""
    try:
        from services.user_manager import UserManager
        um = UserManager()
        profile = um.register(body.username, body.password)
        if profile:
            return {"ok": True, "profile": profile.dict()}
        return {"ok": False, "message": "Tên đăng nhập đã tồn tại"}
    except Exception as e:
        return {"ok": False, "message": str(e)}
