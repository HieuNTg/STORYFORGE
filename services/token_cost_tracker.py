"""Token Cost Tracker — tracks LLM token usage and estimates costs per call.

Aggregates by story_id, pipeline layer (1/2/3), agent_name, and model_name.
Stores records in-memory with optional JSON persistence.

API endpoint concept (how this would be routed in api/metrics_routes.py):
    # GET  /api/v1/stories/<story_id>/token-cost  -> get_story_cost(story_id)
    # GET  /api/v1/token-cost/session             -> get_session_summary()
    # POST /api/v1/token-cost/reset               -> reset_session()
"""

import json
import logging
import os
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default pricing table (USD per 1 000 tokens)
# Sources: official provider pricing pages as of 2026-Q1.
# Override via STORYFORGE_TOKEN_PRICING env var (JSON string) or at runtime.
# ---------------------------------------------------------------------------
DEFAULT_PRICING: dict[str, dict[str, float]] = {
    # OpenAI
    "gpt-4o-mini":         {"prompt": 0.000150, "completion": 0.000600},
    "gpt-4o":              {"prompt": 0.002500, "completion": 0.010000},
    "gpt-4-turbo":         {"prompt": 0.010000, "completion": 0.030000},
    # Google
    "gemini-1.5-flash":    {"prompt": 0.000075, "completion": 0.000300},
    "gemini-1.5-pro":      {"prompt": 0.001250, "completion": 0.005000},
    "gemini-2.0-flash":    {"prompt": 0.000100, "completion": 0.000400},
    # Anthropic
    "claude-3-haiku":      {"prompt": 0.000250, "completion": 0.001250},
    "claude-3-5-sonnet":   {"prompt": 0.003000, "completion": 0.015000},
    "claude-3-5-haiku":    {"prompt": 0.000800, "completion": 0.004000},
    # DeepSeek
    "deepseek-chat":       {"prompt": 0.000140, "completion": 0.000280},
    "deepseek-reasoner":   {"prompt": 0.000550, "completion": 0.002190},
    # Fallback for unknown models (very rough average)
    "_default":            {"prompt": 0.001000, "completion": 0.002000},
}

# Legacy aliases so callers using old model names still get sensible pricing
_MODEL_ALIASES: dict[str, str] = {
    "claude-3.5-sonnet": "claude-3-5-sonnet",
    "claude-3.5-haiku":  "claude-3-5-haiku",
}


@dataclass
class UsageRecord:
    """Single LLM call record."""
    story_id: str
    layer: int          # 1 = story gen, 2 = drama/enhance
    agent_name: str
    model_name: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class StoryCostSummary:
    story_id: str
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    by_layer: dict = field(default_factory=dict)   # layer -> {tokens, cost}
    by_agent: dict = field(default_factory=dict)   # agent_name -> {tokens, cost}
    by_model: dict = field(default_factory=dict)   # model_name -> {tokens, cost}
    call_count: int = 0


