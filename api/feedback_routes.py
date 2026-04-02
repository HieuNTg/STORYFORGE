"""Feedback API routes — collect and query user ratings for story chapters.

Prefix: /api/feedback
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.feedback_collector import FeedbackEntry, RatingScores, collector

router = APIRouter(prefix="/feedback", tags=["feedback"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class RateRequest(BaseModel):
    """Body for POST /rate."""
    story_id: str = Field(..., min_length=1, max_length=128)
    chapter_idx: int = Field(..., ge=0)
    user_id: str = Field(..., min_length=1, max_length=64)
    scores: RatingScores
    comment: str = Field(default="", max_length=2000)


class RateResponse(BaseModel):
    """Confirmation response after submitting a rating."""
    feedback_id: str
    overall: float
    status: str = "ok"


class StoryRatingsResponse(BaseModel):
    """All ratings for a single story."""
    story_id: str
    total: int
    ratings: list[dict[str, Any]]


class StatsResponse(BaseModel):
    """Aggregate feedback statistics across all stories."""
    total_ratings: int
    avg_overall: float
    avg_coherence: float
    avg_character: float
    avg_drama: float
    avg_writing: float
    score_distribution: dict[str, int]
    per_story_count: dict[str, int]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/rate", response_model=RateResponse, status_code=201)
def submit_rating(body: RateRequest) -> RateResponse:
    """Submit a user rating for a specific chapter.

    Scores are 1–5 per dimension: coherence, character, drama, writing.
    """
    try:
        entry: FeedbackEntry = collector.submit_rating(
            story_id=body.story_id,
            chapter_idx=body.chapter_idx,
            user_id=body.user_id,
            scores=body.scores.model_dump(),
            comment=body.comment,
        )
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return RateResponse(feedback_id=entry.feedback_id, overall=entry.overall)


@router.get("/story/{story_id}", response_model=StoryRatingsResponse)
def get_story_ratings(story_id: str) -> StoryRatingsResponse:
    """Return all ratings submitted for a story, ordered by chapter then time."""
    entries = collector.get_story_ratings(story_id)
    return StoryRatingsResponse(
        story_id=story_id,
        total=len(entries),
        ratings=[e.model_dump() for e in entries],
    )


@router.get("/stats", response_model=StatsResponse)
def get_stats() -> StatsResponse:
    """Return aggregate feedback statistics across all rated stories."""
    stats = collector.get_aggregate_stats()
    return StatsResponse(**stats)
