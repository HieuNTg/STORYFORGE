"""Low-level JWT encoding helpers — internal use by jwt_manager only.

Extracted to keep jwt_manager.py under the 200-line project limit.
Do not import this module directly from outside the services package.
"""
import base64
import hashlib
import hmac


def b64url_encode(data: bytes) -> str:
    """URL-safe base64 encode without trailing padding characters.

    Args:
        data: Raw bytes to encode.

    Returns:
        URL-safe base64 string with '=' padding stripped.
    """
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def b64url_decode(s: str) -> bytes:
    """URL-safe base64 decode, re-adding required '=' padding.

    Args:
        s: URL-safe base64 string (with or without padding).

    Returns:
        Decoded bytes.

    Raises:
        Exception: If the string is not valid base64.
    """
    padding = 4 - len(s) % 4
    if padding != 4:
        s += "=" * padding
    return base64.urlsafe_b64decode(s)


def sign_input(signing_input: str, secret: bytes) -> str:
    """Compute HMAC-SHA256 signature and return as URL-safe base64.

    Args:
        signing_input: The string to sign (header.payload).
        secret: 32-byte HMAC secret key.

    Returns:
        URL-safe base64-encoded signature (no padding).
    """
    sig = hmac.new(secret, signing_input.encode(), hashlib.sha256).digest()
    return b64url_encode(sig)
