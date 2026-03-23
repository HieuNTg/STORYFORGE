"""Quản lý lifecycle server OpenClaw Zero Token."""

import atexit
import logging
import os
import platform
import shutil
import subprocess
import time
import urllib.request
import urllib.error
from typing import Optional

logger = logging.getLogger(__name__)

# Đường dẫn mặc định tới OpenClaw
OPENCLAW_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "vendor", "openclaw-zero-token",
)


class OpenClawManager:
    """Singleton quản lý server OpenClaw Zero Token."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._process: Optional[subprocess.Popen] = None
        self._port = 3002
        self._use_wsl = False
        # Tự động dọn dẹp khi thoát
        atexit.register(self.stop)

    @property
    def is_windows(self) -> bool:
        return platform.system() == "Windows"

    def _detect_wsl(self) -> bool:
        """Kiểm tra WSL2 có sẵn trên Windows không."""
        if not self.is_windows:
            return False
        try:
            result = subprocess.run(
                ["wsl", "--status"],
                capture_output=True, text=True, timeout=10,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def _check_prerequisites(self) -> tuple[bool, str]:
        """Kiểm tra điều kiện cần thiết để chạy OpenClaw."""
        # Kiểm tra thư mục vendor
        if not os.path.isdir(OPENCLAW_DIR):
            return False, (
                "Chưa cài OpenClaw. Chạy:\n"
                "  git submodule update --init vendor/openclaw-zero-token"
            )

        # Trên Windows, kiểm tra WSL2
        if self.is_windows:
            if not self._detect_wsl():
                return False, (
                    "Windows cần WSL2 để chạy OpenClaw.\n"
                    "Cài đặt: wsl --install"
                )
            self._use_wsl = True
            return True, "WSL2 detected"

        # Trên Linux/macOS, kiểm tra Node.js
        if not shutil.which("node"):
            return False, "Cần cài Node.js >= 18"

        return True, "OK"

    def start(self, port: int = 3002) -> tuple[bool, str]:
        """Khởi động OpenClaw server."""
        if self._process and self._process.poll() is None:
            return True, f"Server đang chạy trên port {self._port}"

        self._port = port

        ok, msg = self._check_prerequisites()
        if not ok:
            return False, msg

        try:
            server_script = os.path.join(OPENCLAW_DIR, "server.sh")

            if self._use_wsl:
                # Chuyển đổi đường dẫn Windows sang WSL
                wsl_path = subprocess.run(
                    ["wsl", "wslpath", "-u", OPENCLAW_DIR],
                    capture_output=True, text=True,
                ).stdout.strip()
                cmd = ["wsl", "bash", "-c", f"cd {wsl_path} && PORT={port} ./server.sh"]
            else:
                cmd = ["bash", server_script]

            env = os.environ.copy()
            env["PORT"] = str(port)

            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                cwd=OPENCLAW_DIR if not self._use_wsl else None,
            )

            # Chờ server sẵn sàng (tối đa 30s)
            for _ in range(30):
                time.sleep(1)
                if self.health_check():
                    logger.info(f"OpenClaw đã sẵn sàng trên port {port}")
                    return True, f"Server đang chạy trên port {port}"

            # Timeout
            self.stop()
            return False, "OpenClaw không khởi động được sau 30s"

        except Exception as e:
            logger.error(f"Lỗi khởi động OpenClaw: {e}")
            return False, f"Lỗi: {str(e)}"

    def stop(self):
        """Dừng OpenClaw server."""
        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except (subprocess.TimeoutExpired, Exception):
                try:
                    self._process.kill()
                except Exception:
                    pass
            self._process = None
            logger.info("OpenClaw đã dừng")

    def health_check(self) -> bool:
        """Kiểm tra server có đang chạy và phản hồi không."""
        try:
            url = f"http://localhost:{self._port}/v1/models"
            req = urllib.request.urlopen(url, timeout=5)
            return req.status == 200
        except Exception:
            return False

    def get_status(self) -> dict:
        """Lấy trạng thái chi tiết của server."""
        running = self._process is not None and self._process.poll() is None
        healthy = self.health_check() if running else False
        return {
            "running": running,
            "healthy": healthy,
            "port": self._port,
            "use_wsl": self._use_wsl,
            "openclaw_dir": OPENCLAW_DIR,
            "dir_exists": os.path.isdir(OPENCLAW_DIR),
        }
