# Shim: re-exports from new location for backward compatibility
from services.auth.auth_revocation import revoke_token, is_revoked, clear_revocations

__all__ = ["revoke_token", "is_revoked", "clear_revocations"]
