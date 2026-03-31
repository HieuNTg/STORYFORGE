"""Lightweight Prometheus text exposition — no external dependencies.

Thread-safe counters, gauges, and histograms backed by threading.Lock.
Call format_metrics() to get a Prometheus text exposition format string.
"""

import threading
import time
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Internal primitives
# ---------------------------------------------------------------------------

class _Counter:
    """Monotonically increasing counter with optional labels."""

    def __init__(self, name: str, help_text: str, label_names: Optional[List[str]] = None):
        self.name = name
        self.help_text = help_text
        self.label_names = label_names or []
        self._lock = threading.Lock()
        self._values: Dict[tuple, float] = {}

    def inc(self, labels: Optional[Dict[str, str]] = None, amount: float = 1.0) -> None:
        key = self._key(labels)
        with self._lock:
            self._values[key] = self._values.get(key, 0.0) + amount

    def _key(self, labels: Optional[Dict[str, str]]) -> tuple:
        if not labels:
            return ()
        return tuple(labels.get(n, "") for n in self.label_names)

    def render(self) -> str:
        lines = [
            f"# HELP {self.name} {self.help_text}",
            f"# TYPE {self.name} counter",
        ]
        with self._lock:
            items = list(self._values.items())
        for key, val in items:
            label_str = _format_labels(self.label_names, key)
            lines.append(f"{self.name}{label_str} {val}")
        if not items:
            lines.append(f"{self.name} 0")
        return "\n".join(lines)


class _Gauge:
    """Gauge that can go up or down."""

    def __init__(self, name: str, help_text: str):
        self.name = name
        self.help_text = help_text
        self._lock = threading.Lock()
        self._value: float = 0.0

    def inc(self, amount: float = 1.0) -> None:
        with self._lock:
            self._value += amount

    def dec(self, amount: float = 1.0) -> None:
        with self._lock:
            self._value -= amount

    def set(self, value: float) -> None:
        with self._lock:
            self._value = value

    def render(self) -> str:
        with self._lock:
            val = self._value
        return "\n".join([
            f"# HELP {self.name} {self.help_text}",
            f"# TYPE {self.name} gauge",
            f"{self.name} {val}",
        ])


class _Histogram:
    """Histogram with configurable buckets."""

    def __init__(self, name: str, help_text: str, buckets: List[float],
                 label_names: Optional[List[str]] = None):
        self.name = name
        self.help_text = help_text
        self.label_names = label_names or []
        self._buckets = sorted(buckets)
        self._lock = threading.Lock()
        # key -> (bucket_counts list, sum, count)
        self._data: Dict[tuple, List] = {}

    def _ensure_key(self, key: tuple) -> None:
        if key not in self._data:
            self._data[key] = [[0] * len(self._buckets), 0.0, 0]

    def observe(self, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        key = self._key(labels)
        with self._lock:
            self._ensure_key(key)
            counts, total, n = self._data[key]
            for i, bound in enumerate(self._buckets):
                if value <= bound:
                    counts[i] += 1
            self._data[key] = [counts, total + value, n + 1]

    def _key(self, labels: Optional[Dict[str, str]]) -> tuple:
        if not labels:
            return ()
        return tuple(labels.get(n, "") for n in self.label_names)

    def render(self) -> str:
        lines = [
            f"# HELP {self.name} {self.help_text}",
            f"# TYPE {self.name} histogram",
        ]
        with self._lock:
            items = list(self._data.items())

        if not items:
            # emit empty skeleton
            for bound in self._buckets:
                lines.append(f'{self.name}_bucket{{le="{bound}"}} 0')
            lines.append(f'{self.name}_bucket{{le="+Inf"}} 0')
            lines.append(f"{self.name}_sum 0")
            lines.append(f"{self.name}_count 0")
            return "\n".join(lines)

        for key, (counts, total, n) in items:
            base_labels = _format_labels(self.label_names, key)
            # strip closing brace to append le= label
            prefix = base_labels.rstrip("}") if base_labels else "{"
            # counts[i] is already cumulative (observe increments all bounds >= value)
            for i, bound in enumerate(self._buckets):
                le_label = f'{prefix},le="{bound}"}}' if base_labels else f'{{le="{bound}"}}'
                lines.append(f"{self.name}_bucket{le_label} {counts[i]}")
            # +Inf bucket equals total observation count
            inf_label = f'{prefix},le="+Inf"}}' if base_labels else '{le="+Inf"}'
            lines.append(f"{self.name}_bucket{inf_label} {n}")
            lines.append(f"{self.name}_sum{base_labels} {total}")
            lines.append(f"{self.name}_count{base_labels} {n}")

        return "\n".join(lines)


def _format_labels(names: List[str], values: tuple) -> str:
    if not names or not values:
        return ""
    pairs = ", ".join(f'{k}="{v}"' for k, v in zip(names, values))
    return "{" + pairs + "}"


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

pipeline_runs_total = _Counter(
    "pipeline_runs_total",
    "Total pipeline runs by status.",
    label_names=["status"],
)

pipeline_duration_seconds = _Histogram(
    "pipeline_duration_seconds",
    "Pipeline execution duration in seconds.",
    buckets=[1, 5, 10, 30, 60, 120, 300, 600],
)

llm_requests_total = _Counter(
    "llm_requests_total",
    "Total LLM API requests.",
    label_names=["provider", "model"],
)

llm_errors_total = _Counter(
    "llm_errors_total",
    "Total LLM API errors.",
    label_names=["provider", "error_type"],
)

quality_score_histogram = _Histogram(
    "quality_score_histogram",
    "Distribution of story quality scores.",
    buckets=[1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0],
)

active_pipelines = _Gauge(
    "active_pipelines",
    "Number of currently running pipelines.",
)

_ALL_METRICS = [
    pipeline_runs_total,
    pipeline_duration_seconds,
    llm_requests_total,
    llm_errors_total,
    quality_score_histogram,
    active_pipelines,
]


def format_metrics() -> str:
    """Return all metrics in Prometheus text exposition format (0.0.4)."""
    parts = [m.render() for m in _ALL_METRICS]
    return "\n".join(parts) + "\n"
