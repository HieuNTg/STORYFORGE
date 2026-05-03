"""Continuation history sidecar — advisory log of when chapters were appended.

Writes ``<checkpoint>.history.json`` next to each checkpoint file when a story
is continued. Purely for UX (library pill + reader jump-to-new-chapter); never
fails the calling pipeline if the disk write breaks.
"""

import json
import logging
import os
import pathlib
import re
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# Cap retention to avoid unbounded growth; matches the v1 spec.
_MAX_EVENTS = 20


def _project_root() -> pathlib.Path:
    return pathlib.Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))).resolve()


def checkpoint_dir() -> pathlib.Path:
    return _project_root() / "output" / "checkpoints"


def slug_for_title(title: str) -> str:
    """Match ``CheckpointManager.save`` filename slug exactly."""
    raw = (title or "untitled")[:30]
    return re.sub(r"[^\w\-]", "_", raw)


def sidecar_path_for(checkpoint_filename: str) -> pathlib.Path:
    """Resolve sidecar path for ``<filename>.json`` → ``<filename>.history.json``."""
    safe = pathlib.Path(checkpoint_filename).name
    if safe.endswith(".json"):
        safe = safe[: -len(".json")]
    return checkpoint_dir() / f"{safe}.history.json"


def read_events(checkpoint_filename: str) -> list[dict]:
    """Return events list (newest-last) or ``[]`` when sidecar missing/corrupt."""
    path = sidecar_path_for(checkpoint_filename)
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        events = data.get("events") if isinstance(data, dict) else None
        return events if isinstance(events, list) else []
    except (OSError, json.JSONDecodeError) as e:
        logger.info("history sidecar read skip %s: %s", path.name, e)
        return []


def latest_event(checkpoint_filename: str) -> Optional[dict]:
    events = read_events(checkpoint_filename)
    return events[-1] if events else None


def record_continuation(
    title: str,
    previous_chapter_count: int,
    new_chapter_count: int,
    layer: int = 1,
) -> Optional[pathlib.Path]:
    """Append a continuation event to the sidecar. Best-effort, never raises.

    Filename derived from the same slug rule used by ``CheckpointManager.save``
    so the sidecar lands next to ``<slug>_layer<L>.json``. Returns the written
    path on success, ``None`` on any failure.
    """
    if new_chapter_count <= previous_chapter_count:
        # Nothing was actually added; skip the noise.
        return None

    slug = slug_for_title(title)
    checkpoint_filename = f"{slug}_layer{layer}.json"
    path = sidecar_path_for(checkpoint_filename)

    event = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "previous_chapter_count": int(previous_chapter_count),
        "new_chapter_count": int(new_chapter_count),
        "added": int(new_chapter_count - previous_chapter_count),
    }

    try:
        events = read_events(checkpoint_filename)
        events.append(event)
        if len(events) > _MAX_EVENTS:
            events = events[-_MAX_EVENTS:]
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"events": events}, f, ensure_ascii=False, indent=2)
        logger.info("Continuation history appended: %s (+%d)", path.name, event["added"])
        return path
    except OSError as e:
        logger.warning("Continuation sidecar write failed (%s): %s", path.name, e)
        return None
