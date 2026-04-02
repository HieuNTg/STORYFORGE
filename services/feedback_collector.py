"""Human feedback collection service for StoryForge quality improvement.

Stores per-chapter user ratings as JSON files under data/feedback/.
Thread-safe singleton — import `collector` for application use.
Rating dimensions mirror the LLM quality scorer for direct comparison.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from threading import Lock
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class RatingScores(BaseModel):
    """Per-dimension scores 1–5, mirroring quality scorer dimensions."""
    coherence: float = Field(..., ge=1, le=5)
    character: float = Field(..., ge=1, le=5)
    drama: float = Field(..., ge=1, le=5)
    writing: float = Field(..., ge=1, le=5)


class FeedbackEntry(BaseModel):
    """A single user rating record persisted to disk."""
    feedback_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    story_id: str
    chapter_index: int
    user_id: str
    scores: RatingScores
    overall: float
    comment: str = ""
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------

def _story_file(data_dir: Path, story_id: str) -> Path:
    safe = story_id.replace("/", "_").replace("\\", "_")[:64]
    return data_dir / f"{safe}.json"


def _load(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def _save(path: Path, records: list[dict[str, Any]]) -> None:
    path.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# Collector
# ---------------------------------------------------------------------------

_DEFAULT_DIR = Path(os.environ.get("STORYFORGE_FEEDBACK_DIR", "data/feedback"))


class FeedbackCollector:
    """Thread-safe service for collecting and querying story chapter ratings."""

    def __init__(self, data_dir: Path = _DEFAULT_DIR) -> None:
        self._dir = Path(data_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    def submit_rating(
        self,
        story_id: str,
        chapter_idx: int,
        user_id: str,
        scores: dict[str, float],
        comment: str = "",
    ) -> FeedbackEntry:
        """Persist a user rating for a specific chapter.

        Args:
            story_id: Unique story identifier.
            chapter_idx: Zero-based chapter index.
            user_id: Submitting user ID.
            scores: Dict with coherence, character, drama, writing (1–5).
            comment: Optional free-text annotation.
        """
        rs = RatingScores(**scores)
        entry = FeedbackEntry(
            story_id=story_id,
            chapter_index=chapter_idx,
            user_id=user_id,
            scores=rs,
            overall=round(mean([rs.coherence, rs.character, rs.drama, rs.writing]), 4),
            comment=comment,
        )
        with self._lock:
            path = _story_file(self._dir, story_id)
            records = _load(path)
            records.append(entry.model_dump())
            _save(path, records)
        return entry

    def get_story_ratings(self, story_id: str) -> list[FeedbackEntry]:
        """Return all ratings for a story sorted by chapter index then timestamp."""
        with self._lock:
            records = _load(_story_file(self._dir, story_id))
        return sorted(
            [FeedbackEntry(**r) for r in records],
            key=lambda e: (e.chapter_index, e.timestamp),
        )

    def get_aggregate_stats(self) -> dict[str, Any]:
        """Compute aggregate statistics across all stored feedback files."""
        with self._lock:
            all_files = list(self._dir.glob("*.json"))

        all_entries: list[FeedbackEntry] = []
        per_story: dict[str, int] = {}
        for fp in all_files:
            with self._lock:
                records = _load(fp)
            entries = [FeedbackEntry(**r) for r in records]
            all_entries.extend(entries)
            if entries:
                per_story[entries[0].story_id] = len(entries)

        if not all_entries:
            return {
                "total_ratings": 0, "avg_overall": 0.0,
                "avg_coherence": 0.0, "avg_character": 0.0,
                "avg_drama": 0.0, "avg_writing": 0.0,
                "score_distribution": {str(i): 0 for i in range(1, 6)},
                "per_story_count": {},
            }

        overalls = [e.overall for e in all_entries]
        dist = {str(i): 0 for i in range(1, 6)}
        for o in overalls:
            dist[str(min(5, max(1, round(o))))] += 1

        return {
            "total_ratings": len(all_entries),
            "avg_overall": round(mean(overalls), 4),
            "avg_coherence": round(mean(e.scores.coherence for e in all_entries), 4),
            "avg_character": round(mean(e.scores.character for e in all_entries), 4),
            "avg_drama": round(mean(e.scores.drama for e in all_entries), 4),
            "avg_writing": round(mean(e.scores.writing for e in all_entries), 4),
            "score_distribution": dist,
            "per_story_count": per_story,
        }

    def export_for_benchmark(self) -> list[dict[str, Any]]:
        """Format all feedback as benchmark-compatible records.

        Output keys match golden_dataset structure so feedback can feed
        directly into eval_runner for ongoing calibration.
        """
        with self._lock:
            all_files = list(self._dir.glob("*.json"))
        results: list[dict[str, Any]] = []
        for fp in all_files:
            with self._lock:
                records = _load(fp)
            for r in records:
                e = FeedbackEntry(**r)
                results.append({
                    "id": e.feedback_id,
                    "story_id": e.story_id,
                    "chapter_index": e.chapter_index,
                    "user_id": e.user_id,
                    "human_scores": {
                        "coherence": e.scores.coherence,
                        "character_depth": e.scores.character,
                        "drama_intensity": e.scores.drama,
                        "writing_quality": e.scores.writing,
                    },
                    "human_overall": e.overall,
                    "comment": e.comment,
                    "timestamp": e.timestamp,
                })
        return results


# Module-level singleton
collector = FeedbackCollector()
