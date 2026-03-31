"""Browser-based web authentication for free LLM access.

Launches Chrome with CDP (Chrome DevTools Protocol), connects via Playwright,
and captures authentication credentials (cookies, bearer tokens) when user
logs into provider web interfaces (e.g., DeepSeek).
"""

import json
import logging
import os
import platform
import subprocess
import threading
import time
import urllib.error
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

# Credential storage path
AUTH_PROFILES_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "auth_profiles.json",
)

# Chrome CDP port
CDP_PORT = 9222

# Encryption key for auth profiles
_ENCRYPTION_KEY_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
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

# DeepSeek web URLs for interception
DEEPSEEK_DOMAINS = ["chat.deepseek.com", "deepseek.com"]
DEEPSEEK_API_PREFIX = "/api/v0/"


def _find_chrome_path() -> Optional[str]:
    """Find Chrome/Chromium executable path by platform."""
    system = platform.system()
    candidates = []

    if system == "Windows":
        candidates = [
            os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
        ]
    elif system == "Darwin":
        candidates = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
    else:  # Linux
        candidates = ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser"]

    for path in candidates:
        if os.path.isfile(path):
            return path
        # Check in PATH for linux command names
        import shutil
        if shutil.which(path):
            return shutil.which(path)

    return None


class BrowserAuth:
    """Manages browser-based credential capture for web LLM providers.

    Flow:
    1. launch_chrome() — start Chrome with remote debugging
    2. capture_deepseek_credentials() — intercept auth data via Playwright CDP
    3. get_credentials() — retrieve saved credentials for API calls
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
        self._initialized = True
        self._chrome_process: Optional[subprocess.Popen] = None
        self._chrome_path = _find_chrome_path()

    def launch_chrome(self, login_url: str = "https://chat.deepseek.com") -> tuple[bool, str]:
        """Launch Chrome with remote debugging enabled.

        Args:
            login_url: URL to open for user login

        Returns:
            (success, message) tuple
        """
        if not self._chrome_path:
            return False, (
                "Khong tim thay Chrome/Chromium.\n"
                "Cai dat tai: https://www.google.com/chrome/"
            )

        # Check if Chrome CDP already running
        if self._is_cdp_available():
            return True, f"Chrome CDP da san sang tren port {CDP_PORT}"

        try:
            user_data_dir = os.path.join(
                os.path.expanduser("~"), ".storyforge-chrome-debug"
            )
            os.makedirs(user_data_dir, exist_ok=True)

            cmd = [
                self._chrome_path,
                f"--remote-debugging-port={CDP_PORT}",
                f"--user-data-dir={user_data_dir}",
                "--remote-allow-origins=http://127.0.0.1:9222",
                "--no-first-run",
                "--no-default-browser-check",
                login_url,
            ]

            self._chrome_process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            # Wait for CDP to be ready (max 10s)
            for _ in range(20):
                time.sleep(0.5)
                if self._is_cdp_available():
                    logger.info(f"Chrome CDP ready on port {CDP_PORT}")
                    return True, f"Chrome da khoi dong. Hay dang nhap DeepSeek trong trinh duyet."
            return False, "Chrome khoi dong nhung CDP khong phan hoi."

        except (OSError, subprocess.SubprocessError) as e:
            logger.error(f"Chrome launch error: {e}")
            return False, f"Loi khoi dong Chrome: {e}"

    def _is_cdp_available(self) -> bool:
        """Check if Chrome CDP is responding.

        Issue #14: CDP is intentionally over HTTP to localhost only — no SSL needed.
        Guard ensures we never attempt a non-localhost CDP URL.
        """
        try:
            import urllib.request
            # Only allow localhost CDP connections (Issue #14)
            url = f"http://127.0.0.1:{CDP_PORT}/json/version"
            req = urllib.request.urlopen(url, timeout=2)
            return req.status == 200
        except (urllib.error.URLError, OSError, ValueError):
            return False

    def capture_deepseek_credentials(self, timeout: int = 300) -> tuple[bool, str]:
        """Connect to Chrome via CDP and capture DeepSeek auth credentials.

        Intercepts network requests to extract cookies, bearer tokens, and
        user-agent from the user's authenticated browser session.

        Args:
            timeout: Max seconds to wait for auth (default 5 min)

        Returns:
            (success, message) tuple
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return False, (
                "Can cai playwright:\n"
                "  pip install playwright\n"
                "  playwright install chromium"
            )

        if not self._is_cdp_available():
            return False, "Chrome CDP khong hoat dong. Hay chay 'Khoi dong trinh duyet' truoc."

        captured = {
            "cookies": "",
            "bearer": "",
            "user_agent": "",
            "provider": "deepseek-web",
        }

        try:
            with sync_playwright() as pw:
                # CDP intentionally over HTTP to localhost only — no SSL needed (Issue #14)
                cdp_url = f"http://127.0.0.1:{CDP_PORT}"
                browser = pw.chromium.connect_over_cdp(cdp_url)
                context = browser.contexts[0] if browser.contexts else browser.new_context()

                # Find or create DeepSeek tab
                page = None
                for p in context.pages:
                    if any(domain in p.url for domain in DEEPSEEK_DOMAINS):
                        page = p
                        break
                if page is None:
                    page = context.new_page()
                    page.goto("https://chat.deepseek.com")

                page.bring_to_front()
                logger.info("Dang cho nguoi dung dang nhap DeepSeek...")

                # Intercept network requests for bearer token
                def on_request(request):
                    url = request.url
                    if DEEPSEEK_API_PREFIX in url:
                        auth_header = request.headers.get("authorization", "")
                        if auth_header.startswith("Bearer "):
                            captured["bearer"] = auth_header[7:]
                        ua = request.headers.get("user-agent", "")
                        if ua:
                            captured["user_agent"] = ua

                page.on("request", on_request)

                # Poll for valid session (cookies + bearer)
                start_time = time.time()
                while time.time() - start_time < timeout:
                    # Extract cookies
                    cookies = context.cookies(["https://chat.deepseek.com", "https://deepseek.com"])
                    cookie_str = "; ".join(f"{c['name']}={c['value']}" for c in cookies)

                    # Check for session indicators
                    has_session = any(
                        indicator in cookie_str
                        for indicator in ("ds_session", "token", "userToken")
                    )

                    if has_session and captured["bearer"]:
                        captured["cookies"] = cookie_str
                        break

                    # If cookies present but no bearer yet, trigger an API call
                    if has_session and not captured["bearer"]:
                        try:
                            page.evaluate("fetch('/api/v0/users/current')")
                        except Exception as e:
                            logger.debug(f"Page eval failed: {e}")

                    time.sleep(2)

                # Disconnect (don't close — user's browser stays open)
                browser.close()

            if captured["bearer"] and captured["cookies"]:
                self._save_credentials(captured)
                return True, "Dang nhap thanh cong! Credentials da luu."
            elif captured["cookies"]:
                # Save with cookies only (some providers don't need bearer)
                self._save_credentials(captured)
                return True, "Da luu cookies (khong co bearer token)."
            else:
                return False, (
                    f"Het thoi gian ({timeout}s). Hay dang nhap DeepSeek "
                    "trong trinh duyet va thu lai."
                )

        except Exception as e:
            logger.error(f"Credential capture error: {e}")
            return False, f"Loi: {e}"

    def _load_profiles(self) -> dict:
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
                # Normal path: strip marker then decrypt
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
                        self._save_credentials_dict(data)
                        return data
                except (json.JSONDecodeError, UnicodeDecodeError):
                    pass
                return {}
            else:
                # Unrecognized format — refuse to load (prevents downgrade attack)
                logger.error("Auth profile format unrecognized — refusing to load")
                return {}

        # No key yet — load plaintext (first-run before any credential save)
        try:
            return json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}

    def _save_credentials_dict(self, profiles: dict):
        """Save profiles dict encrypted (with SF_ENC: marker) or plaintext fallback.

        Issue #12: Prepend _ENCRYPTED_MARKER so _load_profiles can distinguish
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

    def _save_credentials(self, credentials: dict):
        """Save captured credentials to encrypted auth_profiles.json."""
        os.makedirs(os.path.dirname(AUTH_PROFILES_PATH), exist_ok=True)

        profiles = {}
        if os.path.exists(AUTH_PROFILES_PATH):
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

        # Delegate to _save_credentials_dict which handles encryption + SF_ENC: marker
        self._save_credentials_dict(profiles)
        logger.info(f"Encrypted credentials saved for {provider}")

    def get_credentials(self, provider: str = "deepseek-web") -> Optional[dict]:
        """Load saved credentials for a provider.

        Returns:
            dict with keys: cookies, bearer, user_agent, updated_at
            or None if not found
        """
        try:
            profiles = self._load_profiles()
            return profiles.get(provider)
        except (json.JSONDecodeError, OSError):
            return None

    def is_authenticated(self, provider: str = "deepseek-web") -> bool:
        """Check if valid credentials exist for provider."""
        creds = self.get_credentials(provider)
        return creds is not None and bool(creds.get("cookies"))

    def clear_credentials(self, provider: str = "deepseek-web"):
        """Remove saved credentials for a provider."""
        try:
            profiles = self._load_profiles()
            if provider in profiles:
                del profiles[provider]
                self._save_credentials_dict(profiles)
        except (json.JSONDecodeError, OSError):
            pass

    def clear_sensitive(self):
        """Best-effort cleanup of sensitive data from memory (Issue #13).

        Python does not guarantee memory zeroing, but triggering GC
        reduces the window sensitive data is readable in memory.
        """
        import gc
        gc.collect()

    def stop_chrome(self):
        """Stop the Chrome process if we launched it."""
        if getattr(self, '_chrome_process', None):
            try:
                self._chrome_process.terminate()
                self._chrome_process.wait(timeout=5)
            except (OSError, subprocess.SubprocessError):
                try:
                    self._chrome_process.kill()
                except (OSError, subprocess.SubprocessError):
                    pass
            self._chrome_process = None
