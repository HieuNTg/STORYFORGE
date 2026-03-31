"""Encrypt/decrypt secrets at rest using Fernet symmetric encryption."""
import os
import json
import logging
import base64
import hashlib

from cryptography.fernet import Fernet

STORYFORGE_SECRET_KEY_ENV = "STORYFORGE_SECRET_KEY"


def _get_fernet():
    """Get Fernet instance from env var. Returns None if key not set."""
    raw_key = os.environ.get(STORYFORGE_SECRET_KEY_ENV, "")
    if not raw_key:
        return None
    # Derive a valid Fernet key from arbitrary string
    key = base64.urlsafe_b64encode(hashlib.sha256(raw_key.encode()).digest())
    return Fernet(key)


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
            logging.getLogger(__name__).warning(f"Decryption failed, trying plaintext: {e}")
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
        logging.getLogger(__name__).warning(f"Failed to load {filepath}: {e}")
        return {}
