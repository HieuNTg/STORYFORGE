"""Structured progress tracking for pipeline steps.

Emits typed progress events that UI can render as visual indicators.
Events are persisted in Redis when a session_id is provided.
"""

import json
import os
import time
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

_SESSION_TTL = 86400  # 24 hours


def _session_key(session_id: str, namespace: str) -> str:
    return f"storyforge:session:{session_id}:{namespace}"


def _make_redis_client():
    """Create a Redis client from REDIS_URL env var. Raises if unavailable."""
    redis_url = os.environ.get("REDIS_URL", "").strip()
    if not redis_url:
        raise RuntimeError(
            "REDIS_URL is not set. Redis is required for session state. "
            "Start Redis via docker-compose and set REDIS_URL."
        )
    try:
        import redis as _redis_lib
    except ImportError as exc:
        raise RuntimeError(
            "redis package is not installed. Run: pip install redis"
        ) from exc
    client = _redis_lib.from_url(redis_url, decode_responses=True)
    client.ping()
    return client


@dataclass
class ProgressEvent:
    """A structured progress event."""
    step: str           # "layer1", "layer2", "layer3", "gate", "revision", "scoring"
    status: str         # "started", "in_progress", "retry", "completed", "failed"
    message: str        # Human-readable message
    detail: str = ""    # Optional detail (e.g., chapter number)
    progress: float = 0.0  # 0.0-1.0 within this step
    timestamp: float = field(default_factory=time.time)

    def to_log_prefix(self) -> str:
        """Format as log prefix for backward-compatible log messages."""
        step_labels = {
            "layer1": "L1", "layer2": "L2", "layer3": "L3",
            "gate": "GATE", "revision": "REVISION", "scoring": "METRICS",
        }
        label = step_labels.get(self.step, self.step.upper())
        status_icons = {
            "started": "▶", "in_progress": "⟳", "retry": "↻",
            "completed": "✓", "failed": "✗",
        }
        icon = status_icons.get(self.status, "•")
        return f"[{label}] {icon}"

    def to_dict(self) -> dict:
        return {
            "step": self.step,
            "status": self.status,
            "message": self.message,
            "detail": self.detail,
            "progress": self.progress,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ProgressEvent":
        return cls(
            step=d["step"],
            status=d["status"],
            message=d["message"],
            detail=d.get("detail", ""),
            progress=d.get("progress", 0.0),
            timestamp=d.get("timestamp", 0.0),
        )


class ProgressTracker:
    """Track pipeline progress with structured events.

    When session_id is provided, events are persisted in Redis.
    Without session_id, events accumulate in memory only (backward compat).
    """

    def __init__(self, callback=None, session_id: str = ""):
        self._callback = callback
        self._session_id = session_id
        self._redis = None
        self._local_events: list[ProgressEvent] = []

        if session_id:
            try:
                self._redis = _make_redis_client()
                logger.debug("ProgressTracker: Redis connected for session %s", session_id)
            except Exception as exc:
                logger.error("ProgressTracker: Redis init failed: %s", exc)
                raise

    def emit(self, step: str, status: str, message: str,
             detail: str = "", progress: float = 0.0) -> ProgressEvent:
        """Emit a progress event."""
        event = ProgressEvent(
            step=step, status=status, message=message,
            detail=detail, progress=progress,
        )

        if self._redis and self._session_id:
            key = _session_key(self._session_id, "progress")
            try:
                self._redis.rpush(key, json.dumps(event.to_dict()))
                self._redis.expire(key, _SESSION_TTL)
            except Exception as exc:
                logger.warning("ProgressTracker: Redis write error: %s", exc)
                self._local_events.append(event)
        else:
            self._local_events.append(event)

        if self._callback:
            log_msg = f"{event.to_log_prefix()} {message}"
            if detail:
                log_msg += f" ({detail})"
            self._callback(log_msg)

        return event

    def gate_started(self, layer: int):
        self.emit("gate", "started", f"Quality gate kiểm tra Layer {layer}...")

    def gate_passed(self, layer: int, score: float):
        self.emit("gate", "completed", f"Quality gate PASSED: {score:.1f}/5.0",
                  detail=f"Layer {layer}")

    def gate_retry(self, layer: int, score: float, attempt: int):
        self.emit("gate", "retry", f"Score {score:.1f} thấp, thử lại lần {attempt}",
                  detail=f"Layer {layer}")

    def gate_failed(self, layer: int, score: float):
        self.emit("gate", "failed", f"Score {score:.1f} vẫn thấp, tiếp tục",
                  detail=f"Layer {layer}")

    def revision_started(self, total_weak: int):
        self.emit("revision", "started", f"Phát hiện {total_weak} chương yếu, bắt đầu sửa...")

    def revision_chapter(self, chapter_num: int, pass_num: int, total_weak: int, current: int):
        progress = current / max(total_weak, 1)
        self.emit("revision", "in_progress",
                  f"Đang sửa chương {chapter_num} (lần {pass_num})",
                  detail=f"{current}/{total_weak}",
                  progress=progress)

    def revision_chapter_done(self, chapter_num: int, old_score: float, new_score: float):
        delta = new_score - old_score
        self.emit("revision", "completed",
                  f"Chương {chapter_num}: {old_score:.1f} → {new_score:.1f} ({delta:+.1f})",
                  detail=f"ch{chapter_num}")

    def revision_done(self, revised: int, total_weak: int):
        self.emit("revision", "completed",
                  f"Hoàn tất: sửa {revised}/{total_weak} chương",
                  progress=1.0)

    def scoring_started(self, layer: int):
        self.emit("scoring", "started", f"Đang chấm điểm Layer {layer}...")

    def scoring_done(self, layer: int, score: float):
        self.emit("scoring", "completed", f"Layer {layer}: {score:.1f}/5.0")

    @property
    def events(self) -> list[ProgressEvent]:
        if self._redis and self._session_id:
            key = _session_key(self._session_id, "progress")
            try:
                self._redis.expire(key, _SESSION_TTL)
                raw = self._redis.lrange(key, 0, -1)
                return [ProgressEvent.from_dict(json.loads(r)) for r in raw]
            except Exception as exc:
                logger.warning("ProgressTracker: Redis read error: %s", exc)
        return list(self._local_events)

    @property
    def last_event(self) -> ProgressEvent | None:
        evts = self.events
        return evts[-1] if evts else None
