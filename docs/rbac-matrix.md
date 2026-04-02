# RBAC Permission Matrix — StoryForge

## Roles

| Role | Description |
|---|---|
| **viewer** | Read-only access; can browse published stories |
| **creator** | Create and manage own stories |
| **admin** | Manage users and platform config |
| **superadmin** | Full system access including audit and API keys |

## Permission Matrix

| Permission | Viewer | Creator | Admin | Superadmin |
|---|:---:|:---:|:---:|:---:|
| `read_stories` | Y | Y | Y | Y |
| `create_stories` | N | Y | Y | Y |
| `delete_own_stories` | N | Y | Y | Y |
| `delete_any_stories` | N | N | Y | Y |
| `manage_users` | N | N | Y | Y |
| `access_analytics` | N | N | Y | Y |
| `configure_pipeline` | N | N | Y | Y |
| `manage_api_keys` | N | N | N | Y |
| `view_audit_logs` | N | N | N | Y |

## Implementation Notes

### Middleware-based enforcement

```python
# middleware/rbac_middleware.py
ROLE_PERMISSIONS = {
    "viewer":     {"read_stories"},
    "creator":    {"read_stories", "create_stories", "delete_own_stories"},
    "admin":      {... all except manage_api_keys, view_audit_logs},
    "superadmin": {... all permissions},
}

def require_permission(permission: str):
    """FastAPI dependency — decorator pattern."""
    def _dep(user=Depends(get_current_user)):
        role = user.get("role", "viewer")
        if permission not in ROLE_PERMISSIONS.get(role, set()):
            raise HTTPException(403, f"Permission denied: {permission}")
        return user
    return _dep
```

### Usage on routes

```python
@router.delete("/{story_id}")
def delete_story(story_id: str, user=Depends(require_permission("delete_own_stories"))):
    ...
```

### Role storage

- Stored as `role: str` field on User model in `data/users/`
- Default role on registration: `creator`
- Superadmin bootstrapped via `STORYFORGE_SUPERADMIN_ID` env var

### Escalation path

`viewer` → `creator` (self-service registration)
`creator` → `admin` (superadmin grants)
`admin` → `superadmin` (superadmin grants only)
