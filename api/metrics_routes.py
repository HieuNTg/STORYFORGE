"""Prometheus metrics endpoint."""

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from services.metrics import format_metrics

router = APIRouter(tags=["metrics"])


@router.get("/metrics", response_class=PlainTextResponse)
async def get_metrics() -> PlainTextResponse:
    """Expose Prometheus text metrics (format version 0.0.4)."""
    return PlainTextResponse(
        content=format_metrics(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
