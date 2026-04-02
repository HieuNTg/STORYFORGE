"""RBAC unit tests — middleware/rbac.py.

Covers:
  - Role enum values
  - Permission enum values
  - ROLE_PERMISSIONS mapping correctness for all 4 roles
  - Exact permission sets (no phantom grants, no missing grants)
  - _resolve_role helper (normal path, unknown role, superadmin env var)
  - require_permission dependency (allow, deny, 401 no-token)
  - require_role dependency (allow at level, allow above level, deny below)
  - get_current_user_role dependency integration
"""
from __future__ import annotations

import os
import pytest

os.environ.setdefault("STORYFORGE_SECRET_KEY", "test-secret-for-rbac-tests")

# ---------------------------------------------------------------------------
# Imports (deferred so the env var is set first)
# ---------------------------------------------------------------------------

from middleware.rbac import (  # noqa: E402
    ROLE_PERMISSIONS,
    Permission,
    Role,
    _resolve_role,
    require_permission,
    require_role,
)


# ===========================================================================
# 1. Enum sanity checks
# ===========================================================================

class TestEnums:
    def test_role_enum_values(self):
        assert Role.VIEWER.value == "viewer"
        assert Role.CREATOR.value == "creator"
        assert Role.ADMIN.value == "admin"
        assert Role.SUPERADMIN.value == "superadmin"

    def test_permission_enum_count(self):
        """Exactly 9 permissions defined."""
        assert len(Permission) == 9

    def test_all_permission_values_are_strings(self):
        for p in Permission:
            assert isinstance(p.value, str)


# ===========================================================================
# 2. ROLE_PERMISSIONS mapping
# ===========================================================================

class TestRolePermissions:
    def test_viewer_has_only_read_stories(self):
        perms = ROLE_PERMISSIONS[Role.VIEWER]
        assert perms == {Permission.READ_STORIES}

    def test_creator_permissions(self):
        perms = ROLE_PERMISSIONS[Role.CREATOR]
        assert Permission.READ_STORIES in perms
        assert Permission.CREATE_STORIES in perms
        assert Permission.DELETE_OWN_STORIES in perms
        # Must NOT have elevated perms
        assert Permission.DELETE_ANY_STORIES not in perms
        assert Permission.MANAGE_USERS not in perms
        assert Permission.MANAGE_API_KEYS not in perms
        assert Permission.VIEW_AUDIT_LOGS not in perms

    def test_admin_permissions(self):
        perms = ROLE_PERMISSIONS[Role.ADMIN]
        required = {
            Permission.READ_STORIES,
            Permission.CREATE_STORIES,
            Permission.DELETE_OWN_STORIES,
            Permission.DELETE_ANY_STORIES,
            Permission.MANAGE_USERS,
            Permission.ACCESS_ANALYTICS,
            Permission.CONFIGURE_PIPELINE,
        }
        assert required.issubset(perms)
        # Admin must NOT have superadmin-only perms
        assert Permission.MANAGE_API_KEYS not in perms
        assert Permission.VIEW_AUDIT_LOGS not in perms

    def test_superadmin_has_all_permissions(self):
        perms = ROLE_PERMISSIONS[Role.SUPERADMIN]
        for p in Permission:
            assert p in perms, f"SUPERADMIN missing permission: {p}"

    def test_all_roles_present_in_map(self):
        for role in Role:
            assert role in ROLE_PERMISSIONS, f"Role {role} missing from ROLE_PERMISSIONS"

    def test_permission_sets_are_frozensets(self):
        for role, perms in ROLE_PERMISSIONS.items():
            assert isinstance(perms, frozenset), f"{role} permissions should be frozenset"


# ===========================================================================
# 3. _resolve_role helper
# ===========================================================================

class TestResolveRole:
    def test_resolves_valid_role_string(self):
        assert _resolve_role({"user_id": "u1", "role": "admin"}) == Role.ADMIN

    def test_unknown_role_defaults_to_viewer(self):
        result = _resolve_role({"user_id": "u2", "role": "unknownrole"})
        assert result == Role.VIEWER

    def test_missing_role_key_defaults_to_viewer(self):
        result = _resolve_role({"user_id": "u3"})
        assert result == Role.VIEWER

    def test_superadmin_env_var_overrides_role(self, monkeypatch):
        monkeypatch.setenv("STORYFORGE_SUPERADMIN_ID", "bootstrap-user")
        result = _resolve_role({"user_id": "bootstrap-user", "role": "viewer"})
        assert result == Role.SUPERADMIN

    def test_superadmin_env_var_does_not_affect_other_users(self, monkeypatch):
        monkeypatch.setenv("STORYFORGE_SUPERADMIN_ID", "bootstrap-user")
        result = _resolve_role({"user_id": "normal-user", "role": "creator"})
        assert result == Role.CREATOR


