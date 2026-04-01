"""Credential persistence: encrypted load/save of JWT cookies and bearer tokens."""

import json
import logging
import os
import time
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

# Credential storage path
AUTH_PROFILES_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "auth_profiles.json",
)

# Encryption key for auth profiles
_ENCRYPTION_KEY_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", ".auth_key",
)

# Issue #12: marker prefix to distinguish encrypted files from plaintext
_ENCRYPTED_MARKER = b"SF_ENC:"


def _get_or_create_fernet():
    """Get or create Fernet encryption key for auth profiles.

    Intentionally independent from services/secret_manager.py.
    secret_manager.py encrypts config secrets at rest using STORYFORGE_SECRET_KEY
    env var (suitable for server/Docker deployments).
    This function manages a local machine key in data/.auth_key for browser
    session credentials — a separate trust boundary (local-only, no env var needed).
    """
    os.makedirs(os.path.dirname(_ENCRYPTION_KEY_PATH), exist_ok=True)
    if os.path.exists(_ENCRYPTION_KEY_PATH):
        with open(_ENCRYPTION_KEY_PATH, "rb") as f:
            key = f.read()
    else:
        key = Fernet.generate_key()
        with open(_ENCRYPTION_KEY_PATH, "wb") as f:
            f.write(key)
    return Fernet(key)


class CredentialStore:
    """Handles encrypted load/save of auth profiles to disk."""

    def load_profiles(self) -> dict:
        """Load and decrypt auth profiles.

        Issue #12: When encryption key exists, only accept files with the SF_ENC:
        prefix. Legacy plaintext is auto-migrated. Unrecognized formats are refused
        to prevent downgrade attacks.
        """
        if not os.path.exists(AUTH_PROFILES_PATH):
            return {}

        with open(AUTH_PROFILES_PATH, "rb") as f:
            raw = f.read()

        key_exists = os.path.exists(_ENCRYPTION_KEY_PATH)

        if key_exists:
            if raw.startswith(_ENCRYPTED_MARKER):
                try:
                    fernet = _get_or_create_fernet()
                    decrypted = fernet.decrypt(raw[len(_ENCRYPTED_MARKER):])
                    return json.loads(decrypted.decode("utf-8"))
                except InvalidToken:
                    logger.error("Auth profile decryption failed — possible tampering")
                    return {}
            elif raw.startswith(b"{"):
                # Legacy plaintext detected while key is present — migrate it
                logger.warning("Migrating plaintext auth profiles to encrypted format")
                try:
                    data = json.loads(raw.decode("utf-8"))
                    if isinstance(data, dict):
                        self.save_profiles_dict(data)
                        return data
                except (json.JSONDecodeError, UnicodeDecodeError):
                    pass
                return {}
            else:
                logger.error("Auth profile format unrecognized — refusing to load")
                return {}

        # No key yet — load plaintext (first-run before any credential save)
        try:
            return json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}

    def save_profiles_dict(self, profiles: dict):
        """Save profiles dict encrypted (with SF_ENC: marker) or plaintext fallback.

        Issue #12: Prepend _ENCRYPTED_MARKER so load_profiles can distinguish
        encrypted files from legacy plaintext and refuse downgrades.
        """
        os.makedirs(os.path.dirname(AUTH_PROFILES_PATH), exist_ok=True)
        try:
            fernet = _get_or_create_fernet()
            payload = json.dumps(profiles, ensure_ascii=False).encode("utf-8")
            encrypted = _ENCRYPTED_MARKER + fernet.encrypt(payload)
            with open(AUTH_PROFILES_PATH, "wb") as f:
                f.write(encrypted)
        except Exception as e:
            logger.error(f"Encryption failed, credentials NOT saved: {e}")
            raise

    def save_credentials(self, credentials: dict):
        """Save captured credentials to encrypted auth_profiles.json."""
        os.makedirs(os.path.dirname(AUTH_PROFILES_PATH), exist_ok=True)

        profiles = {}
        if os.path.exists(AUTH_PROFILES_PATH):
            try:
                profiles = self.load_profiles()
            except (json.JSONDecodeError, OSError):
                pass

        provider = credentials.get("provider", "deepseek-web")
        profiles[provider] = {
            "cookies": credentials["cookies"],
            "bearer": credentials["bearer"],
            "user_agent": credentials["user_agent"],
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }

        self.save_profiles_dict(profiles)
        logger.info(f"Encrypted credentials saved for {provider}")

    def get_credentials(self, provider: str = "deepseek-web") -> Optional[dict]:
        """Load saved credentials for a provider."""
        try:
            profiles = self.load_profiles()
            return profiles.get(provider)
        except (json.JSONDecodeError, OSError):
            return None

    def clear_credentials(self, provider: str = "deepseek-web"):
        """Remove saved credentials for a provider."""
        try:
            profiles = self.load_profiles()
            if provider in profiles:
                del profiles[provider]
                self.save_profiles_dict(profiles)
        except (json.JSONDecodeError, OSError):
            pass
