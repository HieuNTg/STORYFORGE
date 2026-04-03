# Shim: re-exports from new location for backward compatibility
from services.auth.user_manager import UserManager

__all__ = ["UserManager"]
