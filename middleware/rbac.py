"""Role-Based Access Control (RBAC) — FastAPI dependencies and permission helpers.

Design
------
Four roles (VIEWER < CREATOR < ADMIN < SUPERADMIN) map to a fixed set of
permissions defined in docs/rbac-matrix.md.  The role is stored as a string
on the User record (SQLite ``role`` column / SQLAlchemy ``User.role`` field).

Usage on routes
---------------
Protect individual endpoints with *either* approach:

    # Permission-based (preferred — granular)
    @router.delete("/{story_id}")
    async def delete_story(
        story_id: str,
        user=Depends(require_permission(Permission.DELETE_ANY_STORIES)),
    ):
        ...

    # Role-level (coarser — useful for admin panels)
    @router.get("/admin/users")
    async def list_users(user=Depends(require_role(Role.ADMIN))):
        ...

    # As a route-level dependency (no user object needed in handler body)
    @router.get(
        "/admin/api-keys",
        dependencies=[Depends(require_permission(Permission.MANAGE_API_KEYS))],
    )
    async def list_api_keys():
        ...

Superadmin bootstrap
--------------------
Set ``STORYFORGE_SUPERADMIN_ID`` env var to a user_id that should always be
treated as SUPERADMIN regardless of stored role.
"""
from __future__ import annotations

import logging
import os
from enum import Enum

from fastapi import Request
from fastapi.exceptions import HTTPException

from middleware.auth_middleware import get_current_user

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Role(str, Enum):
    """User roles in ascending privilege order."""
    VIEWER = "viewer"
    CREATOR = "creator"
    ADMIN = "admin"
    SUPERADMIN = "superadmin"


class Permission(str, Enum):
    """Granular permissions.  See docs/rbac-matrix.md for the full matrix."""
    READ_STORIES = "read_stories"
    CREATE_STORIES = "create_stories"
    DELETE_OWN_STORIES = "delete_own_stories"
    DELETE_ANY_STORIES = "delete_any_stories"
    MANAGE_USERS = "manage_users"
    ACCESS_ANALYTICS = "access_analytics"
    CONFIGURE_PIPELINE = "configure_pipeline"
    MANAGE_API_KEYS = "manage_api_keys"
    VIEW_AUDIT_LOGS = "view_audit_logs"


# ---------------------------------------------------------------------------
# Role → Permission mapping  (source of truth; mirrors rbac-matrix.md)
# ---------------------------------------------------------------------------

ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.VIEWER: frozenset({
        Permission.READ_STORIES,
    }),
    Role.CREATOR: frozenset({
        Permission.READ_STORIES,
        Permission.CREATE_STORIES,
        Permission.DELETE_OWN_STORIES,
    }),
    Role.ADMIN: frozenset({
        Permission.READ_STORIES,
        Permission.CREATE_STORIES,
        Permission.DELETE_OWN_STORIES,
        Permission.DELETE_ANY_STORIES,
        Permission.MANAGE_USERS,
        Permission.ACCESS_ANALYTICS,
        Permission.CONFIGURE_PIPELINE,
    }),
    Role.SUPERADMIN: frozenset({
        Permission.READ_STORIES,
        Permission.CREATE_STORIES,
        Permission.DELETE_OWN_STORIES,
        Permission.DELETE_ANY_STORIES,
        Permission.MANAGE_USERS,
        Permission.ACCESS_ANALYTICS,
        Permission.CONFIGURE_PIPELINE,
        Permission.MANAGE_API_KEYS,
        Permission.VIEW_AUDIT_LOGS,
    }),
}

# Ordered list used by require_role() for hierarchy checks.
_ROLE_ORDER: list[Role] = [Role.VIEWER, Role.CREATOR, Role.ADMIN, Role.SUPERADMIN]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _resolve_role(user: dict) -> Role:
    """Return the effective Role for a user dict.

    Handles the superadmin bootstrap env var and falls back to VIEWER if the
    stored role string is unknown.
    """
    superadmin_id = os.environ.get("STORYFORGE_SUPERADMIN_ID", "")
    if superadmin_id and user.get("user_id") == superadmin_id:
        return Role.SUPERADMIN

    raw = user.get("role", "viewer")
    try:
        return Role(raw)
    except ValueError:
        logger.warning("Unknown role %r for user %r — defaulting to VIEWER", raw, user.get("user_id"))
        return Role.VIEWER


def get_current_user_role(request: Request) -> Role:
    """FastAPI dependency — returns the Role of the authenticated user.

    Raises 401 if the token is missing/invalid (via get_current_user).
    """
    user = get_current_user(request)
    return _resolve_role(user)


# ---------------------------------------------------------------------------
# Public dependencies
# ---------------------------------------------------------------------------

def require_permission(permission: Permission):
    """Return a FastAPI dependency that enforces a single Permission.

    The dependency returns the current user dict so handlers can inspect it.

    Raises:
        401 — missing / invalid token (from get_current_user)
        403 — authenticated but insufficient permission
    """
    def _dep(request: Request) -> dict:
        user = get_current_user(request)
        role = _resolve_role(user)
        if permission not in ROLE_PERMISSIONS.get(role, frozenset()):
            logger.info(
                "Permission denied: user=%r role=%r required=%r",
                user.get("user_id"), role, permission,
            )
            raise HTTPException(
                status_code=403,
                detail=f"Permission denied: {permission.value}",
            )
        return user

    # Give the inner function a readable name for FastAPI's OpenAPI schema.
    _dep.__name__ = f"require_{permission.value}"
    return _dep


def require_role(min_role: Role):
    """Return a FastAPI dependency that enforces a minimum role level.

    Roles are ordered: VIEWER < CREATOR < ADMIN < SUPERADMIN.
    A user passes if their role is >= min_role in that ordering.

    Raises:
        401 — missing / invalid token
        403 — role below minimum
    """
    min_index = _ROLE_ORDER.index(min_role)

    def _dep(request: Request) -> dict:
        user = get_current_user(request)
        role = _resolve_role(user)
        if _ROLE_ORDER.index(role) < min_index:
            logger.info(
                "Role check failed: user=%r role=%r required_min=%r",
                user.get("user_id"), role, min_role,
            )
            raise HTTPException(
                status_code=403,
                detail=f"Insufficient role: requires {min_role.value} or higher",
            )
        return user

    _dep.__name__ = f"require_role_{min_role.value}"
    return _dep
