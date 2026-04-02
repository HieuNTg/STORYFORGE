"""Evaluation pipeline — automated + human eval for story quality.

Auto metrics (40%) combined with human evaluator scores (60%) to produce
aggregate quality reports per story.
"""

import json
import logging
import os
import re
import statistics
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

_EVALS_DIR = "data/evals"

# Vietnamese unicode ranges: Basic Latin + Vietnamese extended blocks
# U+00C0-U+024F (Latin Extended), U+1E00-U+1EFF (Latin Extended Additional)
# Vietnamese uses many codepoints in U+1EA0-U+1EF9
_VIET_PATTERN = re.compile(
    r"[\u00C0-\u024F\u1E00-\u1EFF\u0300-\u036F]|"
    r"[àáâãèéêìíòóôõùúýăđơưạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ"
    r"ÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚÝĂĐƠƯẠẢẤẦẨẪẬẮẰẲẴẶẸẺẼẾỀỂỄỆỈỊỌỎỐỒỔỖỘỚỜỞỠỢỤỦỨỪỬỮỰỲỴỶỸ]",
    re.UNICODE,
)


class EvalPipeline:
    """Compute automated + human evaluation metrics for stories."""

    def __init__(self, evals_dir: str = _EVALS_DIR):
        self._evals_dir = evals_dir
        os.makedirs(self._evals_dir, exist_ok=True)
        # In-memory eval store: story_id -> list of human eval dicts
        self._human_evals: dict[str, list[dict]] = {}

    # ------------------------------------------------------------------
    # Automated metrics
    # ------------------------------------------------------------------

    def auto_score(self, story_data: dict) -> dict:
        """Compute automated metrics from story data.

        Args:
            story_data: dict with keys:
                - chapters: list of {"title": str, "content": str, "characters": list[str]}
                - character_names: list of expected character names (optional)

        Returns:
            dict with keys: character_name_consistency, chapter_length_variance,
                            language_purity, auto_score_overall
        """
        chapters = story_data.get("chapters", [])
        char_names = story_data.get("character_names", [])

        consistency = self._character_name_consistency(chapters, char_names)
        variance = self._chapter_length_variance(chapters)
        purity = self._language_purity(chapters)

        # Normalize to 0-1 scale
        # consistency: already 0-1
        # variance: lower is better; cap at 2000 words std dev → score = 1 - min(std/2000, 1)
        variance_score = max(0.0, 1.0 - min(variance / 2000.0, 1.0)) if variance >= 0 else 0.0
        # purity: already 0-1

        overall = (consistency + variance_score + purity) / 3.0

        return {
            "character_name_consistency": round(consistency, 4),
            "chapter_length_variance_std": round(variance, 2),
            "chapter_length_variance_score": round(variance_score, 4),
            "language_purity": round(purity, 4),
            "auto_score_overall": round(overall, 4),
        }

    def _character_name_consistency(self, chapters: list[dict], char_names: list[str]) -> float:
        """Check that each named character appears at least once across all chapters.

        Returns ratio of names that appear in the combined text (0-1).
        """
        if not char_names or not chapters:
            return 1.0  # No names to check → perfect

        combined = " ".join(ch.get("content", "") for ch in chapters)
        found = sum(
            1 for name in char_names
            if re.search(re.escape(name), combined, re.IGNORECASE)
        )
        return found / len(char_names)

    def _chapter_length_variance(self, chapters: list[dict]) -> float:
        """Compute standard deviation of chapter word counts.

        Returns std dev in words (lower = more consistent).
        """
        if len(chapters) < 2:
            return 0.0
        lengths = [len(ch.get("content", "").split()) for ch in chapters]
        try:
            return statistics.stdev(lengths)
        except statistics.StatisticsError:
            return 0.0

    def _language_purity(self, chapters: list[dict]) -> float:
        """Estimate percentage of Vietnamese characters in content.

        Uses unicode ranges for Vietnamese diacritics and extended Latin.
        Returns 0-1 fraction of chars that are Vietnamese/accented.
        """
        if not chapters:
            return 0.0

        total_chars = 0
        viet_chars = 0
        for ch in chapters:
            content = ch.get("content", "")
            # Only count alpha chars
            alpha = [c for c in content if c.isalpha()]
            total_chars += len(alpha)
            viet_chars += len(_VIET_PATTERN.findall(content))

        if total_chars == 0:
            return 0.0
        return min(1.0, viet_chars / total_chars)

    # ------------------------------------------------------------------
    # Human evaluation
    # ------------------------------------------------------------------

    def submit_human_eval(
        self,
        story_id: str,
        evaluator_id: str,
        scores_dict: dict,
        persist: bool = True,
    ) -> dict:
        """Store a human evaluation for a story.

        Args:
            story_id: identifier of the story
            evaluator_id: who submitted the eval
            scores_dict: dict of metric_name -> float (expected 0-5 scale)
            persist: whether to write to JSON file

        Returns:
            The saved eval record.
        """
        record = {
            "story_id": story_id,
            "evaluator_id": evaluator_id,
            "scores": scores_dict,
            "submitted_at": datetime.now(timezone.utc).isoformat(),
        }
        self._human_evals.setdefault(story_id, []).append(record)

        if persist:
            self._persist_eval(story_id, record)

        logger.info(f"Human eval stored: story={story_id} evaluator={evaluator_id}")
        return record

    def _persist_eval(self, story_id: str, record: dict) -> None:
        path = os.path.join(self._evals_dir, f"{story_id}.json")
        existing: list[dict] = []
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except (json.JSONDecodeError, OSError):
                existing = []
        existing.append(record)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)

    def _load_human_evals(self, story_id: str) -> list[dict]:
        """Return in-memory evals, falling back to disk if empty."""
        if story_id in self._human_evals and self._human_evals[story_id]:
            return self._human_evals[story_id]
        path = os.path.join(self._evals_dir, f"{story_id}.json")
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._human_evals[story_id] = data
                    return data
            except (json.JSONDecodeError, OSError):
                pass
        return []

    # ------------------------------------------------------------------
    # Aggregation
    # ------------------------------------------------------------------

    def get_aggregate_score(
        self,
        story_id: str,
        auto_metrics: Optional[dict] = None,
    ) -> dict:
        """Combine auto (40%) + human (60%) scores.

        Args:
            story_id: story to aggregate
            auto_metrics: pre-computed auto_score dict (optional; uses 0 if absent)

        Returns:
            dict with auto_score, human_score, aggregate_score, human_eval_count
        """
        auto_overall = 0.0
        if auto_metrics:
            auto_overall = float(auto_metrics.get("auto_score_overall", 0.0))

        evals = self._load_human_evals(story_id)
        human_score = 0.0
        if evals:
            # Average of all evaluator overall scores (normalize 0-5 → 0-1 if needed)
            flat_scores = []
            for ev in evals:
                scores = ev.get("scores", {})
                if scores:
                    vals = list(scores.values())
                    avg = sum(vals) / len(vals)
                    # If scale is 0-5, normalize to 0-1
                    if avg > 1.0:
                        avg = avg / 5.0
                    flat_scores.append(avg)
            if flat_scores:
                human_score = sum(flat_scores) / len(flat_scores)

        aggregate = auto_overall * 0.4 + human_score * 0.6

        return {
            "story_id": story_id,
            "auto_score": round(auto_overall, 4),
            "human_score": round(human_score, 4),
            "aggregate_score": round(aggregate, 4),
            "human_eval_count": len(evals),
            "weight_auto": 0.4,
            "weight_human": 0.6,
        }

    def generate_report(
        self,
        story_id: str,
        story_data: Optional[dict] = None,
    ) -> dict:
        """Generate a full evaluation report for a story.

        Args:
            story_id: story identifier
            story_data: raw story dict for auto-scoring (optional)

        Returns:
            dict with all metrics, scores, timestamp.
        """
        auto_metrics = self.auto_score(story_data) if story_data else {}
        aggregate = self.get_aggregate_score(story_id, auto_metrics)
        evals = self._load_human_evals(story_id)

        return {
            "story_id": story_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "auto_metrics": auto_metrics,
            "human_evals": evals,
            "aggregate": aggregate,
        }
