"""Token usage API routes — exposes TokenCostTracker data over HTTP.

Endpoints:
    GET  /api/v1/usage/{story_id}        — cost breakdown for one story
    GET  /api/v1/usage/session           — session-wide summary
    DELETE /api/v1/usage/session         — reset session tracking
    GET  /api/v1/usage/story/{filename}  — per-checkpoint sidecar (Piece L)
"""

from __future__ import annotations

import pathlib

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.token_cost_tracker import TokenCostTracker
from services.usage_history import read_usage

router = APIRouter(prefix="/usage", tags=["usage"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class LayerBreakdown(BaseModel):
    tokens: int
    cost_usd: float


class StoryCostResponse(BaseModel):
    story_id: str
    call_count: int
    total_prompt_tokens: int
    total_completion_tokens: int
    total_tokens: int
    total_cost_usd: float
    by_layer: dict[str, LayerBreakdown]
    by_agent: dict[str, LayerBreakdown]
    by_model: dict[str, LayerBreakdown]


class SessionSummaryResponse(BaseModel):
    call_count: int
    total_prompt_tokens: int
    total_completion_tokens: int
    total_tokens: int
    total_cost_usd: float
    by_story: dict[str, LayerBreakdown]
    by_model: dict[str, LayerBreakdown]


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------


@router.get("/session", response_model=SessionSummaryResponse)
async def get_session_summary() -> SessionSummaryResponse:
    """Return aggregated token usage and cost for the current server session.

    The session accumulates all tracked calls since the server started (or
    since the last DELETE /usage/session reset).
    """
    tracker = TokenCostTracker()
    data = tracker.get_session_summary()
    return SessionSummaryResponse(**data)


@router.delete("/session", status_code=200)
async def reset_session() -> dict:
    """Clear all in-memory token usage records for the current session.

    Does **not** affect any persisted cost log file configured via
    STORYFORGE_COST_LOG.  Returns a confirmation message.
    """
    tracker = TokenCostTracker()
    tracker.reset_session()
    return {"status": "ok", "message": "Session token usage reset."}


@router.get("/{story_id}", response_model=StoryCostResponse)
async def get_story_usage(story_id: str) -> StoryCostResponse:
    """Return token usage and cost breakdown for a single story.

    Path parameters:
        story_id: The story identifier used when tracking was recorded.

    Returns a breakdown by pipeline layer (1/2/3), by agent name, and by
    model name.  All totals are zero when no records exist for the story.
    """
    if not story_id or len(story_id) > 256:
        raise HTTPException(status_code=400, detail="Invalid story_id")

    tracker = TokenCostTracker()
    summary = tracker.get_story_cost(story_id)

    # Convert internal dicts to typed models
    def _to_breakdown(raw: dict) -> dict[str, LayerBreakdown]:
        return {k: LayerBreakdown(**v) for k, v in raw.items()}

    return StoryCostResponse(
        story_id=summary.story_id,
        call_count=summary.call_count,
        total_prompt_tokens=summary.total_prompt_tokens,
        total_completion_tokens=summary.total_completion_tokens,
        total_tokens=summary.total_tokens,
        total_cost_usd=summary.total_cost_usd,
        by_layer=_to_breakdown(summary.by_layer),
        by_agent=_to_breakdown(summary.by_agent),
        by_model=_to_breakdown(summary.by_model),
    )


# ──────────────────────────────────────────────────────────────────────────
# Per-story usage sidecar (Piece L) — reads ``<checkpoint>.usage.json``
# ──────────────────────────────────────────────────────────────────────────


@router.get("/story/{filename}")
def get_story_usage_sidecar(filename: str) -> dict:
    """Return ``{events, totals}`` for a checkpoint, or empty totals if missing.

    Always 200 — older stories without a sidecar return zeroed totals so the
    frontend can render uniformly. Filename validation blocks path traversal.
    """
    safe = pathlib.Path(filename).name
    if not safe or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    data = read_usage(safe)
    if data is None:
        return {
            "events": [],
            "totals": {"total_tokens": 0, "total_cost_usd": 0.0, "call_count": 0},
        }
    return data
