"""Resume-status derivation — Piece N.

Given a checkpoint metadata dict (as returned by ``PipelineOrchestrator.list_checkpoints``)
plus its continuation-history sidecar, decide whether the story looks "interrupted"
(i.e. partial L1 generation failed mid-flight and the user should be offered a
"Resume from chapter N" affordance on the library card).

Definition of *interrupted*:

* Checkpoint exists with ``chapter_count < outline_count`` (chapters_written < target).
* No continuation-history event in the last ``RECENT_SUCCESS_WINDOW_HOURS``
  (default 6h) — a successful continuation within that window means the user
  has already recovered and the story is no longer in a stuck state.

Returns three derived fields:

* ``interrupted`` (bool) — show the affordance.
* ``resume_from_chapter`` (int | None) — 1-indexed next chapter to write
  (= ``chapters_written + 1``). ``None`` when not interrupted.
* ``target_chapters`` (int) — original goal (``outline_count``).

Best-effort: any malformed input falls through as ``interrupted=False``. Pure
function — no I/O beyond ``services.continuation_history.read_events``.
"""

from datetime import datetime, timezone
from typing import Optional

from services.continuation_history import read_events

# Window after which a successful continuation no longer "covers" an interrupt.
RECENT_SUCCESS_WINDOW_HOURS = 6


def _has_recent_continuation(filename: str, *, now: Optional[datetime] = None) -> bool:
    """True if the sidecar has any event newer than ``RECENT_SUCCESS_WINDOW_HOURS``."""
    events = read_events(filename)
    if not events:
        return False
    now = now or datetime.now(timezone.utc)
    cutoff_seconds = RECENT_SUCCESS_WINDOW_HOURS * 3600
    for ev in events:
        ts = ev.get("ts") if isinstance(ev, dict) else None
        if not isinstance(ts, str):
            continue
        try:
            # Stored format: "2026-05-03T22:39:00Z" — strip the trailing Z.
            ev_dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if (now - ev_dt).total_seconds() <= cutoff_seconds:
            return True
    return False


def derive_resume_status(checkpoint: dict, *, now: Optional[datetime] = None) -> dict:
    """Compute interrupted/resume_from_chapter/target_chapters for one checkpoint dict.

    Returns a dict with keys ``interrupted``, ``resume_from_chapter``, ``target_chapters``.
    Always returns the keys (never raises) so callers can ``dict.update(...)`` blindly.
    """
    target = int(checkpoint.get("outline_count") or 0)
    written = int(checkpoint.get("chapter_count") or 0)
    filename = checkpoint.get("file") or ""

    # Cannot derive without a target. Treat unknown target as "not interrupted".
    if target <= 0 or written >= target:
        return {
            "interrupted": False,
            "resume_from_chapter": None,
            "target_chapters": target,
        }

    if filename and _has_recent_continuation(filename, now=now):
        # User already recovered recently; suppress the affordance.
        return {
            "interrupted": False,
            "resume_from_chapter": None,
            "target_chapters": target,
        }

    return {
        "interrupted": True,
        "resume_from_chapter": written + 1,
        "target_chapters": target,
    }
