#!/usr/bin/env python3
"""StoryForge cross-platform dev launcher (stdlib only).

Runs the FastAPI backend and the Next.js frontend, prefixes their output with
[api] / [web], and stops both on Ctrl+C or when either one exits.

Usage: python scripts/dev.py [--api-port 7860] [--web-port 3001]
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IS_WINDOWS = sys.platform == "win32"
GRACE_SECONDS = 5


def build_commands(api_port: int, web_port: int) -> list[tuple[str, list[str], Path]]:
    """Return (name, argv, cwd) for each child. api_port is passed via env."""
    npm = "npm.cmd" if IS_WINDOWS else "npm"
    return [
        ("api", [sys.executable, "app.py"], ROOT),
        ("web", [npm, "run", "dev", "--", "--port", str(web_port)], ROOT / "frontend"),
    ]


def child_env(name: str, api_port: int) -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    if name == "api":
        env["STORYFORGE_PORT"] = str(api_port)
        env["STORYFORGE_DEBUG"] = "1"
    return env


def _spawn(name: str, argv: list[str], cwd: Path, api_port: int) -> subprocess.Popen:
    kwargs: dict = {}
    if IS_WINDOWS:
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(
        argv,
        cwd=str(cwd),
        env=child_env(name, api_port),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        **kwargs,
    )


def _pump(name: str, proc: subprocess.Popen) -> None:
    assert proc.stdout is not None
    for line in proc.stdout:
        print(f"[{name}] {line.rstrip()}", flush=True)


def _signal_group(proc: subprocess.Popen, sig_kind: str) -> None:
    if proc.poll() is not None:
        return
    try:
        if IS_WINDOWS:
            if sig_kind == "term":
                proc.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    capture_output=True,
                    check=False,
                )
        else:
            os.killpg(proc.pid, signal.SIGTERM if sig_kind == "term" else signal.SIGKILL)
    except (OSError, ProcessLookupError):
        pass


def terminate_all(procs: list[subprocess.Popen]) -> None:
    for p in procs:
        _signal_group(p, "term")
    deadline = time.monotonic() + GRACE_SECONDS
    for p in procs:
        try:
            p.wait(timeout=max(0.0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            _signal_group(p, "kill")
            try:
                p.wait(timeout=GRACE_SECONDS)
            except subprocess.TimeoutExpired:
                pass
    # A group leader may exit while descendants linger (npm -> node): sweep.
    for p in procs:
        if not IS_WINDOWS:
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except (OSError, ProcessLookupError):
                pass
        else:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(p.pid)],
                capture_output=True,
                check=False,
            )


def run(commands: list[tuple[str, list[str], Path]], api_port: int) -> int:
    procs: list[subprocess.Popen] = []
    try:
        for name, argv, cwd in commands:
            procs.append(_spawn(name, argv, cwd, api_port))
        for (name, _, _), p in zip(commands, procs):
            threading.Thread(target=_pump, args=(name, p), daemon=True).start()
        code = 0
        while True:
            for (name, _, _), p in zip(commands, procs):
                rc = p.poll()
                if rc is not None:
                    print(f"[dev] {name} exited with code {rc}; stopping the rest.", flush=True)
                    return rc or code
            time.sleep(0.3)
    except KeyboardInterrupt:
        print("\n[dev] Ctrl+C received; stopping.", flush=True)
        return 0
    finally:
        terminate_all(procs)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run StoryForge API + web in dev mode.")
    parser.add_argument("--api-port", type=int, default=7860)
    parser.add_argument("--web-port", type=int, default=3001)
    args = parser.parse_args(argv)
    print(f"[dev] API  http://localhost:{args.api_port}")
    print(f"[dev] Web  http://localhost:{args.web_port}/forge/", flush=True)
    return run(build_commands(args.api_port, args.web_port), args.api_port)


if __name__ == "__main__":
    sys.exit(main())
