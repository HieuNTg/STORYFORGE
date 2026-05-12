"""Analytics API routes — onboarding funnel tracking."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from middleware.rbac import Permission, require_permission_if_enabled
from services.onboarding_analytics import tracker

router = APIRouter(prefix="/analytics", tags=["analytics"])
_ACCESS_ANALYTICS = Depends(require_permission_if_enabled(Permission.ACCESS_ANALYTICS))


class StepBody(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=64)
    step: str = Field(..., min_length=1, max_length=128)
    duration_ms: int = Field(..., ge=0, le=3_600_000)


class DropoutBody(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=64)
    step: str = Field(..., min_length=1, max_length=128)


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


@router.get("/onboarding", dependencies=[_ACCESS_ANALYTICS])
def get_funnel():
    """Return onboarding funnel summary."""
    return {"funnel": tracker.get_funnel()}
