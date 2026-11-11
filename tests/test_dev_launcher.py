"""Tests for the cross-platform dev launcher (scripts/dev.py)."""

import importlib.util
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load():
    spec = importlib.util.spec_from_file_location("dev_launcher", ROOT / "scripts" / "dev.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_build_commands():
    dev = _load()
    npm = "npm.cmd" if sys.platform == "win32" else "npm"
    cmds = dev.build_commands(7860, 3001)
    assert cmds == [
        ("api", [sys.executable, "app.py"], ROOT),
        ("web", [npm, "run", "dev", "--", "--port", "3001"], ROOT / "frontend"),
    ]


def test_child_env():
    dev = _load()
    api = dev.child_env("api", 9000)
    assert api["STORYFORGE_PORT"] == "9000"
    assert api["STORYFORGE_DEBUG"] == "1"


def test_child_env_forces_utf8_for_api():
    dev = _load()
    env = dev.child_env("api", 7860)
    assert env["PYTHONIOENCODING"] == "utf-8"
    assert env["PYTHONUTF8"] == "1"


@pytest.mark.timeout(30)
def test_supervisor_stops_sleeper_when_other_child_dies():
    dev = _load()
    cmds = [
        ("api", [sys.executable, "-c", "import time; time.sleep(60)"], ROOT),
        ("web", [sys.executable, "-c", "print('bye')"], ROOT),
    ]
    procs: list = []
    start = time.monotonic()
    rc = dev.run(cmds, 7860, procs)
    assert rc != 0
    assert time.monotonic() - start < 15
    assert len(procs) == 2
    assert procs[0].poll() is not None
