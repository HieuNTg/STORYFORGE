"""Encrypt/decrypt secrets at rest using Fernet symmetric encryption.

Field-level encryption for sensitive config values:
  Sensitive fields: any key containing 'key', 'secret', 'token', 'password'.
  Encrypted values are stored as strings prefixed with ENC: followed by the
  Fernet ciphertext (base64url).

The Fernet key is never something the user has to create. Resolution order:
  1. STORYFORGE_SECRET_KEY env var, if set, not a placeholder, and a valid
     Fernet key (anything else is a hard startup error).
  2. data/.secret_key, if present (must hold a valid Fernet key).
  3. Otherwise a fresh key is generated and written to data/.secret_key.
Values that cannot be decrypted with the current key become empty strings.
"""

import os
import json
import logging
import sys
import tempfile
from pathlib import Path
from typing import NoReturn

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
SECRET_KEY_FILE = DATA_DIR / ".secret_key"

STORYFORGE_SECRET_KEY_ENV = "STORYFORGE_SECRET_KEY"
_ENC_PREFIX = "ENC:"
_decrypt_warned = False

# Placeholder values shipped in .env templates. Encrypting with one of these is
# worse than storing plaintext: anyone with the file can decrypt it, while the
# ENC: prefix makes the values look protected. Treat them as "no key set".
_PLACEHOLDER_KEYS = frozenset(
    {
        "change-me-in-production",
        "change-me",
        "changeme",
        "your-secret-key-here",
        "secret",
    }
)


def is_placeholder_key(raw_key: str) -> bool:
    return raw_key.strip().lower() in _PLACEHOLDER_KEYS

# Field names that contain secrets — matched by substring (case-insensitive)
_SENSITIVE_SUBSTRINGS = ("key", "secret", "token", "password")


def _is_sensitive(field_name: str) -> bool:
    """Return True if field_name looks like a secret."""
    name_lower = field_name.lower()
    return any(s in name_lower for s in _SENSITIVE_SUBSTRINGS)


_KEY_HELP = (
    "Generate one with: python -c \"from cryptography.fernet import Fernet; "
    "print(Fernet.generate_key().decode())\""
)


def _is_valid_fernet_key(raw: bytes) -> bool:
    try:
        Fernet(raw)
    except (ValueError, TypeError):
        return False
    return True


def _die(message: str) -> NoReturn:
    print(f"STORYFORGE: {message}", file=sys.stderr)
    raise SystemExit(2)


def ensure_secret_key() -> bytes:
    """Return the Fernet key, creating data/.secret_key on first use."""
    env_raw = os.environ.get(STORYFORGE_SECRET_KEY_ENV, "").strip()
    if env_raw and not is_placeholder_key(env_raw):
        key = env_raw.encode("ascii", errors="replace")
        if not _is_valid_fernet_key(key):
            _die(
                f"{STORYFORGE_SECRET_KEY_ENV} is not a valid Fernet key "
                f"(32 url-safe base64 bytes). {_KEY_HELP} -- or unset it and "
                f"a key will be generated automatically in {SECRET_KEY_FILE}."
            )
        return key

    path = Path(SECRET_KEY_FILE)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        if _publish_key(path, Fernet.generate_key()):
            logger.info("Generated a new encryption key at %s", path)
    # Always return what is on disk: if another process won the race, its key
    # is the one that counts.
    key = path.read_bytes().strip()
    if not _is_valid_fernet_key(key):
        _die(
            f"{path} exists but does not contain a valid Fernet key. "
            "Refusing to regenerate it, because that would orphan every "
            "encrypted value. Restore the file from a backup, or delete it "
            "to start fresh (stored API keys will have to be re-entered)."
        )
    return key


def _publish_key(path: Path, key: bytes) -> bool:
    """Atomically create `path` holding `key`; never overwrite an existing file.

    Returns True if this call created the file, False if it already existed.
    """
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".secret_key.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(key)
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass  # best effort (Windows)
        try:
            os.link(tmp, path)  # fails if the destination exists
            return True
        except FileExistsError:
            return False
        except (OSError, NotImplementedError, AttributeError):
            pass  # hard links unsupported on this filesystem
        try:
            wfd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            return False
        with os.fdopen(wfd, "wb") as f:
            f.write(key)
        return True
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _get_fernet() -> Fernet:
    """Fernet instance for the resolved key. Never None."""
    return Fernet(ensure_secret_key())


