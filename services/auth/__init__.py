# Backward-compatible re-exports for services.auth.*
from .auth import create_token, verify_token, _b64url_encode, _b64url_decode
from .jwt_manager import (
    generate_key,
    get_current_key,
    get_valid_keys,
    rotate_key,
    sign_token,
)
from .auth_revocation import revoke_token, is_revoked, clear_revocations
from .user_store import UserStore, get_user_store
from .user_manager import UserManager

__all__ = [
    # auth.py
    "create_token",
    "verify_token",
    # jwt_manager.py
    "generate_key",
    "get_current_key",
    "get_valid_keys",
    "rotate_key",
    "sign_token",
    # auth_revocation.py
    "revoke_token",
    "is_revoked",
    "clear_revocations",
    # user_store.py
    "UserStore",
    "get_user_store",
    # user_manager.py
    "UserManager",
]
