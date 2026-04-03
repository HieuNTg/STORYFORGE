"""JWT auth: RS256 primary, HS256 fallback for legacy tokens.

Keys auto-generated in STORYFORGE_JWT_KEY_DIR (default: data/jwt_keys/).
Rotation: set STORYFORGE_JWT_KEY_ID to a new value; old public keys stay
for verification. Revocation via jti claim + services.auth_revocation.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from pathlib import Path
from typing import Optional

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from services.auth.auth_revocation import is_revoked

logger = logging.getLogger(__name__)

# JWT token TTL — configurable via env var, defaults to 24 hours.
# Valid range: 300s (5 min) to 604800s (7 days). Out-of-range values are
# clamped with a warning so misconfiguration doesn't silently break auth.
_TOKEN_TTL_MIN = 300       # 5 minutes
_TOKEN_TTL_MAX = 604_800   # 7 days
_TOKEN_TTL = int(os.environ.get("STORYFORGE_JWT_TTL_SECONDS", "86400"))
if _TOKEN_TTL < _TOKEN_TTL_MIN:
    logger.warning(
        "STORYFORGE_JWT_TTL_SECONDS=%d is below minimum %d — clamping to %d",
        _TOKEN_TTL, _TOKEN_TTL_MIN, _TOKEN_TTL_MIN,
    )
    _TOKEN_TTL = _TOKEN_TTL_MIN
elif _TOKEN_TTL > _TOKEN_TTL_MAX:
    logger.warning(
        "STORYFORGE_JWT_TTL_SECONDS=%d exceeds maximum %d — clamping to %d",
        _TOKEN_TTL, _TOKEN_TTL_MAX, _TOKEN_TTL_MAX,
    )
    _TOKEN_TTL = _TOKEN_TTL_MAX

_MAX_OLD_KEYS = 3  # Max previous rotation keys to load for verification

# Cached RSA keys — avoids disk I/O on every token operation
_cached_kid: Optional[str] = None
_cached_priv: Optional[rsa.RSAPrivateKey] = None
_cached_pubs: Optional[list[rsa.RSAPublicKey]] = None


# Base64url helpers — public because tests import them directly
def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

def _b64url_decode(s: str) -> bytes:
    p = 4 - len(s) % 4
    if p != 4:
        s += "=" * p
    return base64.urlsafe_b64decode(s)


# HS256 fallback — required by tests and legacy token verification
def _get_secret() -> bytes:
    """Derive HS256 signing key from STORYFORGE_SECRET_KEY.

    Raises:
        RuntimeError: If STORYFORGE_SECRET_KEY is not set.
    """
    raw = os.environ.get("STORYFORGE_SECRET_KEY", "")
    if not raw:
        raise RuntimeError("STORYFORGE_SECRET_KEY env var is required")
    return hashlib.sha256(raw.encode()).digest()


# RSA key management
def _key_dir() -> Path:
    base = os.environ.get("STORYFORGE_JWT_KEY_DIR", "data/jwt_keys")
    kid = os.environ.get("STORYFORGE_JWT_KEY_ID", "default")
    return Path(base) / kid


def _load_or_generate_rsa_keys() -> tuple[rsa.RSAPrivateKey, list[rsa.RSAPublicKey]]:
    """Load RSA keys from disk, auto-generating 4096-bit pair on first run.

    Keys are cached in module-level variables and only reloaded when the
    active key ID changes (via STORYFORGE_JWT_KEY_ID env var).

    Note: In-memory revocation does not survive server restarts.
    Deploy with REDIS_URL for persistent revocation in production.
    """
    global _cached_kid, _cached_priv, _cached_pubs

    kid = os.environ.get("STORYFORGE_JWT_KEY_ID", "default")
    if _cached_priv is not None and _cached_kid == kid:
        return _cached_priv, _cached_pubs  # type: ignore[return-value]

    key_dir = _key_dir()
    key_dir.mkdir(parents=True, exist_ok=True)
    priv_path, pub_path = key_dir / "private.pem", key_dir / "public.pem"

    if not priv_path.exists():
        logger.info(f"Generating RSA-4096 key pair in {key_dir}")
        priv_key = rsa.generate_private_key(65537, 4096, default_backend())
        priv_pem = priv_key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption())
        priv_path.write_bytes(priv_pem)
        try:
            priv_path.chmod(0o600)
        except OSError:
            pass  # Windows doesn't support POSIX permissions
        pub_path.write_bytes(priv_key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    else:
        priv_key = serialization.load_pem_private_key(
            priv_path.read_bytes(), password=None, backend=default_backend())

    # Current public key + up to _MAX_OLD_KEYS previous rotation keys
    pub_keys: list[rsa.RSAPublicKey] = [
        serialization.load_pem_public_key(pub_path.read_bytes(), backend=default_backend())
    ]
    old_count = 0
    for sibling in sorted(key_dir.parent.iterdir(), reverse=True):
        if old_count >= _MAX_OLD_KEYS:
            break
        if sibling.is_dir() and sibling.name != key_dir.name:
            old_pub = sibling / "public.pem"
            if old_pub.exists():
                try:
                    pub_keys.append(serialization.load_pem_public_key(
                        old_pub.read_bytes(), backend=default_backend()))
                    old_count += 1
                except Exception as exc:
                    logger.warning(f"Skipping old public key {old_pub}: {exc}")

    _cached_kid, _cached_priv, _cached_pubs = kid, priv_key, pub_keys
    return priv_key, pub_keys


# Public API
def create_token(user_id: str, username: str) -> str:
    """Create a signed RS256 JWT with 24h expiry and jti revocation claim."""
    kid = os.environ.get("STORYFORGE_JWT_KEY_ID", "default")
    priv_key, _ = _load_or_generate_rsa_keys()
    now = int(time.time())
    header = _b64url_encode(json.dumps({"alg": "RS256", "typ": "JWT", "kid": kid}).encode())
    payload = _b64url_encode(json.dumps({
        "sub": user_id, "username": username, "jti": secrets.token_hex(16),
        "iat": now, "exp": now + _TOKEN_TTL,
    }).encode())
    signing_input = f"{header}.{payload}"
    sig = priv_key.sign(signing_input.encode(), padding.PKCS1v15(), hashes.SHA256())
    return f"{signing_input}.{_b64url_encode(sig)}"


def verify_token(token: str) -> dict:
    """Verify a JWT. RS256 primary; HS256 fallback for pre-migration tokens.

    Raises:
        ValueError: Malformed, invalid signature, expired, or revoked token.
    """
    try:
        header_b64, payload_b64, sig_b64 = token.split(".")
    except ValueError:
        raise ValueError("Malformed token")
    try:
        header = json.loads(_b64url_decode(header_b64))
    except Exception:
        raise ValueError("Malformed token header")

    if header.get("alg") == "RS256":
        return _verify_rs256(header_b64, payload_b64, sig_b64)
    return _verify_hs256(header_b64, payload_b64, sig_b64)


def _verify_rs256(header_b64: str, payload_b64: str, sig_b64: str) -> dict:
    signing_input = f"{header_b64}.{payload_b64}"
    try:
        sig_bytes = _b64url_decode(sig_b64)
    except Exception:
        raise ValueError("Invalid token signature encoding")
    _, pub_keys = _load_or_generate_rsa_keys()
    last_exc: Optional[Exception] = None
    for pub_key in pub_keys:
        try:
            pub_key.verify(sig_bytes, signing_input.encode(), padding.PKCS1v15(), hashes.SHA256())
            return _decode_and_validate(payload_b64)
        except Exception as exc:
            last_exc = exc
    raise ValueError(f"Invalid token signature: {last_exc}")


def _verify_hs256(header_b64: str, payload_b64: str, sig_b64: str) -> dict:
    signing_input = f"{header_b64}.{payload_b64}"
    expected = hmac.new(_get_secret(), signing_input.encode(), hashlib.sha256).digest()
    try:
        provided = _b64url_decode(sig_b64)
    except Exception:
        raise ValueError("Invalid token signature encoding")
    if not hmac.compare_digest(expected, provided):
        raise ValueError("Invalid token signature")
    return _decode_and_validate(payload_b64)


def _decode_and_validate(payload_b64: str) -> dict:
    try:
        payload = json.loads(_b64url_decode(payload_b64))
    except Exception:
        raise ValueError("Malformed token payload")
    if payload.get("exp", 0) < int(time.time()):
        raise ValueError("Token expired")
    jti = payload.get("jti")
    if jti and is_revoked(jti):
        raise ValueError("Token has been revoked")
    return payload
