"""Thread-safe Prometheus metrics singleton for StoryForge.

Tracks requests, pipeline runs, SSE connections, and uptime.
No external prometheus_client library required — outputs raw text exposition.
"""

import threading
import time
from collections import defaultdict
from typing import Dict, List, Tuple

_DURATION_BUCKETS = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]


class PrometheusMetrics:
    """Singleton metrics collector. Use `prometheus_metrics` module-level instance."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._start_time = time.time()

        # storyforge_requests_total{method, path, status}
        self._requests: Dict[Tuple[str, str, str], int] = defaultdict(int)

        # storyforge_request_duration_seconds{path} -> (bucket_counts, sum, count)
        self._durations: Dict[str, List] = {}

        # storyforge_pipeline_runs_total{genre, status}
        self._pipeline_runs: Dict[Tuple[str, str], int] = defaultdict(int)

        # storyforge_active_sse_connections (gauge)
        self._active_sse: int = 0

    # ------------------------------------------------------------------
    # Public recording API
    # ------------------------------------------------------------------

    def record_request(self, method: str, path: str, status: int, duration_ms: float) -> None:
        """Record an HTTP request with its outcome and duration."""
        key = (method.upper(), path, str(status))
        duration_s = duration_ms / 1000.0
        with self._lock:
            self._requests[key] += 1
            if path not in self._durations:
                self._durations[path] = [[0] * len(_DURATION_BUCKETS), 0.0, 0]
            bucket_counts, total, n = self._durations[path]
            for i, bound in enumerate(_DURATION_BUCKETS):
                if duration_s <= bound:
                    bucket_counts[i] += 1
            self._durations[path] = [bucket_counts, total + duration_s, n + 1]

    def record_pipeline_run(self, genre: str, status: str) -> None:
        """Increment pipeline run counter for given genre + status."""
        with self._lock:
            self._pipeline_runs[(genre, status)] += 1

    def increment_sse(self) -> None:
        """Call when a new SSE connection is established."""
        with self._lock:
            self._active_sse += 1

    def decrement_sse(self) -> None:
        """Call when an SSE connection closes."""
        with self._lock:
            self._active_sse = max(0, self._active_sse - 1)

    # ------------------------------------------------------------------
    # Prometheus text exposition
    # ------------------------------------------------------------------

    def format_prometheus(self) -> str:
        """Return all metrics in Prometheus text exposition format 0.0.4."""
        with self._lock:
            requests_snapshot = dict(self._requests)
            durations_snapshot = {p: list(v) for p, v in self._durations.items()}
            pipeline_snapshot = dict(self._pipeline_runs)
            sse_count = self._active_sse
        uptime = time.time() - self._start_time

        lines: List[str] = []

        # --- storyforge_requests_total ---
        lines += [
            "# HELP storyforge_requests_total Total HTTP requests by method, path, status.",
            "# TYPE storyforge_requests_total counter",
        ]
        if requests_snapshot:
            for (method, path, status), count in requests_snapshot.items():
                lines.append(
                    f'storyforge_requests_total{{method="{method}",path="{path}",status="{status}"}} {count}'
                )
        else:
            lines.append("storyforge_requests_total 0")

        # --- storyforge_request_duration_seconds ---
        lines += [
            "# HELP storyforge_request_duration_seconds HTTP request duration in seconds.",
            "# TYPE storyforge_request_duration_seconds histogram",
        ]
        if durations_snapshot:
            for path, (bucket_counts, total, n) in durations_snapshot.items():
                for i, bound in enumerate(_DURATION_BUCKETS):
                    lines.append(
                        f'storyforge_request_duration_seconds_bucket{{path="{path}",le="{bound}"}} {bucket_counts[i]}'
                    )
                lines.append(
                    f'storyforge_request_duration_seconds_bucket{{path="{path}",le="+Inf"}} {n}'
                )
                lines.append(f'storyforge_request_duration_seconds_sum{{path="{path}"}} {total}')
                lines.append(f'storyforge_request_duration_seconds_count{{path="{path}"}} {n}')
        else:
            for bound in _DURATION_BUCKETS:
                lines.append(f'storyforge_request_duration_seconds_bucket{{le="{bound}"}} 0')
            lines.append('storyforge_request_duration_seconds_bucket{le="+Inf"} 0')
            lines.append("storyforge_request_duration_seconds_sum 0")
            lines.append("storyforge_request_duration_seconds_count 0")

        # --- storyforge_pipeline_runs_total ---
        lines += [
            "# HELP storyforge_pipeline_runs_total Total pipeline runs by genre and status.",
            "# TYPE storyforge_pipeline_runs_total counter",
        ]
        if pipeline_snapshot:
            for (genre, status), count in pipeline_snapshot.items():
                lines.append(
                    f'storyforge_pipeline_runs_total{{genre="{genre}",status="{status}"}} {count}'
                )
        else:
            lines.append("storyforge_pipeline_runs_total 0")

        # --- storyforge_active_sse_connections ---
        lines += [
            "# HELP storyforge_active_sse_connections Currently open SSE connections.",
            "# TYPE storyforge_active_sse_connections gauge",
            f"storyforge_active_sse_connections {sse_count}",
        ]

        # --- storyforge_uptime_seconds ---
        lines += [
            "# HELP storyforge_uptime_seconds Seconds since the application started.",
            "# TYPE storyforge_uptime_seconds gauge",
            f"storyforge_uptime_seconds {uptime:.3f}",
        ]

        return "\n".join(lines) + "\n"


# Module-level singleton
prometheus_metrics = PrometheusMetrics()
