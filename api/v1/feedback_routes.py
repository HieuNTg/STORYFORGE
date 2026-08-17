"""Feedback API routes (placeholder — Sprint N+1)."""

from fastapi import APIRouter

router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.post("")
async def submit_feedback():
    """Placeholder — user feedback submission (not yet implemented)."""
    return {"message": "Feedback endpoint coming soon."}


@router.get("")
async def list_feedback():
    """Placeholder — list feedback entries (not yet implemented)."""
    return {"message": "Feedback listing coming soon."}