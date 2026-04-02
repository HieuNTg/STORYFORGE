"""Encrypt/decrypt secrets at rest using Fernet symmetric encryption.

Field-level encryption for sensitive config values:
  Sensitive fields: any key containing 'key', 'secret', 'token', 'password'.
  Encrypted values are stored as strings prefixed with ENC: followed by the
  Fernet ciphertext (base64url). Plaintext values are left as-is when no
  STORYFORGE_SECRET_KEY env var is set (backward-compatible).
"""
import os
import json
import logging
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

STORYFORGE_SECRET_KEY_ENV = "STORYFORGE_SECRET_KEY"
_ENC_PREFIX = "ENC:"

# Field names that contain secrets — matched by substring (case-insensitive)
_SENSITIVE_SUBSTRINGS = ("key", "secret", "token", "password")


def _is_sensitive(field_name: str) -> bool:
    """Return True if field_name looks like a secret."""
    name_lower = field_name.lower()
    return any(s in name_lower for s in _SENSITIVE_SUBSTRINGS)


def _get_fernet():
    """Get Fernet instance from env var. Returns None if key not set."""
    raw_key = os.environ.get(STORYFORGE_SECRET_KEY_ENV, "")
    if not raw_key:
        return None
    # Derive a valid Fernet key from arbitrary string
    key = base64.urlsafe_b64encode(hashlib.sha256(raw_key.encode()).digest())
    return Fernet(key)


def encrypt_value(plaintext: str) -> str:
    """Encrypt a single string value. Returns 'ENC:<ciphertext>' or plaintext if no key."""
    if not plaintext:
        return plaintext
    fernet = _get_fernet()
    if not fernet:
        return plaintext
    ciphertext = fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")
    return f"{_ENC_PREFIX}{ciphertext}"


def decrypt_value(value: str) -> str:
    """Decrypt a single string value. Handles ENC: prefix or plaintext gracefully."""
    if not value or not value.startswith(_ENC_PREFIX):
        return value  # plaintext or empty — pass through
    fernet = _get_fernet()
    if not fernet:
        # No key: strip prefix and return raw ciphertext (won't be useful, but won't crash)
        logger.warning("ENC: value found but STORYFORGE_SECRET_KEY not set — cannot decrypt")
        return ""
    try:
        raw = fernet.decrypt(value[len(_ENC_PREFIX):].encode("ascii"))
        return raw.decode("utf-8")
    except InvalidToken:
        logger.warning("Failed to decrypt value — wrong key or corrupted data")
        return ""


def encrypt_sensitive_fields(data: dict) -> dict:
    """Return a copy of data with sensitive string fields encrypted in-place (recursive)."""
    result = {}
    for k, v in data.items():
        if isinstance(v, dict):
            result[k] = encrypt_sensitive_fields(v)
        elif isinstance(v, str) and _is_sensitive(k) and v and not v.startswith(_ENC_PREFIX):
            result[k] = encrypt_value(v)
        else:
            result[k] = v
    return result


def decrypt_sensitive_fields(data: dict) -> dict:
    """Return a copy of data with ENC: prefixed values decrypted (recursive)."""
    result = {}
    for k, v in data.items():
        if isinstance(v, dict):
            result[k] = decrypt_sensitive_fields(v)
        elif isinstance(v, str) and v.startswith(_ENC_PREFIX):
            result[k] = decrypt_value(v)
        else:
            result[k] = v
    return result


def encrypt_json(data: dict) -> bytes:
    """Encrypt dict as JSON bytes. Returns plaintext JSON if no key set."""
    fernet = _get_fernet()
    json_bytes = json.dumps(data, ensure_ascii=False).encode("utf-8")
    if not fernet:
        return json_bytes
    return fernet.encrypt(json_bytes)


def decrypt_json(data: bytes) -> dict:
    """Decrypt bytes to dict. Falls back to plaintext JSON parse if decryption fails."""
    fernet = _get_fernet()
    if fernet:
        try:
            decrypted = fernet.decrypt(data)
            return json.loads(decrypted)
        except Exception as e:
            logger.warning(f"Decryption failed, trying plaintext: {e}")
    # Try plaintext JSON (backward compatibility)
    return json.loads(data)


def save_encrypted(filepath: str, data: dict):
    """Save encrypted data to file."""
    encrypted = encrypt_json(data)
    with open(filepath, "wb") as f:
        f.write(encrypted)


def load_encrypted(filepath: str) -> dict:
    """Load and decrypt data from file. Returns {} on error."""
    try:
        with open(filepath, "rb") as f:
            return decrypt_json(f.read())
    except (OSError, json.JSONDecodeError, Exception) as e:
        logger.warning(f"Failed to load {filepath}: {e}")
        return {}
