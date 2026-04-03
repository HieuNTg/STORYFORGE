"""Browser auth package — re-export hub. Backward-compatible with services.browser_auth.*

Credential methods read AUTH_PROFILES_PATH/_ENCRYPTION_KEY_PATH via sys.modules[__name__]
so mock.patch('services.browser_auth.AUTH_PROFILES_PATH', ...) is always respected.
"""
import gc
import json
import logging
import os
import sys
import threading
import time
import warnings
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from .browser_manager import BrowserManager, CDP_PORT, _find_chrome_path, is_cdp_available
from .token_extractor import (
    CredentialStore, AUTH_PROFILES_PATH, _ENCRYPTION_KEY_PATH,
    _ENCRYPTED_MARKER, _get_or_create_fernet,
)
from .auth_flow import AuthFlow, DEEPSEEK_DOMAINS, DEEPSEEK_API_PREFIX

logger = logging.getLogger(__name__)


def _this_module():
    """Return services.browser_auth module (respects mock.patch)."""
    return sys.modules[__name__]


class BrowserAuth:
    """Backward-compatible singleton facade over BrowserManager/AuthFlow/CredentialStore.

    Credential methods read path constants via _this_module() so that
    mock.patch('services.browser_auth.AUTH_PROFILES_PATH', ...) is respected.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return
        warnings.warn(
            "BrowserAuth is deprecated and will be removed in v4.0. "
            "Use API key authentication instead (STORYFORGE_API_KEY env var).",
            DeprecationWarning,
            stacklevel=2,
        )
        self._initialized = True
        self._mgr = BrowserManager()
        self._flow_obj = AuthFlow(CredentialStore())
        self._chrome_path = self._mgr._chrome_path

    def _get_mgr(self) -> BrowserManager:
        if not hasattr(self, '_mgr') or self._mgr is None:
            self._mgr = BrowserManager()
        return self._mgr

    def _get_flow(self) -> AuthFlow:
        if not hasattr(self, '_flow_obj') or self._flow_obj is None:
            self._flow_obj = AuthFlow(CredentialStore())
        return self._flow_obj

    # --- Browser lifecycle ---
    def launch_chrome(self, login_url: str = "https://chat.deepseek.com") -> tuple[bool, str]:
        return self._get_mgr().launch_chrome(login_url)

    def _is_cdp_available(self) -> bool:
        return is_cdp_available()

    def stop_chrome(self):
        self._get_mgr().stop_chrome()

    # --- Auth flow ---
    def capture_deepseek_credentials(self, timeout: int = 300) -> tuple[bool, str]:
        return self._get_flow().capture_deepseek_credentials(timeout)

    # --- Credential methods: inline to respect mock.patch on module-level constants ---
    def _make_fernet(self, key_path: str) -> Fernet:
        os.makedirs(os.path.dirname(key_path), exist_ok=True)
        if os.path.exists(key_path):
            with open(key_path, "rb") as f:
                key = f.read()
        else:
            key = Fernet.generate_key()
            with open(key_path, "wb") as f:
                f.write(key)
        return Fernet(key)

    def _load_profiles(self) -> dict:
        mod = _this_module()
        profiles_path, key_path = mod.AUTH_PROFILES_PATH, mod._ENCRYPTION_KEY_PATH
        marker = mod._ENCRYPTED_MARKER
        if not os.path.exists(profiles_path):
            return {}
        with open(profiles_path, "rb") as f:
            raw = f.read()
        if os.path.exists(key_path):
            if raw.startswith(marker):
                try:
                    dec = self._make_fernet(key_path).decrypt(raw[len(marker):])
                    return json.loads(dec.decode("utf-8"))
                except InvalidToken:
                    logger.error("Auth profile decryption failed — possible tampering")
                    return {}
            elif raw.startswith(b"{"):
                logger.warning("Migrating plaintext auth profiles to encrypted format")
                try:
                    data = json.loads(raw.decode("utf-8"))
                    if isinstance(data, dict):
                        self._save_credentials_dict(data)
                        return data
                except (json.JSONDecodeError, UnicodeDecodeError):
                    pass
                return {}
            else:
                logger.error("Auth profile format unrecognized — refusing to load")
                return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}

    def _save_credentials_dict(self, profiles: dict):
        mod = _this_module()
        profiles_path, key_path = mod.AUTH_PROFILES_PATH, mod._ENCRYPTION_KEY_PATH
        marker = mod._ENCRYPTED_MARKER
        os.makedirs(os.path.dirname(profiles_path), exist_ok=True)
        try:
            payload = json.dumps(profiles, ensure_ascii=False).encode("utf-8")
            encrypted = marker + self._make_fernet(key_path).encrypt(payload)
            with open(profiles_path, "wb") as f:
                f.write(encrypted)
        except Exception as e:
            logger.error(f"Encryption failed, credentials NOT saved: {e}")
            raise

    def _save_credentials(self, credentials: dict):
        profiles_path = _this_module().AUTH_PROFILES_PATH
        profiles = {}
        if os.path.exists(profiles_path):
            try:
                profiles = self._load_profiles()
            except (json.JSONDecodeError, OSError):
                pass
        provider = credentials.get("provider", "deepseek-web")
        profiles[provider] = {
            "cookies": credentials["cookies"],
            "bearer": credentials["bearer"],
            "user_agent": credentials["user_agent"],
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        self._save_credentials_dict(profiles)
        logger.info(f"Encrypted credentials saved for {provider}")

    def get_credentials(self, provider: str = "deepseek-web") -> Optional[dict]:
        try:
            return self._load_profiles().get(provider)
        except (json.JSONDecodeError, OSError):
            return None

    def is_authenticated(self, provider: str = "deepseek-web") -> bool:
        creds = self.get_credentials(provider)
        return creds is not None and bool(creds.get("cookies"))

    def clear_credentials(self, provider: str = "deepseek-web"):
        try:
            profiles = self._load_profiles()
            if provider in profiles:
                del profiles[provider]
                self._save_credentials_dict(profiles)
        except (json.JSONDecodeError, OSError):
            pass

    def clear_sensitive(self):
        """Best-effort GC of sensitive memory (Issue #13)."""
        gc.collect()


__all__ = [
    "BrowserAuth", "_find_chrome_path", "AUTH_PROFILES_PATH",
    "_ENCRYPTION_KEY_PATH", "_ENCRYPTED_MARKER", "_get_or_create_fernet",
    "CDP_PORT", "DEEPSEEK_DOMAINS", "DEEPSEEK_API_PREFIX",
    "is_cdp_available", "BrowserManager", "CredentialStore", "AuthFlow",
]
