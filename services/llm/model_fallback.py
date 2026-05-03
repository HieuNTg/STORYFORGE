"""Intelligent model fallback manager.

Selects the best available model based on health checks, latency thresholds,
and cost constraints. Falls back through configured fallback_models list.

Integrated with LLMClient for:
- Latency tracking per model
- Health status caching (30s TTL)
- Cost-based filtering
"""

import logging
import time
import threading
from typing import Optional

logger = logging.getLogger(__name__)

# Health cache TTL in seconds
_HEALTH_TTL_SECONDS = 30

# Singleton instance
_instance: Optional["ModelFallbackManager"] = None
_instance_lock = threading.Lock()


def get_fallback_manager(
    max_latency_ms: int = 120000, max_cost_per_1k: float = 0.01
) -> "ModelFallbackManager":
    """Get or create singleton ModelFallbackManager instance."""
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = ModelFallbackManager(max_latency_ms, max_cost_per_1k)
        return _instance


def reset_fallback_manager():
    """Reset singleton (for tests)."""
    global _instance
    with _instance_lock:
        _instance = None


class ModelFallbackManager:
    """Select the optimal model, falling back when primary is unhealthy or slow.

    Health checks are cached with a 30-second TTL to avoid hammering endpoints.
    Latency is tracked as a rolling average (last 10 samples).
    """

    def __init__(self, max_latency_ms: int = 120000, max_cost_per_1k: float = 0.01):
        self._max_latency_ms = max_latency_ms
        self._max_cost_per_1k = max_cost_per_1k
        self._lock = threading.Lock()

        # health cache: model_id -> {"healthy": bool, "checked_at": float}
        self._health_cache: dict[str, dict] = {}

        # latency rolling window: model_id -> list of float (ms)
        self._latency_samples: dict[str, list[float]] = {}
        self._latency_window = 10

        # consecutive failure counter — resets on mark_healthy. Surfaces in
        # /api/providers/health so CEO can see "model X has failed 3x in a row".
        self._failure_count: dict[str, int] = {}

        # most-recent error class per model — clears on mark_healthy
        self._last_error: dict[str, str] = {}

        # track why fallback was triggered
        self._last_fallback_reason: str = ""

    def update_thresholds(self, max_latency_ms: int = None, max_cost_per_1k: float = None):
        """Update thresholds dynamically (e.g., from config reload)."""
        with self._lock:
            if max_latency_ms is not None:
                self._max_latency_ms = max_latency_ms
            if max_cost_per_1k is not None:
                self._max_cost_per_1k = max_cost_per_1k

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def select_model(
        self,
        primary_model: str,
        fallback_models: list[dict],
        context: Optional[dict] = None,
    ) -> dict:
        """Choose the best model from primary + fallback list.

        Args:
            primary_model: primary model identifier string
            fallback_models: list of dicts with keys: model, base_url, api_key (optional),
                             cost_per_1k (optional float)
            context: optional dict with extra hints (e.g. {"required_tokens": 2000})

        Returns:
            dict with selected model info: {"model": str, "is_fallback": bool,
                                            "reason": str}
        """
        # Try primary first
        if self._is_model_acceptable(primary_model, context):
            return {"model": primary_model, "is_fallback": False, "reason": "primary_ok"}

        # Walk fallback list
        for idx, fb in enumerate(fallback_models):
            if not isinstance(fb, dict):
                logger.warning(
                    "Fallback config entry at index %d is not a dict (got %s); skipping.",
                    idx, type(fb).__name__,
                )
                continue
            fb_model = fb.get("model", "")
            if not fb_model:
                logger.warning(
                    "Fallback config entry at index %d is missing or has empty 'model' key; skipping.",
                    idx,
                )
                continue
            cost = fb.get("cost_per_1k", 0.0)
            if cost > self._max_cost_per_1k:
                logger.debug(f"Skipping {fb_model}: cost {cost} > threshold {self._max_cost_per_1k}")
                continue
            if self._is_model_acceptable(fb_model, context):
                reason = self._last_fallback_reason or "primary_unhealthy"
                logger.info(f"Falling back to {fb_model}: {reason}")
                return {"model": fb_model, "is_fallback": True, "reason": reason, **fb}

        # Nothing passed — return primary and hope for the best
        self._last_fallback_reason = "all_fallbacks_failed"
        logger.warning("All fallback models failed checks; returning primary as last resort")
        return {"model": primary_model, "is_fallback": False, "reason": "all_fallbacks_failed"}

    def record_latency(self, model: str, latency_ms: float) -> None:
        """Update rolling latency average for a model.

        Args:
            model: model identifier
            latency_ms: measured latency in milliseconds
        """
        with self._lock:
            samples = self._latency_samples.setdefault(model, [])
            samples.append(latency_ms)
            if len(samples) > self._latency_window:
                self._latency_samples[model] = samples[-self._latency_window:]
        logger.debug(f"Latency recorded: {model} = {latency_ms:.1f}ms (avg={self.get_avg_latency(model):.1f}ms)")

    def get_avg_latency(self, model: str) -> float:
        """Return rolling average latency for model in ms. Returns 0 if unknown."""
        with self._lock:
            samples = self._latency_samples.get(model, [])
        if not samples:
            return 0.0
        return sum(samples) / len(samples)

    def mark_unhealthy(self, model: str, error_class: str = "") -> None:
        """Explicitly mark a model as unhealthy (e.g. after a hard failure).

        ``error_class`` (optional) is the exception class name (e.g.
        "RateLimitError") surfaced via health_snapshot for the providers UI.
        """
        with self._lock:
            self._health_cache[model] = {
                "healthy": False,
                "checked_at": time.monotonic(),
            }
            self._failure_count[model] = self._failure_count.get(model, 0) + 1
            if error_class:
                self._last_error[model] = error_class
        logger.warning(f"Model marked unhealthy: {model}")

    def mark_healthy(self, model: str) -> None:
        """Explicitly mark a model as healthy."""
        with self._lock:
            self._health_cache[model] = {
                "healthy": True,
                "checked_at": time.monotonic(),
            }
            self._failure_count[model] = 0
            self._last_error.pop(model, None)

    def get_fallback_reason(self) -> str:
        """Return reason why fallback was triggered on last select_model call."""
        return self._last_fallback_reason

    def should_skip_model(self, model: str, cost_per_1k: float = 0.0) -> tuple[bool, str]:
        """Check if a model should be skipped in fallback chain.

        Returns: (should_skip, reason)
        """
        # Health check
        if not self._check_health(model):
            return True, f"unhealthy:{model}"

        # Latency check
        avg_lat = self.get_avg_latency(model)
        if avg_lat > 0 and avg_lat > self._max_latency_ms:
            return True, f"latency:{model}:{avg_lat:.0f}ms>{self._max_latency_ms}ms"

        # Cost check
        if cost_per_1k > 0 and cost_per_1k > self._max_cost_per_1k:
            return True, f"cost:{model}:{cost_per_1k}>${self._max_cost_per_1k}"

        return False, ""

    def clear_model_health(self, model: str):
        """Clear health cache for a model (force re-evaluation)."""
        with self._lock:
            self._health_cache.pop(model, None)

    def get_stats(self) -> dict:
        """Return current health/latency stats for debugging."""
        with self._lock:
            return {
                "health_cache": dict(self._health_cache),
                "latency_samples": {k: list(v) for k, v in self._latency_samples.items()},
                "max_latency_ms": self._max_latency_ms,
                "max_cost_per_1k": self._max_cost_per_1k,
            }

    def health_snapshot(self) -> list[dict]:
        """Return a per-model health snapshot for the providers UI.

        Lock is held only long enough to copy state out — JSON serialization
        happens after release. Each entry has the shape consumed by
        ``GET /api/providers/health``.
        """
        now = time.monotonic()
        with self._lock:
            health_cache = dict(self._health_cache)
            latency_samples = {k: list(v) for k, v in self._latency_samples.items()}
            failure_count = dict(self._failure_count)
            last_error = dict(self._last_error)

        # Union of every model we've seen in any structure
        models = set(health_cache) | set(latency_samples) | set(failure_count)
        out: list[dict] = []
        for model in sorted(models):
            entry = health_cache.get(model)
            samples = latency_samples.get(model, [])
            avg_latency = (sum(samples) / len(samples)) if samples else None
            if entry is not None:
                healthy = bool(entry["healthy"])
                age = now - entry["checked_at"]
                cooldown_remaining = max(0.0, _HEALTH_TTL_SECONDS - age) if not healthy else 0.0
            else:
                healthy = True  # never-checked models are optimistic
                cooldown_remaining = 0.0
            out.append({
                "model": model,
                "healthy": healthy,
                "last_latency_ms": int(samples[-1]) if samples else None,
                "avg_latency_ms": int(avg_latency) if avg_latency is not None else None,
                "consecutive_failures": failure_count.get(model, 0),
                "cooldown_remaining_s": int(cooldown_remaining),
                "last_error_class": last_error.get(model) or None,
            })
        return out

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _is_model_acceptable(self, model: str, context: Optional[dict]) -> bool:
        """Check health cache and latency threshold for a model."""
        # Health check (cached, 30s TTL)
        if not self._check_health(model):
            self._last_fallback_reason = f"unhealthy:{model}"
            return False

        # Latency check
        avg_lat = self.get_avg_latency(model)
        if avg_lat > 0 and avg_lat > self._max_latency_ms:
            self._last_fallback_reason = f"latency_exceeded:{model}:{avg_lat:.0f}ms"
            logger.debug(f"Model {model} avg latency {avg_lat:.0f}ms > threshold {self._max_latency_ms}ms")
            return False

        return True

    def _check_health(self, model: str) -> bool:
        """Return cached health status; assume healthy if never checked (optimistic)."""
        with self._lock:
            entry = self._health_cache.get(model)
        if entry is None:
            # Never checked — assume healthy (lazy evaluation)
            return True
        age = time.monotonic() - entry["checked_at"]
        if age > _HEALTH_TTL_SECONDS:
            # Cache expired — assume healthy until next explicit check
            return True
        return entry["healthy"]
