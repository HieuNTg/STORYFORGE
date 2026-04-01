"""DeepSeek login flow: Playwright CDP interception, session detection."""

import logging
import time
from typing import TYPE_CHECKING

from .browser_manager import is_cdp_available, CDP_PORT
from .token_extractor import CredentialStore

logger = logging.getLogger(__name__)

# DeepSeek web URLs for interception
DEEPSEEK_DOMAINS = ["chat.deepseek.com", "deepseek.com"]
DEEPSEEK_API_PREFIX = "/api/v0/"


class AuthFlow:
    """Handles Playwright-based credential capture for DeepSeek web."""

    def __init__(self, credential_store: CredentialStore):
        self._store = credential_store

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

        if not is_cdp_available():
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
                    cookies = context.cookies(["https://chat.deepseek.com", "https://deepseek.com"])
                    cookie_str = "; ".join(f"{c['name']}={c['value']}" for c in cookies)

                    has_session = any(
                        indicator in cookie_str
                        for indicator in ("ds_session", "token", "userToken")
                    )

                    if has_session and captured["bearer"]:
                        captured["cookies"] = cookie_str
                        break

                    if has_session and not captured["bearer"]:
                        try:
                            page.evaluate("fetch('/api/v0/users/current')")
                        except Exception as e:
                            logger.debug(f"Page eval failed: {e}")

                    time.sleep(2)

                # Disconnect (don't close — user's browser stays open)
                browser.close()

            if captured["bearer"] and captured["cookies"]:
                self._store.save_credentials(captured)
                return True, "Dang nhap thanh cong! Credentials da luu."
            elif captured["cookies"]:
                self._store.save_credentials(captured)
                return True, "Da luu cookies (khong co bearer token)."
            else:
                return False, (
                    f"Het thoi gian ({timeout}s). Hay dang nhap DeepSeek "
                    "trong trinh duyet va thu lai."
                )

        except Exception as e:
            logger.error(f"Credential capture error: {e}")
            return False, f"Loi: {e}"
