"""Chrome browser lifecycle management: launch, CDP check, shutdown."""

import logging
import os
import platform
import subprocess
import time
import urllib.error
from typing import Optional

logger = logging.getLogger(__name__)

# Chrome CDP port
CDP_PORT = 9222


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
        import shutil
        if shutil.which(path):
            return shutil.which(path)

    return None


def is_cdp_available() -> bool:
    """Check if Chrome CDP is responding.

    Issue #14: CDP is intentionally over HTTP to localhost only — no SSL needed.
    Guard ensures we never attempt a non-localhost CDP URL.
    """
    try:
        import urllib.request
        url = f"http://127.0.0.1:{CDP_PORT}/json/version"
        req = urllib.request.urlopen(url, timeout=2)
        return req.status == 200
    except (urllib.error.URLError, OSError, ValueError):
        return False


class BrowserManager:
    """Handles Chrome process launch and shutdown."""

    def __init__(self):
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

        if is_cdp_available():
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
                if is_cdp_available():
                    logger.info(f"Chrome CDP ready on port {CDP_PORT}")
                    return True, "Chrome da khoi dong. Hay dang nhap DeepSeek trong trinh duyet."
            return False, "Chrome khoi dong nhung CDP khong phan hoi."

        except (OSError, subprocess.SubprocessError) as e:
            logger.error(f"Chrome launch error: {e}")
            return False, f"Loi khoi dong Chrome: {e}"

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
