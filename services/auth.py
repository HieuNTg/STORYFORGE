"""Minimal JWT implementation using stdlib hmac + base64 + json. No external deps."""
import base64
import hashlib
import hmac
import json
import logging
import os
import time

logger = logging.getLogger(__name__)

_ALGORITHM = "HS256"
_TOKEN_TTL = 86_400  # 24 hours


def _get_secret() -> bytes:
    """Derive signing secret from STORYFORGE_SECRET_KEY env var."""
    raw = os.environ.get("STORYFORGE_SECRET_KEY", "")
    if not raw:
        raise RuntimeError("STORYFORGE_SECRET_KEY env var is required")
    return hashlib.sha256(raw.encode()).digest()


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    padding = 4 - len(s) % 4
    if padding != 4:
        s += "=" * padding
    return base64.urlsafe_b64decode(s)


def create_token(user_id: str, username: str) -> str:
    """Create a signed JWT (HS256) with 24h expiry.

    Args:
        user_id: UUID string
        username: display name

    Returns:
        JWT token string
    """
    header = _b64url_encode(json.dumps({"alg": _ALGORITHM, "typ": "JWT"}).encode())
    payload = _b64url_encode(
        json.dumps({
            "sub": user_id,
            "username": username,
            "iat": int(time.time()),
            "exp": int(time.time()) + _TOKEN_TTL,
        }).encode()
    )
    signing_input = f"{header}.{payload}"
    sig = hmac.new(_get_secret(), signing_input.encode(), hashlib.sha256).digest()
    return f"{signing_input}.{_b64url_encode(sig)}"


def verify_token(token: str) -> dict:
    """Verify JWT and return payload dict.

    Args:
        token: JWT string

    Returns:
        Payload dict with sub, username, iat, exp

    Raises:
        ValueError: invalid signature, expired, or malformed token
    """
    try:
        header_b64, payload_b64, sig_b64 = token.split(".")
    except ValueError:
        raise ValueError("Malformed token")

    signing_input = f"{header_b64}.{payload_b64}"
    expected_sig = hmac.new(_get_secret(), signing_input.encode(), hashlib.sha256).digest()

    try:
        provided_sig = _b64url_decode(sig_b64)
    except Exception:
        raise ValueError("Invalid token signature encoding")

    if not hmac.compare_digest(expected_sig, provided_sig):
        raise ValueError("Invalid token signature")

    try:
        payload = json.loads(_b64url_decode(payload_b64))
    except Exception:
        raise ValueError("Malformed token payload")

    if payload.get("exp", 0) < int(time.time()):
        raise ValueError("Token expired")

    return payload
