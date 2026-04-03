# Shim: re-exports from new location for backward compatibility
from services.auth.user_store import UserStore, get_user_store

__all__ = ["UserStore", "get_user_store"]
