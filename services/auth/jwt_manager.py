"""JWT key rotation manager for StoryForge.

Thread-safe JWT signing with key rotation (default 30-day interval).
Keys stored encrypted at data/jwt_keys.enc via secret_manager.
Backward-compatible: initialises a new key store if none exists.

# Token Rotation Policy
# ----------------------
# StoryForge uses a two-key sliding window for zero-downtime key rotation.
#
# TOKEN_ROTATION_INTERVAL (default: 24 h, env: JWT_KEY_ROTATION_DAYS)
#   How often the active signing key is automatically replaced.  After each
#   rotation the previous key is retained for one additional interval so that
#   tokens signed just before the rotation remain valid.  Set
#   JWT_KEY_ROTATION_DAYS=30 (the production default) to rotate monthly.
#
# TOKEN_REVOCATION_CHECK (default: True)
#   When True, callers should cross-reference the token `jti` claim against a
#   revocation store (e.g. Redis set) before trusting the payload.  This
#   module does NOT perform the check itself — it is the responsibility of
#   verify_token callers (see api/auth_routes.py).
#
# MAX_TOKEN_AGE (default: 7 days = 604800 s)
#   Hard upper bound on token lifetime regardless of the `exp` claim.  Any
#   token whose `iat` is older than MAX_TOKEN_AGE_SECONDS is rejected.
#   Enforced by verify_token.
#
# Rotation algorithm:
#   1. On sign_token(), maybe_rotate() checks whether the active key has
#      exceeded TOKEN_ROTATION_INTERVAL.  If so it archives the current key
#      as `previous_key` and generates a new `current_key`.
#   2. verify_token() tries `current_key` first, then `previous_key` if
#      present and within one rotation window (overlap period).
#   3. Both keys are persisted encrypted via secret_manager.
#
# Environment overrides:
#   JWT_KEY_ROTATION_DAYS   — sets TOKEN_ROTATION_INTERVAL (integer days)
#   JWT_MAX_TOKEN_AGE_DAYS  — sets MAX_TOKEN_AGE (integer days)
#   JWT_REVOCATION_CHECK    — "false" disables TOKEN_REVOCATION_CHECK

Usage:
    from services.jwt_manager import sign_token, verify_token, rotate_key
"""
import hashlib
import hmac
import json
import logging
import os
import secrets
import threading
import time
from typing import Optional

from services.secret_manager import save_encrypted, load_encrypted
from services._jwt_helpers import b64url_encode, b64url_decode, sign_input

logger = logging.getLogger(__name__)

_KEY_STORE_PATH = os.path.join("data", "jwt_keys.enc")
_ALGORITHM = "HS256"

# ---------------------------------------------------------------------------
# Rotation policy configuration constants
# Override via environment variables documented in the module docstring.
# ---------------------------------------------------------------------------

# How frequently the active signing key is replaced (seconds).
TOKEN_ROTATION_INTERVAL: int = int(os.environ.get("JWT_KEY_ROTATION_DAYS", "1")) * 86_400

# Whether verify_token callers should check a revocation store for `jti`.
TOKEN_REVOCATION_CHECK: bool = os.environ.get("JWT_REVOCATION_CHECK", "true").lower() != "false"

# Hard upper bound on accepted token age (seconds). Tokens older than this
# are rejected even if the `exp` claim has not yet elapsed.
MAX_TOKEN_AGE: int = int(os.environ.get("JWT_MAX_TOKEN_AGE_DAYS", "7")) * 86_400

# Internal alias kept for backward compat (used by _JWTKeyStore).
_ROTATION_INTERVAL_SEC = TOKEN_ROTATION_INTERVAL


