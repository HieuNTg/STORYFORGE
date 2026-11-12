"""Structured progress tracking for pipeline steps.

Emits typed progress events that UI can render as visual indicators.
Events are kept in memory for the life of the tracker.
"""

import logging

# Stable import surface: consumers (pipeline, tests) import ProgressEvent
# from services.progress_tracker, not from the internal module.
from services._progress_event import ProgressEvent  # noqa: F401

logger = logging.getLogger(__name__)


class ProgressTracker:
    """Track pipeline progress with structured events.

    Events accumulate in memory. ``session_id`` is kept for callers that tag
    a tracker with the pipeline session it belongs to.
    """

    def __init__(self, callback=None, session_id: str = ""):
        self._callback = callback
        self._session_id = session_id
        self._local_events: list[ProgressEvent] = []

    def emit(
        self,
        step: str,
        status: str,
        message: str,
        detail: str = "",
        progress: float = 0.0,
    ) -> ProgressEvent:
        """Emit a progress event."""
        event = ProgressEvent(
            step=step,
            status=status,
            message=message,
            detail=detail,
            progress=progress,
        )

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
        self.emit(
            "gate",
            "completed",
            f"Quality gate PASSED: {score:.1f}/5.0",
            detail=f"Layer {layer}",
        )

    def gate_retry(self, layer: int, score: float, attempt: int):
        self.emit(
            "gate",
            "retry",
            f"Score {score:.1f} thấp, thử lại lần {attempt}",
            detail=f"Layer {layer}",
        )

    def gate_failed(self, layer: int, score: float):
        self.emit(
            "gate",
            "failed",
            f"Score {score:.1f} vẫn thấp, tiếp tục",
            detail=f"Layer {layer}",
        )

    def revision_started(self, total_weak: int):
        self.emit(
            "revision", "started", f"Phát hiện {total_weak} chương yếu, bắt đầu sửa..."
        )

    def revision_chapter(
        self, chapter_num: int, pass_num: int, total_weak: int, current: int
    ):
        progress = current / max(total_weak, 1)
        self.emit(
            "revision",
            "in_progress",
            f"Đang sửa chương {chapter_num} (lần {pass_num})",
            detail=f"{current}/{total_weak}",
            progress=progress,
        )

    def revision_chapter_done(
        self, chapter_num: int, old_score: float, new_score: float
    ):
        delta = new_score - old_score
        self.emit(
            "revision",
            "completed",
            f"Chương {chapter_num}: {old_score:.1f} → {new_score:.1f} ({delta:+.1f})",
            detail=f"ch{chapter_num}",
        )

    def revision_done(self, revised: int, total_weak: int):
        self.emit(
            "revision",
            "completed",
            f"Hoàn tất: sửa {revised}/{total_weak} chương",
            progress=1.0,
        )

    def scoring_started(self, layer: int):
        self.emit("scoring", "started", f"Đang chấm điểm Layer {layer}...")

    def scoring_done(self, layer: int, score: float):
        self.emit("scoring", "completed", f"Layer {layer}: {score:.1f}/5.0")

    @property
    def events(self) -> list[ProgressEvent]:
        return list(self._local_events)

    @property
    def last_event(self) -> ProgressEvent | None:
        evts = self.events
        return evts[-1] if evts else None
