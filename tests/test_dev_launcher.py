"""Tests for the cross-platform dev launcher (scripts/dev.py)."""

import importlib.util
import sys
from pathlib import Path

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
