"""Diagnostics routes — L1→L2 handoff observability.

GET /api/diagnostics/handoff/{story_id}
    Returns per-signal health + per-chapter contract reconciliation data.
    404 if story not found or pre-migration (no handoff_envelope persisted).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/diagnostics", tags=["diagnostics"])


@router.get("/handoff/{story_id}", summary="L1→L2 handoff diagnostics for a story")
async def get_handoff_diagnostics(story_id: str) -> JSONResponse:
    """Return handoff signal health and per-chapter contract data.

    Returns 404 when the story does not exist or was created before the
    handoff envelope migration (pipeline_runs.handoff_envelope is NULL).
    """
    from services.diagnostics_service import build_handoff_diagnostics

    result = build_handoff_diagnostics(story_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail="Story not found or no handoff envelope persisted (pre-migration story).",
        )
    return JSONResponse(content=result)


@router.get("/semantic/{story_id}", summary="Sprint-2 semantic verification diagnostics for a story")
async def get_semantic_diagnostics(story_id: str) -> JSONResponse:
    """Return per-chapter semantic findings and outline metrics.

    Returns 404 when the story does not exist or has no Sprint-2 semantic
    data (pre-Sprint-2 stories where both semantic_findings and
    outline_metrics columns are NULL).
    """
    from services.diagnostics_service import build_semantic_diagnostics

    result = build_semantic_diagnostics(story_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail="Story not found or no semantic diagnostics available (pre-Sprint-2 story).",
        )
    return JSONResponse(content=result)
