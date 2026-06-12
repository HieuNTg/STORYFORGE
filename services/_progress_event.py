"""ProgressEvent dataclass for pipeline progress tracking.

Internal module — import ProgressEvent via services.progress_tracker,
which re-exports it as the stable import surface.
"""

import time
from dataclasses import dataclass, field


@dataclass
class ProgressEvent:
    """A structured progress event."""

    step: str  # "layer1", "layer2", "layer3", "gate", "revision", "scoring"
    status: str  # "started", "in_progress", "retry", "completed", "failed"
    message: str  # Human-readable message
    detail: str = ""  # Optional detail (e.g., chapter number)
    progress: float = 0.0  # 0.0-1.0 within this step
    timestamp: float = field(default_factory=time.time)

    def to_log_prefix(self) -> str:
        """Format as log prefix for backward-compatible log messages."""
        step_labels = {
            "layer1": "L1",
            "layer2": "L2",
            "layer3": "L3",
            "gate": "GATE",
            "revision": "REVISION",
            "scoring": "METRICS",
        }
        label = step_labels.get(self.step, self.step.upper())
        status_icons = {
            "started": "▶",
            "in_progress": "⟳",
            "retry": "↻",
            "completed": "✓",
            "failed": "✗",
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
