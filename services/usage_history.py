"""Per-story LLM usage sidecar — advisory token/cost log per checkpoint.

Mirrors :mod:`services.continuation_history`: writes ``<checkpoint>.usage.json``
next to each checkpoint, capturing every LLM call attributed to the story.
Like the continuation sidecar, this is best-effort and **never** fails the
pipeline — sidecar write errors are swallowed with a warning log.

Pricing comes from :mod:`services.llm_pricing` (DRY); unknown models fall back
to ``_default`` rates rather than crashing or returning zero.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

# Reuse slug rule + checkpoint_dir from the continuation sidecar (DRY).
from services.continuation_history import (
    checkpoint_dir,
    slug_for_title,
)
from services.llm_pricing import compute_cost

logger = logging.getLogger(__name__)

# Cap raw events; totals are computed incrementally so rotation never loses data.
_MAX_EVENTS = 500


def usage_sidecar_path_for(checkpoint_filename: str):
    """Resolve usage sidecar path: ``<filename>.json`` → ``<filename>.usage.json``."""
    import pathlib
    safe = pathlib.Path(checkpoint_filename).name
    if safe.endswith(".json"):
        safe = safe[: -len(".json")]
    return checkpoint_dir() / f"{safe}.usage.json"


def _empty_totals() -> dict:
    return {"total_tokens": 0, "total_cost_usd": 0.0, "call_count": 0}


def read_usage(checkpoint_filename: str) -> Optional[dict]:
    """Return ``{events, totals}`` or ``None`` if no sidecar exists.

    Corrupted sidecar → ``None`` (logged at info level so we don't spam).
    """
    path = usage_sidecar_path_for(checkpoint_filename)
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return None
        events = data.get("events") if isinstance(data.get("events"), list) else []
        totals = data.get("totals") if isinstance(data.get("totals"), dict) else _empty_totals()
        # Defensive: ensure required keys exist with sane defaults.
        for k, v in _empty_totals().items():
            totals.setdefault(k, v)
        return {"events": events, "totals": totals}
    except (OSError, json.JSONDecodeError) as e:
        logger.info("usage sidecar read skip %s: %s", path.name, e)
        return None


def usage_summary(checkpoint_filename: str) -> Optional[dict]:
    """Compact totals dict for the library list endpoint, or ``None`` if missing."""
    data = read_usage(checkpoint_filename)
    if data is None:
        return None
    return data["totals"]


def record_usage(
    title: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    layer: int = 1,
    cost_usd: Optional[float] = None,
) -> Optional[str]:
    """Append a usage event for the given story title. Best-effort, never raises.

    ``cost_usd`` is optional — if not supplied we compute it via
    :func:`services.llm_pricing.compute_cost`. Unknown models will resolve to
    the ``_default`` pricing entry; if the caller wants a true zero (e.g. free
    tier) they should pass ``cost_usd=0.0`` explicitly.

    Returns the sidecar path on success, ``None`` on any failure.
    """
    if not title:
        return None
    prompt_tokens = max(0, int(prompt_tokens or 0))
    completion_tokens = max(0, int(completion_tokens or 0))
    if cost_usd is None:
        cost_usd = compute_cost(model or "", prompt_tokens, completion_tokens)
    cost_usd = max(0.0, float(cost_usd))

    slug = slug_for_title(title)
    checkpoint_filename = f"{slug}_layer{layer}.json"
    path = usage_sidecar_path_for(checkpoint_filename)

    event = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "model": model or "",
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "cost_usd": round(cost_usd, 8),
    }

    try:
        existing = read_usage(checkpoint_filename)
        if existing is None:
            events = []
            totals = _empty_totals()
        else:
            events = list(existing["events"])
            totals = dict(existing["totals"])

        # Update totals BEFORE rotation so we never lose aggregate data.
        totals["total_tokens"] = int(totals.get("total_tokens", 0)) + event["total_tokens"]
        totals["total_cost_usd"] = round(
            float(totals.get("total_cost_usd", 0.0)) + event["cost_usd"], 8
        )
        totals["call_count"] = int(totals.get("call_count", 0)) + 1

        events.append(event)
        if len(events) > _MAX_EVENTS:
            events = events[-_MAX_EVENTS:]

        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"events": events, "totals": totals}, f, ensure_ascii=False, indent=2)
        logger.debug("Usage sidecar appended: %s (+%d tokens, $%.6f)",
                     path.name, event["total_tokens"], event["cost_usd"])
        return str(path)
    except OSError as e:
        logger.warning("Usage sidecar write failed (%s): %s", path.name, e)
        return None
    except Exception as e:  # noqa: BLE001 — sidecar must never propagate
        logger.warning("Usage sidecar unexpected error (%s): %s", path.name, e)
        return None
