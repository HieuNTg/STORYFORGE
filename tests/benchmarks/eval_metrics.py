"""Statistics helpers and core evaluation logic for the benchmark runner.

Imported by eval_runner.py — not intended for direct CLI use.
"""

from __future__ import annotations

import math
from typing import Any

# Dimension mapping: golden dataset keys → quality scorer output keys
GOLDEN_TO_SCORER: dict[str, str] = {
    "coherence": "coherence",
    "character_depth": "character_consistency",
    "drama_intensity": "drama",
    "writing_quality": "writing_quality",
}
DIMENSIONS = list(GOLDEN_TO_SCORER.keys())

# Weights for overall score
_WEIGHTS = {"coherence": 0.3, "character_depth": 0.25, "drama_intensity": 0.25, "writing_quality": 0.2}


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

def pearson(xs: list[float], ys: list[float]) -> float:
    """Pearson correlation; returns 0.0 for degenerate input."""
    n = len(xs)
    if n < 2:
        return 0.0
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    denom = math.sqrt(sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys))
    return round(num / denom, 4) if denom else 0.0


def mae(xs: list[float], ys: list[float]) -> float:
    """Mean absolute error."""
    return round(sum(abs(x - y) for x, y in zip(xs, ys)) / len(xs), 4) if xs else 0.0


def mean_val(values: list[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


def bias(llm: list[float], human: list[float]) -> float:
    """Mean signed difference LLM − human. Positive = LLM over-scores."""
    diffs = [lv - h for lv, h in zip(llm, human)]
    return round(sum(diffs) / len(diffs), 4) if diffs else 0.0


def distribution(scores: list[float]) -> dict[str, int]:
    return {
        "low_1_2": sum(1 for s in scores if s <= 2.0),
        "mid_2_4": sum(1 for s in scores if 2.0 < s <= 4.0),
        "high_4_5": sum(1 for s in scores if s > 4.0),
    }


# ---------------------------------------------------------------------------
# Mock scorer
# ---------------------------------------------------------------------------

def mock_score(example: dict[str, Any]) -> dict[str, float]:
    """Deterministic pseudo-score: adds slight positive bias for test coverage."""
    h = example["human_scores"]
    return {
        "coherence": min(5.0, h["coherence"] + 0.3),
        "character_consistency": min(5.0, h["character_depth"] + 0.2),
        "drama": min(5.0, h["drama_intensity"] + 0.4),
        "writing_quality": min(5.0, h["writing_quality"] + 0.1),
    }


# ---------------------------------------------------------------------------
# Core evaluation
# ---------------------------------------------------------------------------

def evaluate(
    examples: list[dict[str, Any]],
    score_fn,  # Callable[[dict], dict[str, float]]
    mode_label: str = "mock",
) -> dict[str, Any]:
    """Run evaluation loop and compute all metrics.

    Args:
        examples: List of golden dataset dicts.
        score_fn: Function receiving an example dict, returning scorer output.
        mode_label: 'mock' or 'live', stored in report.

    Returns:
        Full metrics report dict.
    """
    llm_by_dim: dict[str, list[float]] = {d: [] for d in DIMENSIONS}
    human_by_dim: dict[str, list[float]] = {d: [] for d in DIMENSIONS}
    llm_overall: list[float] = []
    human_overall: list[float] = []
    per_example: list[dict[str, Any]] = []

    for ex in examples:
        scored = score_fn(ex)
        human = ex["human_scores"]
        ex_llm: dict[str, float] = {}
        ex_human: dict[str, float] = {}

        for gk, sk in GOLDEN_TO_SCORER.items():
            lv = float(scored.get(sk, 3.0))
            hv = float(human.get(gk, 3.0))
            llm_by_dim[gk].append(lv)
            human_by_dim[gk].append(hv)
            ex_llm[gk] = lv
            ex_human[gk] = hv

        lv_overall = sum(ex_llm[d] * w for d, w in _WEIGHTS.items())
        llm_overall.append(round(lv_overall, 4))
        human_overall.append(float(ex["human_overall"]))

        per_example.append({
            "id": ex["id"],
            "genre": ex["genre"],
            "llm_scores": ex_llm,
            "human_scores": {k: float(human[k]) for k in DIMENSIONS},
            "llm_overall": round(lv_overall, 4),
            "human_overall": float(ex["human_overall"]),
        })

    dim_metrics: dict[str, dict[str, float]] = {
        dim: {
            "pearson": pearson(llm_by_dim[dim], human_by_dim[dim]),
            "mae": mae(llm_by_dim[dim], human_by_dim[dim]),
            "bias": bias(llm_by_dim[dim], human_by_dim[dim]),
            "llm_mean": mean_val(llm_by_dim[dim]),
            "human_mean": mean_val(human_by_dim[dim]),
        }
        for dim in DIMENSIONS
    }

    return {
        "mode": mode_label,
        "n_examples": len(examples),
        "overall_metrics": {
            "pearson": pearson(llm_overall, human_overall),
            "mae": mae(llm_overall, human_overall),
            "bias": bias(llm_overall, human_overall),
            "llm_mean": mean_val(llm_overall),
            "human_mean": mean_val(human_overall),
        },
        "dimension_metrics": dim_metrics,
        "score_distributions": {
            "llm_overall": distribution(llm_overall),
            "human_overall": distribution(human_overall),
        },
        "bias_summary": {d: dim_metrics[d]["bias"] for d in DIMENSIONS},
        "per_example": per_example,
    }