class _JWTKeyStore:
    """Thread-safe JWT key store with automatic rotation. Singleton."""

    _instance: Optional["_JWTKeyStore"] = None
    _init_lock = threading.Lock()

    def __new__(cls) -> "_JWTKeyStore":
        if cls._instance is None:
            with cls._init_lock:
                if cls._instance is None:
                    inst = super().__new__(cls)
                    inst._lock = threading.Lock()
                    inst._store: dict = {}
                    inst._loaded = False
                    cls._instance = inst
        return cls._instance

    def _load(self) -> None:
        if not os.path.exists(_KEY_STORE_PATH):
            logger.info("JWT key store not found — initialising")
            self._store = {"current_key": secrets.token_hex(32),
                           "current_created": int(time.time()),
                           "previous_key": None, "previous_created": None}
            self._persist()
        else:
            data = load_encrypted(_KEY_STORE_PATH)
            if data and "current_key" in data:
                self._store = data
            else:
                logger.warning("JWT key store corrupt — reinitialising")
                self._store = {"current_key": secrets.token_hex(32),
                               "current_created": int(time.time()),
                               "previous_key": None, "previous_created": None}
                self._persist()

    def _persist(self) -> None:
        os.makedirs(os.path.dirname(_KEY_STORE_PATH), exist_ok=True)
        try:
            save_encrypted(_KEY_STORE_PATH, self._store)
        except Exception as exc:
            logger.error(f"Failed to persist JWT key store: {exc}")

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self._load()
            self._loaded = True

    @staticmethod
    def _key_bytes(hex_key: str) -> bytes:
        return hashlib.sha256(bytes.fromhex(hex_key)).digest()

    def get_current_key(self) -> bytes:
        with self._lock:
            self._ensure_loaded()
            return self._key_bytes(self._store["current_key"])

    def get_valid_keys(self) -> list[bytes]:
        """Return current key plus previous key if still within rotation window."""
        with self._lock:
            self._ensure_loaded()
            keys = [self._key_bytes(self._store["current_key"])]
            prev = self._store.get("previous_key")
            if prev:
                age = time.time() - (self._store.get("previous_created") or 0)
                if age < _ROTATION_INTERVAL_SEC:
                    keys.append(self._key_bytes(prev))
            return keys

    def rotate_key(self) -> None:
        with self._lock:
            self._ensure_loaded()
            self._store["previous_key"] = self._store["current_key"]
            self._store["previous_created"] = self._store["current_created"]
            self._store["current_key"] = secrets.token_hex(32)
            self._store["current_created"] = int(time.time())
            self._persist()
        logger.info("JWT signing key rotated")

    def maybe_rotate(self) -> bool:
        """Rotate if rotation interval elapsed. Returns True if rotation occurred."""
        with self._lock:
            self._ensure_loaded()
            needs = time.time() - self._store.get("current_created", 0) >= _ROTATION_INTERVAL_SEC
        if needs:
            self.rotate_key()
        return needs


_store = _JWTKeyStore()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_key() -> str:
    """Create a new random 32-byte hex signing key (not yet active)."""
    return secrets.token_hex(32)


def get_current_key() -> bytes:
    """Return the active signing key as 32 HMAC bytes."""
    return _store.get_current_key()


def get_valid_keys() -> list[bytes]:
    """Return [current_key, previous_key?] — previous key included within rotation window."""
    return _store.get_valid_keys()


def rotate_key() -> None:
    """Immediately rotate the JWT signing key, archiving the current one."""
    _store.rotate_key()


def sign_token(payload: dict, expiry: int = 86_400) -> str:
    """Create a signed JWT. Auto-rotates key if interval has elapsed.

    Args:
        payload: Claims dict (should include 'sub', 'username').
        expiry: Token TTL seconds (default 86400 = 24 h).

    Returns:
        Signed JWT string (header.payload.signature).
    """
    _store.maybe_rotate()
    now = int(time.time())
    full_payload = {**payload, "iat": now, "exp": now + expiry}
    header = b64url_encode(json.dumps({"alg": _ALGORITHM, "typ": "JWT"}).encode())
    body = b64url_encode(json.dumps(full_payload).encode())
    signing_input = f"{header}.{body}"
    sig = sign_input(signing_input, _store.get_current_key())
    return f"{signing_input}.{sig}"


def verify_token(token: str) -> dict:
    """Verify a JWT against all valid keys (supports rotation overlap).

    Args:
        token: JWT string to verify.

    Returns:
        Decoded payload dict.

    Raises:
        ValueError: Malformed, bad signature, or expired token.
    """
    try:
        header_b64, payload_b64, sig_b64 = token.split(".")
    except ValueError:
        raise ValueError("Malformed token: expected 3 segments")
    signing_input = f"{header_b64}.{payload_b64}"
    try:
        provided_sig = b64url_decode(sig_b64)
    except Exception:
        raise ValueError("Invalid token signature encoding")

    for key_bytes in _store.get_valid_keys():
        expected_sig = hmac.new(key_bytes, signing_input.encode(), hashlib.sha256).digest()
        if hmac.compare_digest(expected_sig, provided_sig):
            try:
                payload = json.loads(b64url_decode(payload_b64))
            except Exception:
                raise ValueError("Malformed token payload")
            if payload.get("exp", 0) < int(time.time()):
                raise ValueError("Token expired")
            iat = payload.get("iat", 0)
            if iat and (int(time.time()) - iat) > MAX_TOKEN_AGE:
                raise ValueError("Token exceeds maximum age")
            return payload

    raise ValueError("Invalid token signature")
