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
from typing import Optional

logger = logging.getLogger(__name__)

# Credential storage path
AUTH_PROFILES_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "auth_profiles.json",
)

# Chrome CDP port
CDP_PORT = 9222

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

        except Exception as e:
            logger.error(f"Chrome launch error: {e}")
            return False, f"Loi khoi dong Chrome: {e}"

    def _is_cdp_available(self) -> bool:
        """Check if Chrome CDP is responding."""
        try:
            import urllib.request
            url = f"http://127.0.0.1:{CDP_PORT}/json/version"
            req = urllib.request.urlopen(url, timeout=2)
            return req.status == 200
        except Exception:
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
                # Connect to existing Chrome via CDP
                browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}")
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
                        except Exception:
                            pass

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

    def _save_credentials(self, credentials: dict):
        """Save captured credentials to auth_profiles.json."""
        os.makedirs(os.path.dirname(AUTH_PROFILES_PATH), exist_ok=True)

        profiles = {}
        if os.path.exists(AUTH_PROFILES_PATH):
            try:
                with open(AUTH_PROFILES_PATH, "r", encoding="utf-8") as f:
                    profiles = json.load(f)
            except Exception:
                pass

        provider = credentials.get("provider", "deepseek-web")
        profiles[provider] = {
            "cookies": credentials["cookies"],
            "bearer": credentials["bearer"],
            "user_agent": credentials["user_agent"],
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }

        with open(AUTH_PROFILES_PATH, "w", encoding="utf-8") as f:
            json.dump(profiles, f, ensure_ascii=False, indent=2)
        logger.info(f"Credentials saved for {provider}")

    def get_credentials(self, provider: str = "deepseek-web") -> Optional[dict]:
        """Load saved credentials for a provider.

        Returns:
            dict with keys: cookies, bearer, user_agent, updated_at
            or None if not found
        """
        if not os.path.exists(AUTH_PROFILES_PATH):
            return None
        try:
            with open(AUTH_PROFILES_PATH, "r", encoding="utf-8") as f:
                profiles = json.load(f)
            return profiles.get(provider)
        except Exception:
            return None

    def is_authenticated(self, provider: str = "deepseek-web") -> bool:
        """Check if valid credentials exist for provider."""
        creds = self.get_credentials(provider)
        return creds is not None and bool(creds.get("cookies"))

    def clear_credentials(self, provider: str = "deepseek-web"):
        """Remove saved credentials for a provider."""
        if not os.path.exists(AUTH_PROFILES_PATH):
            return
        try:
            with open(AUTH_PROFILES_PATH, "r", encoding="utf-8") as f:
                profiles = json.load(f)
            if provider in profiles:
                del profiles[provider]
                with open(AUTH_PROFILES_PATH, "w", encoding="utf-8") as f:
                    json.dump(profiles, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def stop_chrome(self):
        """Stop the Chrome process if we launched it."""
        if self._chrome_process:
            try:
                self._chrome_process.terminate()
                self._chrome_process.wait(timeout=5)
            except Exception:
                try:
                    self._chrome_process.kill()
                except Exception:
                    pass
            self._chrome_process = None
