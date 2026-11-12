"""Where the read-only data shipped with the code lives.

Prompts (``prompts/``), story templates (``templates/``) and the golden eval
set (``evals/golden_dataset.json``) are part of the source tree, not user data.
They live under ``STORYFORGE_BUNDLED_DATA_DIR`` when set, otherwise
``<repo>/data``.

The Docker image sets it to /app/bundled: /app/data is the storyforge-data
volume, which would keep serving the copies from the first image after an
upgrade or a branch switch. User data (database, config, logs, human evals)
stays in ``data/``.
"""

from __future__ import annotations

import os
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


def bundled_data_dir() -> Path:
    """Return ``STORYFORGE_BUNDLED_DATA_DIR`` or ``<repo>/data``. Read on every call."""
    raw = os.environ.get("STORYFORGE_BUNDLED_DATA_DIR", "").strip()
    return Path(raw) if raw else _REPO_ROOT / "data"
