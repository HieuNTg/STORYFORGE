"""RBAC model — roles, permissions, and the role→permission matrix.

Internal module: import these names via ``middleware.rbac``, which re-exports
the full public surface. See docs/rbac-matrix.md for the authoritative matrix.
"""

from __future__ import annotations

from enum import Enum


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
    Role.VIEWER: frozenset(
        {
            Permission.READ_STORIES,
        }
    ),
    Role.CREATOR: frozenset(
        {
            Permission.READ_STORIES,
            Permission.CREATE_STORIES,
            Permission.DELETE_OWN_STORIES,
        }
    ),
    Role.ADMIN: frozenset(
        {
            Permission.READ_STORIES,
            Permission.CREATE_STORIES,
            Permission.DELETE_OWN_STORIES,
            Permission.DELETE_ANY_STORIES,
            Permission.MANAGE_USERS,
            Permission.ACCESS_ANALYTICS,
            Permission.CONFIGURE_PIPELINE,
        }
    ),
    Role.SUPERADMIN: frozenset(
        {
            Permission.READ_STORIES,
            Permission.CREATE_STORIES,
            Permission.DELETE_OWN_STORIES,
            Permission.DELETE_ANY_STORIES,
            Permission.MANAGE_USERS,
            Permission.ACCESS_ANALYTICS,
            Permission.CONFIGURE_PIPELINE,
            Permission.MANAGE_API_KEYS,
            Permission.VIEW_AUDIT_LOGS,
        }
    ),
}

# Ordered list used by require_role() for hierarchy checks.
_ROLE_ORDER: list[Role] = [Role.VIEWER, Role.CREATOR, Role.ADMIN, Role.SUPERADMIN]