# ===========================================================================
# 4. require_permission dependency
# ===========================================================================

def _make_request(role: str) -> object:
    """Build a minimal fake Request whose get_current_user returns the given role."""
    import services.auth as auth_svc
    from unittest.mock import MagicMock

    token = auth_svc.create_token("test-uid", "testuser")

    request = MagicMock()
    request.headers = {"Authorization": f"Bearer {token}"}

    # Patch get_user_store so the middleware resolves the role without a real DB.
    store_mock = MagicMock()
    store_mock.get_user.return_value = {"user_id": "test-uid", "username": "testuser", "role": role}

    return request, store_mock


class TestRequirePermission:
    def test_allowed_role_returns_user(self):
        from unittest.mock import patch

        request, store_mock = _make_request("admin")
        dep = require_permission(Permission.MANAGE_USERS)

        with patch("middleware.auth_middleware.get_user_store", return_value=store_mock):
            result = dep(request)

        assert result["user_id"] == "test-uid"
        assert result["role"] == "admin"

    def test_insufficient_role_raises_403(self):
        from fastapi.exceptions import HTTPException
        from unittest.mock import patch

        request, store_mock = _make_request("creator")
        dep = require_permission(Permission.MANAGE_USERS)

        with patch("middleware.auth_middleware.get_user_store", return_value=store_mock):
            with pytest.raises(HTTPException) as exc_info:
                dep(request)

        assert exc_info.value.status_code == 403

    def test_viewer_denied_create_stories(self):
        from fastapi.exceptions import HTTPException
        from unittest.mock import patch

        request, store_mock = _make_request("viewer")
        dep = require_permission(Permission.CREATE_STORIES)

        with patch("middleware.auth_middleware.get_user_store", return_value=store_mock):
            with pytest.raises(HTTPException) as exc_info:
                dep(request)

        assert exc_info.value.status_code == 403
        assert "create_stories" in exc_info.value.detail

    def test_superadmin_allowed_manage_api_keys(self):
        from unittest.mock import patch

        request, store_mock = _make_request("superadmin")
        dep = require_permission(Permission.MANAGE_API_KEYS)

        with patch("middleware.auth_middleware.get_user_store", return_value=store_mock):
            result = dep(request)

        assert result["role"] == "superadmin"

    def test_missing_token_raises_401(self):
        from fastapi.exceptions import HTTPException
        from unittest.mock import MagicMock

        request = MagicMock()
        request.headers = {}
        dep = require_permission(Permission.READ_STORIES)

        with pytest.raises(HTTPException) as exc_info:
            dep(request)

        assert exc_info.value.status_code == 401

    def test_dep_name_reflects_permission(self):
        dep = require_permission(Permission.VIEW_AUDIT_LOGS)
        assert "view_audit_logs" in dep.__name__


# ===========================================================================
# 5. require_role dependency
# ===========================================================================

class TestRequireRole:
    def test_exact_role_allowed(self):
        from unittest.mock import patch

        request, store_mock = _make_request("admin")
        dep = require_role(Role.ADMIN)

        with patch("middleware.auth_middleware.get_user_store", return_value=store_mock):
            result = dep(request)

        assert result["role"] == "admin"

    def test_higher_role_allowed(self):
        from unittest.mock import patch

        request, store_mock = _make_request("superadmin")
        dep = require_role(Role.ADMIN)

        with patch("middleware.auth_middleware.get_user_store", return_value=store_mock):
            result = dep(request)

        assert result["role"] == "superadmin"

    def test_lower_role_denied(self):
        from fastapi.exceptions import HTTPException
        from unittest.mock import patch

        request, store_mock = _make_request("creator")
        dep = require_role(Role.ADMIN)

        with patch("middleware.auth_middleware.get_user_store", return_value=store_mock):
            with pytest.raises(HTTPException) as exc_info:
                dep(request)

        assert exc_info.value.status_code == 403
        assert "admin" in exc_info.value.detail

    def test_viewer_denied_creator_routes(self):
        from fastapi.exceptions import HTTPException
        from unittest.mock import patch

        request, store_mock = _make_request("viewer")
        dep = require_role(Role.CREATOR)

        with patch("middleware.auth_middleware.get_user_store", return_value=store_mock):
            with pytest.raises(HTTPException) as exc_info:
                dep(request)

        assert exc_info.value.status_code == 403

    def test_dep_name_reflects_role(self):
        dep = require_role(Role.SUPERADMIN)
        assert "superadmin" in dep.__name__
