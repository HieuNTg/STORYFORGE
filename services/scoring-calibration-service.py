"""Scoring calibration service — bridges feedback_collector → calibration utils → quality_scorer.

Reads human feedback, fits per-genre linear calibration curves, persists params to
data/calibration_params.json, and exposes calibrate() / apply() for runtime use.
Genre-specific calibration is stored under the genre key so drift is isolated per genre.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Calibration utilities (tests/benchmarks lives on sys.path in the project)
from tests.benchmarks.scoring_calibration import (
    calculate_bias,
    create_calibration_map,
    apply_calibration,
    export_calibration_params,
    load_calibration_params,
    CalibrationMap,
)
from services.feedback_collector import FeedbackCollector

logger = logging.getLogger(__name__)

# Score dimensions shared between feedback_collector and quality_scorer
_DIMENSIONS = ("coherence", "character", "drama", "writing")

# Mapping: feedback_collector field name → quality_scorer field name (for LLM scores)
_FEEDBACK_TO_LLM: dict[str, str] = {
    "coherence": "coherence",
    "character": "character_depth",
    "drama": "drama_intensity",
    "writing": "writing_quality",
}

_DEFAULT_PARAMS_PATH = Path("data/calibration_params.json")


class ScoringCalibrationService:
    """Fit and apply per-genre LLM score calibration from human feedback.

    Usage:
        svc = ScoringCalibrationService()
        svc.calibrate()                         # fit curves from all feedback
        adjusted = svc.apply(raw_scores, genre) # adjust a score dict at runtime
    """

    def __init__(
        self,
        params_path: Path = _DEFAULT_PARAMS_PATH,
        feedback_collector: FeedbackCollector | None = None,
    ) -> None:
        self._path = Path(params_path)
        self._collector = feedback_collector or FeedbackCollector()
        # {genre: CalibrationMap}  — loaded lazily
        self._genre_maps: dict[str, CalibrationMap] = {}
        self._load_existing_params()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def calibrate(self) -> dict[str, Any]:
        """Rebuild calibration maps from all stored human feedback.

        Returns a summary dict with per-genre bias and MAE stats.
        """
        records = self._collector.export_for_benchmark()
        if not records:
            logger.warning("calibrate(): no feedback records found — skipping")
            return {"status": "no_data", "genres": {}}

        # Group records by genre (genre not in feedback → "unknown")
        by_genre: dict[str, list[dict]] = {}
        for rec in records:
            genre = rec.get("genre", "unknown")
            by_genre.setdefault(genre, []).append(rec)

        summary: dict[str, Any] = {"status": "ok", "genres": {}}
        all_maps: dict[str, CalibrationMap] = {}

        for genre, recs in by_genre.items():
            genre_map, genre_stats = self._fit_genre(genre, recs)
            if genre_map:
                all_maps[genre] = genre_map
                summary["genres"][genre] = genre_stats

        # Persist and cache
        self._genre_maps = all_maps
        self._persist(all_maps)
        logger.info(
            "calibrate(): fitted %d genre(s) from %d records",
            len(all_maps),
            len(records),
        )
        return summary

    def apply(self, raw_scores: dict[str, float], genre: str = "unknown") -> dict[str, float]:
        """Apply genre calibration to a raw score dict from quality_scorer.

        Keys expected: coherence, character_consistency, drama, writing_quality.
        Returns same keys with calibrated values; logs per-dimension deltas.
        """
        # Pick best-matching calibration map (genre → "unknown" → None)
        cal_map = self._genre_maps.get(genre) or self._genre_maps.get("unknown")
        if not cal_map:
            return raw_scores  # no calibration available, return as-is

        # Dimension name mapping from quality_scorer → calibration_map key space
        _qs_to_dim = {
            "coherence": "coherence",
            "character_consistency": "character",
            "drama": "drama",
            "writing_quality": "writing",
        }

        adjusted: dict[str, float] = {}
        for qs_key, value in raw_scores.items():
            dim = _qs_to_dim.get(qs_key, qs_key)
            new_value = apply_calibration(value, cal_map, dim)
            adjusted[qs_key] = new_value
            delta = new_value - value
            if abs(delta) > 0.01:
                logger.debug(
                    "calibrate delta [genre=%s, dim=%s]: %.3f → %.3f (Δ%+.3f)",
                    genre, dim, value, new_value, delta,
                )
        return adjusted

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fit_genre(
        self, genre: str, records: list[dict]
    ) -> tuple[CalibrationMap, dict[str, Any]]:
        """Fit a CalibrationMap for one genre from its feedback records."""
        # Collect paired LLM vs human scores per dimension
        llm_scores: dict[str, list[float]] = {d: [] for d in _DIMENSIONS}
        human_scores: dict[str, list[float]] = {d: [] for d in _DIMENSIONS}

        for rec in records:
            hs = rec.get("human_scores", {})
            ls = rec.get("llm_scores", {})  # optional; may not be present
            if not hs or not ls:
                continue
            for dim in _DIMENSIONS:
                h_key = _FEEDBACK_TO_LLM[dim]
                l_key = _FEEDBACK_TO_LLM[dim]
                if h_key in hs and l_key in ls:
                    human_scores[dim].append(float(hs[h_key]))
                    llm_scores[dim].append(float(ls[l_key]))

        # Need at least 2 paired points per dimension for OLS
        usable = {d for d in _DIMENSIONS if len(llm_scores[d]) >= 2}
        if not usable:
            return {}, {"skipped": "insufficient_paired_data", "n": len(records)}

        filtered_llm = {d: llm_scores[d] for d in usable}
        filtered_human = {d: human_scores[d] for d in usable}

        cal_map = create_calibration_map(filtered_llm, filtered_human)
        bias_stats = {
            d: calculate_bias(filtered_llm[d], filtered_human[d]) for d in usable
        }
        return cal_map, {"n": len(records), "dimensions": list(usable), "bias": bias_stats}

    def _persist(self, maps: dict[str, CalibrationMap]) -> None:
        """Write all genre calibration maps to disk."""
        metadata = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "genres": list(maps.keys()),
        }
        export_calibration_params(maps, self._path, metadata=metadata)
        logger.info("calibration params persisted to %s", self._path)

    def _load_existing_params(self) -> None:
        """Load previously persisted calibration params on startup."""
        if not self._path.exists():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            # export_calibration_params wraps in {"calibration": ..., "metadata": ...}
            cal = raw.get("calibration", raw)
            self._genre_maps = cal
            logger.info("loaded calibration params from %s (%d genres)", self._path, len(cal))
        except Exception as exc:
            logger.warning("failed to load calibration params: %s", exc)


# Module-level singleton
calibration_service = ScoringCalibrationService()
