"""User feedback endpoints — collect ratings and comments on generated stories.

Feedback is stored in-memory (keyed by story_id) and exposed for analytics.
No auth required to submit; listing requires auth to prevent data harvesting.
"""

import logging
import time
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from middleware.auth_middleware import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/feedback", tags=["feedback"])

# In-memory store: story_id -> list of FeedbackEntry dicts
_store: dict[str, list] = {}


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class FeedbackRequest(BaseModel):
    story_id: str = Field(..., min_length=1, max_length=128)
    rating: int = Field(..., ge=1, le=5, description="1–5 star rating")
    comment: Optional[str] = Field(None, max_length=2000)


class FeedbackEntry(BaseModel):
    story_id: str
    rating: int
    comment: Optional[str]
    submitted_at: float


class FeedbackListResponse(BaseModel):
    story_id: str
    entries: List[FeedbackEntry]
    average_rating: float
    count: int


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("", status_code=201)
async def submit_feedback(body: FeedbackRequest) -> dict:
    """Submit a rating and optional comment for a story."""
    entry = FeedbackEntry(
        story_id=body.story_id,
        rating=body.rating,
        comment=body.comment,
        submitted_at=time.time(),
    )
    if body.story_id not in _store:
        _store[body.story_id] = []
    _store[body.story_id].append(entry.model_dump())
    logger.info(f"Feedback submitted: story={body.story_id} rating={body.rating}")
    return {"status": "ok", "story_id": body.story_id}


@router.get("/{story_id}", response_model=FeedbackListResponse)
async def get_feedback(
    story_id: str,
    _user: dict = Depends(get_current_user),
) -> FeedbackListResponse:
    """Return all feedback entries for a story (auth required)."""
    entries_raw = _store.get(story_id, [])
    if not entries_raw:
        raise HTTPException(status_code=404, detail=f"No feedback found for story '{story_id}'")

    entries = [FeedbackEntry(**e) for e in entries_raw]
    avg = round(sum(e.rating for e in entries) / len(entries), 2)
    return FeedbackListResponse(
        story_id=story_id,
        entries=entries,
        average_rating=avg,
        count=len(entries),
    )
