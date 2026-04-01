"""A/B testing — thread-safe in-memory experiment tracking."""

import hashlib
import time
import uuid
from collections import defaultdict
from threading import Lock
from typing import Dict, List


MAX_RESULTS = 1_000
MAX_EXPERIMENTS = 500


class ABTestManager:
    """Thread-safe in-memory A/B experiment manager."""

    def __init__(self) -> None:
        self._experiments: Dict[str, Dict] = {}
        self._results: Dict[str, List[Dict]] = {}
        self._lock = Lock()

    def create_experiment(self, name: str, variants: list) -> str:
        """Register a new experiment; returns experiment_id (uuid)."""
        if not variants:
            raise ValueError("variants must not be empty")
        experiment_id = str(uuid.uuid4())
        with self._lock:
            if len(self._experiments) >= MAX_EXPERIMENTS:
                raise ValueError(f"Experiment limit ({MAX_EXPERIMENTS}) reached")
            self._experiments[experiment_id] = {
                "id": experiment_id,
                "name": name,
                "variants": list(variants),
                "created_at": time.time(),
            }
            self._results[experiment_id] = []
        return experiment_id

    def assign_variant(self, experiment_id: str, session_id: str) -> str:
        """Deterministic variant assignment via hash(session_id + experiment_id)."""
        with self._lock:
            exp = self._experiments.get(experiment_id)
        if exp is None:
            raise KeyError(f"Experiment {experiment_id!r} not found")
        variants = exp["variants"]
        if not variants:
            raise ValueError("Experiment has no variants")
        digest = hashlib.sha256(f"{session_id}{experiment_id}".encode()).hexdigest()
        index = int(digest, 16) % len(variants)
        return variants[index]

    def record_result(
        self, experiment_id: str, session_id: str, metric: str, value: float
    ) -> None:
        """Append an outcome; enforces MAX_RESULTS cap (FIFO)."""
        with self._lock:
            if experiment_id not in self._results:
                raise KeyError(f"Experiment {experiment_id!r} not found")
            self._results[experiment_id].append(
                {
                    "session_id": session_id,
                    "metric": metric,
                    "value": value,
                    "timestamp": time.time(),
                }
            )
            if len(self._results[experiment_id]) > MAX_RESULTS:
                self._results[experiment_id] = self._results[experiment_id][-MAX_RESULTS:]

    def get_results(self, experiment_id: str) -> Dict:
        """Return per-variant aggregation {variant: {count, metric_sum, metric_avg}}."""
        with self._lock:
            exp = self._experiments.get(experiment_id)
            if exp is None:
                raise KeyError(f"Experiment {experiment_id!r} not found")
            snapshot = list(self._results[experiment_id])
            variants = exp["variants"]

        agg: Dict[str, Dict] = {v: {"count": 0, "metric_sum": 0.0} for v in variants}
        for rec in snapshot:
            variant = self.assign_variant(experiment_id, rec["session_id"])
            agg[variant]["count"] += 1
            agg[variant]["metric_sum"] += rec["value"]

        result = {}
        for variant, data in agg.items():
            count = data["count"]
            result[variant] = {
                "count": count,
                "metric_sum": data["metric_sum"],
                "metric_avg": data["metric_sum"] / count if count > 0 else None,
            }
        return result

    def list_experiments(self) -> List[Dict]:
        """Return all experiments with metadata."""
        with self._lock:
            return list(self._experiments.values())


# Module-level singleton
manager = ABTestManager()
