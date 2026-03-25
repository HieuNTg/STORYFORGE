"""Structured progress tracking for pipeline steps.

Emits typed progress events that UI can render as visual indicators.
"""

import time
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


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


class ProgressTracker:
    """Track pipeline progress with structured events.

    Wraps a simple progress_callback to emit ProgressEvent objects
    while maintaining backward-compatible string log output.
    """

    def __init__(self, callback=None):
        self._callback = callback
        self._events: list[ProgressEvent] = []

    def emit(self, step: str, status: str, message: str,
             detail: str = "", progress: float = 0.0) -> ProgressEvent:
        """Emit a progress event."""
        event = ProgressEvent(
            step=step, status=status, message=message,
            detail=detail, progress=progress,
        )
        self._events.append(event)

        # Backward-compatible: call string callback
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
        return list(self._events)

    @property
    def last_event(self) -> ProgressEvent | None:
        return self._events[-1] if self._events else None
