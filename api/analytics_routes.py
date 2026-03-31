"""Analytics API routes — onboarding funnel tracking."""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

from services.onboarding_analytics import tracker

router = APIRouter(prefix="/analytics", tags=["analytics"])


class StepBody(BaseModel):
    session_id: str
    step: str
    duration_ms: int


class DropoutBody(BaseModel):
    session_id: str
    step: str


@router.post("/onboarding/step")
def record_step(body: StepBody):
    """Record completion of an onboarding wizard step."""
    tracker.track_step(body.session_id, body.step, body.duration_ms)
    return {"status": "ok"}


@router.post("/onboarding/dropout")
def record_dropout(body: DropoutBody):
    """Record a dropout at an onboarding wizard step."""
    tracker.track_dropout(body.session_id, body.step)
    return {"status": "ok"}


@router.get("/onboarding")
def get_funnel():
    """Return onboarding funnel summary."""
    return {"funnel": tracker.get_funnel()}
