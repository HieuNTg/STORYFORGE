"""One version everywhere: pyproject, the FastAPI app, /api/health and the
CHANGELOG's release heading."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _pyproject_version() -> str:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]


def _changelog_version() -> str:
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    return re.search(r"^## \[(\d+\.\d+\.\d+)\]", text, re.M).group(1)


def test_versions_agree(client):
    from app import APP_VERSION, create_app

    assert _pyproject_version() == _changelog_version() == APP_VERSION == "2.0.0"
    assert create_app().version == APP_VERSION
    assert client.get("/api/health").json()["version"] == APP_VERSION
