"""Scoring calibration utilities for the LLM-as-judge quality scorer.

Detects systematic bias, fits per-dimension linear calibration maps,
applies adjustments, and evaluates improvement in MAE.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

# {dimension: {slope, intercept, r_squared}}
CalibrationMap = dict[str, dict[str, float]]


def calculate_bias(
    llm_scores: list[float],
    human_scores: list[float],
) -> dict[str, float]:
    """Detect systematic bias between LLM and human scores.

    Returns mean_bias, std_bias, over_count, under_count, exact_count.
    Positive mean_bias means LLM systematically over-scores.
    """
    if len(llm_scores) != len(human_scores):
        raise ValueError("llm_scores and human_scores must have the same length")
    if not llm_scores:
        return {"mean_bias": 0.0, "std_bias": 0.0,
                "over_count": 0, "under_count": 0, "exact_count": 0}

    diffs = [l - h for l, h in zip(llm_scores, human_scores)]
    mean_bias = sum(diffs) / len(diffs)
    std_bias = math.sqrt(sum((d - mean_bias) ** 2 for d in diffs) / len(diffs))
    return {
        "mean_bias": round(mean_bias, 4),
        "std_bias": round(std_bias, 4),
        "over_count": sum(1 for d in diffs if d > 0.1),
        "under_count": sum(1 for d in diffs if d < -0.1),
        "exact_count": sum(1 for d in diffs if abs(d) <= 0.1),
    }


def create_calibration_map(
    llm_scores: dict[str, list[float]],
    human_scores: dict[str, list[float]],
) -> CalibrationMap:
    """Fit per-dimension OLS linear regression: human = slope * llm + intercept.

    Args:
        llm_scores: {dimension: [scores]} for scored examples.
        human_scores: {dimension: [scores]} matching llm_scores.

    Returns:
        CalibrationMap with slope, intercept, r_squared per dimension.
    """
    calibration: CalibrationMap = {}
    for dim in llm_scores:
        if dim not in human_scores:
            continue
        xs, ys = llm_scores[dim], human_scores[dim]
        n = len(xs)
        if n < 2:
            calibration[dim] = {"slope": 1.0, "intercept": 0.0, "r_squared": 0.0}
            continue
        mx, my = sum(xs) / n, sum(ys) / n
        ss_xy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
        ss_xx = sum((x - mx) ** 2 for x in xs)
        ss_yy = sum((y - my) ** 2 for y in ys)
        slope = ss_xy / ss_xx if ss_xx else 1.0
        intercept = my - slope * mx
        r_sq = (ss_xy ** 2 / (ss_xx * ss_yy)) if (ss_xx * ss_yy) else 0.0
        calibration[dim] = {
            "slope": round(slope, 6),
            "intercept": round(intercept, 6),
            "r_squared": round(r_sq, 6),
        }
    return calibration


def apply_calibration(
    raw_score: float,
    calibration_map: CalibrationMap,
    dimension: str,
    clamp_min: float = 1.0,
    clamp_max: float = 5.0,
) -> float:
    """Apply linear calibration to a raw LLM score and clamp to [1, 5]."""
    if dimension not in calibration_map:
        return raw_score
    p = calibration_map[dimension]
    return round(max(clamp_min, min(clamp_max, p["slope"] * raw_score + p["intercept"])), 4)


def evaluate_calibration(
    before_llm: list[float],
    after_llm: list[float],
    human: list[float],
) -> dict[str, float]:
    """Compare MAE before and after calibration.

    Returns mae_before, mae_after, improvement, improvement_pct.
    """
    def _mae(pred: list[float], truth: list[float]) -> float:
        return sum(abs(p - t) for p, t in zip(pred, truth)) / len(pred) if pred else 0.0

    mb = _mae(before_llm, human)
    ma = _mae(after_llm, human)
    imp = mb - ma
    return {
        "mae_before": round(mb, 4),
        "mae_after": round(ma, 4),
        "improvement": round(imp, 4),
        "improvement_pct": round(imp / mb * 100.0, 2) if mb > 0 else 0.0,
    }


def export_calibration_params(
    calibration_map: CalibrationMap,
    out_path: str | Path,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Serialize calibration parameters to JSON."""
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"calibration": calibration_map, "metadata": metadata or {}},
                  f, indent=2, ensure_ascii=False)


def load_calibration_params(path: str | Path) -> CalibrationMap:
    """Load calibration parameters from a JSON file."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)["calibration"]