class TokenCostTracker:
    """Singleton token cost tracker.

    Usage:
        tracker = TokenCostTracker()
        tracker.track_usage("story-42", layer=1, agent="Editor", model="gpt-4o-mini",
                            prompt_tokens=500, completion_tokens=250)
        print(tracker.get_story_cost("story-42"))
        print(tracker.get_session_summary())
    """

    _instance: Optional["TokenCostTracker"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "TokenCostTracker":
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset singleton — useful in tests."""
        with cls._lock:
            cls._instance = None

    def __init__(self) -> None:
        if self._initialized:  # type: ignore[has-type]
            return
        self._initialized = True
        self._records: list[UsageRecord] = []
        self._record_lock = threading.Lock()

        # Pricing table: merge defaults with any env override
        self._pricing: dict[str, dict[str, float]] = dict(DEFAULT_PRICING)
        env_pricing = os.environ.get("STORYFORGE_TOKEN_PRICING")
        if env_pricing:
            try:
                overrides = json.loads(env_pricing)
                self._pricing.update(overrides)
                logger.info("TokenCostTracker: loaded custom pricing from env (%d models)", len(overrides))
            except json.JSONDecodeError as exc:
                logger.warning("TokenCostTracker: invalid STORYFORGE_TOKEN_PRICING JSON — %s", exc)

        # Optional persistence path
        self._persist_path: Optional[str] = os.environ.get("STORYFORGE_COST_LOG")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def track_usage(
        self,
        story_id: str,
        layer: int,
        agent: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> UsageRecord:
        """Record a single LLM call and return the UsageRecord.

        Args:
            story_id:          Identifier for the story being generated.
            layer:             Pipeline layer (1, 2, or 3).
            agent:             Agent/component name that made the call.
            model:             Model identifier string (e.g. "gpt-4o-mini").
            prompt_tokens:     Number of prompt/input tokens consumed.
            completion_tokens: Number of completion/output tokens generated.

        Returns:
            UsageRecord with computed cost_usd populated.
        """
        total = prompt_tokens + completion_tokens
        cost = self._compute_cost(model, prompt_tokens, completion_tokens)
        record = UsageRecord(
            story_id=story_id,
            layer=layer,
            agent_name=agent,
            model_name=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total,
            cost_usd=cost,
        )
        with self._record_lock:
            self._records.append(record)

        if self._persist_path:
            self._append_to_file(record)

        logger.debug(
            "TokenCostTracker: story=%s layer=%d agent=%s model=%s "
            "tokens=%d cost=$%.6f",
            story_id, layer, agent, model, total, cost,
        )
        return record

    def get_story_cost(self, story_id: str) -> StoryCostSummary:
        """Return aggregated cost breakdown for a single story.

        Returns a StoryCostSummary with totals and per-layer/agent/model
        breakdowns.  All values are zero if the story_id has no records.
        """
        with self._record_lock:
            records = [r for r in self._records if r.story_id == story_id]

        summary = StoryCostSummary(story_id=story_id)
        for rec in records:
            summary.total_prompt_tokens += rec.prompt_tokens
            summary.total_completion_tokens += rec.completion_tokens
            summary.total_tokens += rec.total_tokens
            summary.total_cost_usd += rec.cost_usd
            summary.call_count += 1

            layer_key = str(rec.layer)
            _accum(summary.by_layer, layer_key, rec.total_tokens, rec.cost_usd)
            _accum(summary.by_agent, rec.agent_name, rec.total_tokens, rec.cost_usd)
            _accum(summary.by_model, rec.model_name, rec.total_tokens, rec.cost_usd)

        return summary

    def get_session_summary(self) -> dict:
        """Return aggregated stats across the entire in-memory session.

        Returns a plain dict suitable for JSON serialisation.
        """
        with self._record_lock:
            records = list(self._records)

        total_prompt = sum(r.prompt_tokens for r in records)
        total_completion = sum(r.completion_tokens for r in records)
        total_tokens = sum(r.total_tokens for r in records)
        total_cost = sum(r.cost_usd for r in records)

        by_story: dict[str, dict] = {}
        by_model: dict[str, dict] = {}

        for rec in records:
            _accum(by_story, rec.story_id, rec.total_tokens, rec.cost_usd)
            _accum(by_model, rec.model_name, rec.total_tokens, rec.cost_usd)

        return {
            "call_count": len(records),
            "total_prompt_tokens": total_prompt,
            "total_completion_tokens": total_completion,
            "total_tokens": total_tokens,
            "total_cost_usd": round(total_cost, 6),
            "by_story": by_story,
            "by_model": by_model,
        }

    def reset_session(self) -> None:
        """Clear all in-memory records (does not touch the persist file)."""
        with self._record_lock:
            self._records.clear()
        logger.info("TokenCostTracker: session reset")

    def update_pricing(self, pricing: dict[str, dict[str, float]]) -> None:
        """Update pricing table at runtime.

        Args:
            pricing: Mapping of model_name -> {"prompt": float, "completion": float}
                     where values are USD per 1 000 tokens.
        """
        self._pricing.update(pricing)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _compute_cost(self, model: str, prompt_tokens: int, completion_tokens: int) -> float:
        """Return estimated cost in USD for a single call."""
        # Resolve alias (e.g. "claude-3.5-sonnet" -> "claude-3-5-sonnet")
        canonical = _MODEL_ALIASES.get(model, model)

        # Exact match first, then try prefix match (handles version suffixes)
        rates = self._pricing.get(canonical)
        if rates is None:
            for key in self._pricing:
                if key != "_default" and canonical.startswith(key):
                    rates = self._pricing[key]
                    break
        if rates is None:
            rates = self._pricing["_default"]
            logger.debug("TokenCostTracker: unknown model '%s', using _default pricing", model)

        cost = (prompt_tokens * rates["prompt"] + completion_tokens * rates["completion"]) / 1000.0
        return round(cost, 8)

    def _append_to_file(self, record: UsageRecord) -> None:
        """Append a single record as a JSON line to the persist file."""
        try:
            os.makedirs(os.path.dirname(self._persist_path) or ".", exist_ok=True)
            with open(self._persist_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(asdict(record)) + "\n")
        except OSError as exc:
            logger.warning("TokenCostTracker: failed to write persist file — %s", exc)


# ---------------------------------------------------------------------------
# Module-level convenience helpers
# ---------------------------------------------------------------------------

def _accum(mapping: dict, key: str, tokens: int, cost: float) -> None:
    """Accumulate tokens and cost into a dict bucket."""
    if key not in mapping:
        mapping[key] = {"tokens": 0, "cost_usd": 0.0}
    mapping[key]["tokens"] += tokens
    mapping[key]["cost_usd"] = round(mapping[key]["cost_usd"] + cost, 8)
