"""Route tests for api/account_routes.py (previously untested).

UserManager is lazily imported inside the handlers, so it is patched at
its source module. No auth guard — open-source build.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _client() -> TestClient:
    app = FastAPI()
    from api.account_routes import router

    app.include_router(router, prefix="/api")
    return TestClient(app)


def _profile() -> MagicMock:
    profile = MagicMock()
    profile.dict.return_value = {"username": "thanh", "stories": []}
    return profile


def _user_manager(login=None, register=None) -> MagicMock:
    um = MagicMock()
    um.login.return_value = login
    um.register.return_value = register
    return MagicMock(return_value=um), um


class TestLogin:
    def test_login_success_returns_profile(self):
        cls, um = _user_manager(login=_profile())
        with patch("services.user_manager.UserManager", cls):
            resp = _client().post(
                "/api/account/login",
                json={"username": "thanh", "password": "mật-khẩu"},
            )
        assert resp.json() == {
            "ok": True,
            "profile": {"username": "thanh", "stories": []},
        }
        um.login.assert_called_once_with("thanh", "mật-khẩu")

    def test_login_failure_returns_vietnamese_message(self):
        cls, _ = _user_manager(login=None)
        with patch("services.user_manager.UserManager", cls):
            resp = _client().post(
                "/api/account/login", json={"username": "thanh", "password": "sai"}
            )
        assert resp.json() == {"ok": False, "message": "Sai tên hoặc mật khẩu"}


class TestRegister:
    def test_register_success_returns_profile(self):
        cls, um = _user_manager(register=_profile())
        with patch("services.user_manager.UserManager", cls):
            resp = _client().post(
                "/api/account/register",
                json={"username": "thanh", "password": "mật-khẩu"},
            )
        assert resp.json()["ok"] is True
        um.register.assert_called_once_with("thanh", "mật-khẩu")

    def test_register_duplicate_returns_vietnamese_message(self):
        cls, _ = _user_manager(register=None)
        with patch("services.user_manager.UserManager", cls):
            resp = _client().post(
                "/api/account/register",
                json={"username": "thanh", "password": "mật-khẩu"},
            )
        assert resp.json() == {"ok": False, "message": "Tên đăng nhập đã tồn tại"}