def encrypt_value(plaintext: str) -> str:
    """Encrypt a single string value. Returns 'ENC:<ciphertext>'."""
    if not plaintext:
        return plaintext
    ciphertext = _get_fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")
    return f"{_ENC_PREFIX}{ciphertext}"


def decrypt_value(value: str) -> str:
    """Decrypt a single value. Plaintext passes through; undecryptable -> ''."""
    global _decrypt_warned
    if not value or not value.startswith(_ENC_PREFIX):
        return value  # plaintext or empty — pass through
    try:
        raw = _get_fernet().decrypt(value[len(_ENC_PREFIX) :].encode("ascii"))
        return raw.decode("utf-8")
    except (InvalidToken, UnicodeError):
        if not _decrypt_warned:
            _decrypt_warned = True
            logger.warning(
                "Could not decrypt a stored secret (key changed or data "
                "corrupted) — it was reset to empty; re-enter it in Settings."
            )
        return ""


def encrypt_sensitive_fields(data: dict) -> dict:
    """Return a copy of data with sensitive string fields encrypted recursively."""

    def _encrypt_value(key: str, value):
        sensitive = _is_sensitive(key)
        if isinstance(value, dict):
            return {k: _encrypt_value(k, v) for k, v in value.items()}
        if isinstance(value, list):
            return [_encrypt_value(key, item) for item in value]
        if (
            isinstance(value, str)
            and sensitive
            and value
            and not value.startswith(_ENC_PREFIX)
        ):
            return encrypt_value(value)
        return value

    return {k: _encrypt_value(k, v) for k, v in data.items()}


def decrypt_sensitive_fields(data: dict) -> dict:
    """Return a copy of data with ENC: prefixed values decrypted recursively."""

    def _decrypt_value(value):
        if isinstance(value, dict):
            return {k: _decrypt_value(v) for k, v in value.items()}
        if isinstance(value, list):
            return [_decrypt_value(item) for item in value]
        if isinstance(value, str) and value.startswith(_ENC_PREFIX):
            return decrypt_value(value)
        return value

    return {k: _decrypt_value(v) for k, v in data.items()}


def encrypt_json(data: dict) -> bytes:
    """Encrypt dict as JSON bytes."""
    json_bytes = json.dumps(data, ensure_ascii=False).encode("utf-8")
    return _get_fernet().encrypt(json_bytes)


def decrypt_json(data: bytes) -> dict:
    """Decrypt bytes to dict. Falls back to plaintext JSON parse if decryption fails."""
    try:
        return json.loads(_get_fernet().decrypt(data))
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


def has_plaintext_secrets(data: dict) -> bool:
    """True if any sensitive string field is present and not yet encrypted."""

    def _walk(key: str, value) -> bool:
        if isinstance(value, dict):
            return any(_walk(k, v) for k, v in value.items())
        if isinstance(value, list):
            return any(_walk(key, item) for item in value)
        return (
            isinstance(value, str)
            and _is_sensitive(key)
            and bool(value)
            and not value.startswith(_ENC_PREFIX)
        )

    return any(_walk(k, v) for k, v in data.items())


def migrate_plaintext_secrets(filepath: str) -> bool:
    """Encrypt any plaintext secrets already sitting in `filepath`.

    Hand-edited or pre-encryption files may hold plaintext keys; the next
    ordinary save would encrypt new values but leave the rest readable, so
    this rewrites the file once at startup.

    Returns True if the file was rewritten.
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return False

    if not isinstance(data, dict) or not has_plaintext_secrets(data):
        return False

    tmp = filepath + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(encrypt_sensitive_fields(data), f, ensure_ascii=False, indent=2)
    os.replace(tmp, filepath)
    logger.warning(
        "Encrypted the plaintext secrets stored in %s. They can only be read "
        "back with %s — keep that file backed up.",
        filepath,
        SECRET_KEY_FILE,
    )
    return True
