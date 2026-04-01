"""Onboarding analytics — in-memory event tracking for the onboarding wizard."""

import time
from threading import Lock
from typing import Dict, List, Optional


MAX_EVENTS = 10_000


class OnboardingTracker:
    """Thread-safe in-memory tracker for onboarding funnel events."""

    def __init__(self, max_events: int = MAX_EVENTS) -> None:
        self._events: List[Dict] = []
        self._max_events = max_events
        self._lock = Lock()

    def track_step(self, session_id: str, step: str, duration_ms: int) -> None:
        """Record a completed wizard step."""
        event = {
            "session_id": session_id,
            "step": step,
            "event": "complete",
            "duration_ms": duration_ms,
            "timestamp": time.time(),
        }
        with self._lock:
            self._events.append(event)
            if len(self._events) > self._max_events:
                self._events = self._events[-self._max_events:]

    def track_dropout(self, session_id: str, step: str) -> None:
        """Record a dropout at a wizard step."""
        event = {
            "session_id": session_id,
            "step": step,
            "event": "dropout",
            "duration_ms": None,
            "timestamp": time.time(),
        }
        with self._lock:
            self._events.append(event)
            if len(self._events) > self._max_events:
                self._events = self._events[-self._max_events:]

    def get_funnel(self) -> Dict[str, Dict]:
        """Return per-step completion funnel data.

        Returns:
            {step: {count, avg_duration_ms, dropout_count}}
        """
        with self._lock:
            snapshot = list(self._events)

        funnel: Dict[str, Dict] = {}
        for ev in snapshot:
            step = ev["step"]
            if step not in funnel:
                funnel[step] = {"count": 0, "total_duration_ms": 0, "dropout_count": 0}

            if ev["event"] == "complete":
                funnel[step]["count"] += 1
                funnel[step]["total_duration_ms"] += ev["duration_ms"] or 0
            elif ev["event"] == "dropout":
                funnel[step]["dropout_count"] += 1

        result: Dict[str, Dict] = {}
        for step, data in funnel.items():
            count = data["count"]
            avg = data["total_duration_ms"] / count if count > 0 else None
            result[step] = {
                "count": count,
                "avg_duration_ms": avg,
                "dropout_count": data["dropout_count"],
            }
        return result


# Module-level singleton
tracker = OnboardingTracker()
