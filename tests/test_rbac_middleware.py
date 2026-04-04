"""Tests for middleware/rbac.py — RBAC roles, permissions, and dependencies."""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi import Request
from fastapi.exceptions import HTTPException

from middleware.rbac import (
    ROLE_PERMISSIONS,
    Role,
    Permission,
    _resolve_role,
    _ROLE_ORDER,
    get_current_user_role,
    require_permission,
    require_role,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_request() -> Request:
    """Return a minimal mock Request."""
    return MagicMock(spec=Request)


# ---------------------------------------------------------------------------
# TestRoleEnum
# ---------------------------------------------------------------------------

class TestRoleEnum:
    def test_viewer_value(self):
        assert Role.VIEWER == "viewer"

    def test_creator_value(self):
        assert Role.CREATOR == "creator"

    def test_admin_value(self):
        assert Role.ADMIN == "admin"

    def test_superadmin_value(self):
        assert Role.SUPERADMIN == "superadmin"

    def test_role_order_ascending(self):
        """VIEWER < CREATOR < ADMIN < SUPERADMIN by index position."""
        assert _ROLE_ORDER.index(Role.VIEWER) < _ROLE_ORDER.index(Role.CREATOR)
        assert _ROLE_ORDER.index(Role.CREATOR) < _ROLE_ORDER.index(Role.ADMIN)
        assert _ROLE_ORDER.index(Role.ADMIN) < _ROLE_ORDER.index(Role.SUPERADMIN)

    def test_role_is_string_enum(self):
        assert isinstance(Role.ADMIN, str)


# ---------------------------------------------------------------------------
# TestPermissionEnum
# ---------------------------------------------------------------------------

class TestPermissionEnum:
    def test_read_stories(self):
        assert Permission.READ_STORIES == "read_stories"

    def test_create_stories(self):
        assert Permission.CREATE_STORIES == "create_stories"

    def test_delete_own_stories(self):
        assert Permission.DELETE_OWN_STORIES == "delete_own_stories"

    def test_delete_any_stories(self):
        assert Permission.DELETE_ANY_STORIES == "delete_any_stories"

    def test_manage_users(self):
        assert Permission.MANAGE_USERS == "manage_users"

    def test_access_analytics(self):
        assert Permission.ACCESS_ANALYTICS == "access_analytics"

    def test_configure_pipeline(self):
        assert Permission.CONFIGURE_PIPELINE == "configure_pipeline"

    def test_manage_api_keys(self):
        assert Permission.MANAGE_API_KEYS == "manage_api_keys"

    def test_view_audit_logs(self):
        assert Permission.VIEW_AUDIT_LOGS == "view_audit_logs"


# ---------------------------------------------------------------------------
# TestRolePermissionsMapping
# ---------------------------------------------------------------------------

class TestRolePermissionsMapping:
    def test_viewer_has_only_read_stories(self):
        assert ROLE_PERMISSIONS[Role.VIEWER] == frozenset({Permission.READ_STORIES})

    def test_creator_has_read_create_delete_own(self):
        expected = frozenset({
            Permission.READ_STORIES,
            Permission.CREATE_STORIES,
            Permission.DELETE_OWN_STORIES,
        })
        assert ROLE_PERMISSIONS[Role.CREATOR] == expected

    def test_admin_has_no_manage_api_keys(self):
        assert Permission.MANAGE_API_KEYS not in ROLE_PERMISSIONS[Role.ADMIN]

    def test_admin_has_no_view_audit_logs(self):
        assert Permission.VIEW_AUDIT_LOGS not in ROLE_PERMISSIONS[Role.ADMIN]

    def test_admin_has_configure_pipeline(self):
        assert Permission.CONFIGURE_PIPELINE in ROLE_PERMISSIONS[Role.ADMIN]

    def test_superadmin_has_all_permissions(self):
        all_perms = frozenset(Permission)
        assert ROLE_PERMISSIONS[Role.SUPERADMIN] == all_perms

    def test_superadmin_has_manage_api_keys(self):
        assert Permission.MANAGE_API_KEYS in ROLE_PERMISSIONS[Role.SUPERADMIN]

    def test_superadmin_has_view_audit_logs(self):
        assert Permission.VIEW_AUDIT_LOGS in ROLE_PERMISSIONS[Role.SUPERADMIN]

    def test_all_four_roles_mapped(self):
        assert set(ROLE_PERMISSIONS.keys()) == {Role.VIEWER, Role.CREATOR, Role.ADMIN, Role.SUPERADMIN}


# ---------------------------------------------------------------------------
# TestResolveRole
# ---------------------------------------------------------------------------

class TestResolveRole:
    def test_known_role_viewer(self):
        assert _resolve_role({"user_id": "u1", "role": "viewer"}) == Role.VIEWER

    def test_known_role_creator(self):
        assert _resolve_role({"user_id": "u1", "role": "creator"}) == Role.CREATOR

    def test_known_role_admin(self):
        assert _resolve_role({"user_id": "u1", "role": "admin"}) == Role.ADMIN

    def test_known_role_superadmin(self):
        assert _resolve_role({"user_id": "u1", "role": "superadmin"}) == Role.SUPERADMIN

    def test_unknown_role_defaults_to_viewer(self):
        role = _resolve_role({"user_id": "u1", "role": "wizard"})
        assert role == Role.VIEWER

    def test_missing_role_key_defaults_to_viewer(self):
        role = _resolve_role({"user_id": "u1"})
        assert role == Role.VIEWER

    def test_superadmin_env_override(self):
        user = {"user_id": "bootstrap-user", "role": "viewer"}
        with patch.dict(os.environ, {"STORYFORGE_SUPERADMIN_ID": "bootstrap-user"}):
            role = _resolve_role(user)
        assert role == Role.SUPERADMIN

    def test_superadmin_env_override_ignores_stored_role(self):
        """Even if stored role is creator, env var makes them superadmin."""
        user = {"user_id": "sa-id", "role": "creator"}
        with patch.dict(os.environ, {"STORYFORGE_SUPERADMIN_ID": "sa-id"}):
            role = _resolve_role(user)
        assert role == Role.SUPERADMIN

    def test_superadmin_env_override_does_not_affect_other_users(self):
        user = {"user_id": "regular-user", "role": "admin"}
        with patch.dict(os.environ, {"STORYFORGE_SUPERADMIN_ID": "someone-else"}):
            role = _resolve_role(user)
        assert role == Role.ADMIN

    def test_empty_superadmin_env_has_no_effect(self):
        """STORYFORGE_SUPERADMIN_ID='' must not grant superadmin to anyone."""
        user = {"user_id": "", "role": "viewer"}
        with patch.dict(os.environ, {"STORYFORGE_SUPERADMIN_ID": ""}):
            role = _resolve_role(user)
        assert role == Role.VIEWER


# ---------------------------------------------------------------------------
# TestGetCurrentUserRole
# ---------------------------------------------------------------------------

class TestGetCurrentUserRole:
    def test_returns_role_from_auth(self):
        request = _make_request()
        with patch("middleware.rbac.get_current_user", return_value={"user_id": "u1", "role": "admin"}):
            role = get_current_user_role(request)
        assert role == Role.ADMIN

    def test_raises_401_when_get_current_user_raises(self):
        request = _make_request()
        with patch(
            "middleware.rbac.get_current_user",
            side_effect=HTTPException(status_code=401, detail="Missing authentication token"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                get_current_user_role(request)
        assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# TestRequirePermission
# ---------------------------------------------------------------------------

class TestRequirePermission:
    def test_allows_when_user_has_permission(self):
        dep = require_permission(Permission.READ_STORIES)
        request = _make_request()
        user = {"user_id": "u1", "role": "viewer"}
        with patch("middleware.rbac.get_current_user", return_value=user):
            result = dep(request)
        assert result == user

    def test_allows_superadmin_for_any_permission(self):
        dep = require_permission(Permission.MANAGE_API_KEYS)
        request = _make_request()
        user = {"user_id": "u1", "role": "superadmin"}
        with patch("middleware.rbac.get_current_user", return_value=user):
            result = dep(request)
        assert result["user_id"] == "u1"

    def test_raises_403_when_permission_missing(self):
        dep = require_permission(Permission.MANAGE_API_KEYS)
        request = _make_request()
        user = {"user_id": "u1", "role": "admin"}
        with patch("middleware.rbac.get_current_user", return_value=user):
            with pytest.raises(HTTPException) as exc_info:
                dep(request)
        assert exc_info.value.status_code == 403
        assert "manage_api_keys" in exc_info.value.detail

    def test_raises_403_for_viewer_on_create(self):
        dep = require_permission(Permission.CREATE_STORIES)
        request = _make_request()
        user = {"user_id": "u1", "role": "viewer"}
        with patch("middleware.rbac.get_current_user", return_value=user):
            with pytest.raises(HTTPException) as exc_info:
                dep(request)
        assert exc_info.value.status_code == 403

    def test_propagates_401_from_get_current_user(self):
        dep = require_permission(Permission.READ_STORIES)
        request = _make_request()
        with patch(
            "middleware.rbac.get_current_user",
            side_effect=HTTPException(status_code=401, detail="Missing authentication token"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                dep(request)
        assert exc_info.value.status_code == 401

    def test_dep_has_readable_name(self):
        dep = require_permission(Permission.DELETE_ANY_STORIES)
        assert dep.__name__ == "require_delete_any_stories"


# ---------------------------------------------------------------------------
# TestRequireRole
# ---------------------------------------------------------------------------

class TestRequireRole:
    def test_allows_exact_role_match(self):
        dep = require_role(Role.ADMIN)
        request = _make_request()
        user = {"user_id": "u1", "role": "admin"}
        with patch("middleware.rbac.get_current_user", return_value=user):
            result = dep(request)
        assert result == user

    def test_allows_higher_role(self):
        dep = require_role(Role.CREATOR)
        request = _make_request()
        user = {"user_id": "u1", "role": "admin"}
        with patch("middleware.rbac.get_current_user", return_value=user):
            result = dep(request)
        assert result["role"] == "admin"

    def test_raises_403_for_lower_role(self):
        dep = require_role(Role.ADMIN)
        request = _make_request()
        user = {"user_id": "u1", "role": "creator"}
        with patch("middleware.rbac.get_current_user", return_value=user):
            with pytest.raises(HTTPException) as exc_info:
                dep(request)
        assert exc_info.value.status_code == 403
        assert "admin" in exc_info.value.detail

    def test_raises_403_for_viewer_when_admin_required(self):
        dep = require_role(Role.ADMIN)
        request = _make_request()
        user = {"user_id": "u1", "role": "viewer"}
        with patch("middleware.rbac.get_current_user", return_value=user):
            with pytest.raises(HTTPException) as exc_info:
                dep(request)
        assert exc_info.value.status_code == 403

    def test_superadmin_passes_any_role_check(self):
        dep = require_role(Role.SUPERADMIN)
        request = _make_request()
        user = {"user_id": "u1", "role": "superadmin"}
        with patch("middleware.rbac.get_current_user", return_value=user):
            result = dep(request)
        assert result["role"] == "superadmin"

    def test_propagates_401_from_get_current_user(self):
        dep = require_role(Role.VIEWER)
        request = _make_request()
        with patch(
            "middleware.rbac.get_current_user",
            side_effect=HTTPException(status_code=401, detail="Missing authentication token"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                dep(request)
        assert exc_info.value.status_code == 401

    def test_dep_has_readable_name(self):
        dep = require_role(Role.ADMIN)
        assert dep.__name__ == "require_role_admin"
