"""Prometheus metrics endpoints."""

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse

from middleware.rbac import Permission, require_permission_if_enabled
from services.metrics import format_metrics
from services.prometheus_metrics import prometheus_metrics

router = APIRouter(tags=["metrics"])
_ACCESS_ANALYTICS = Depends(require_permission_if_enabled(Permission.ACCESS_ANALYTICS))


@router.get("/metrics", response_class=PlainTextResponse, dependencies=[_ACCESS_ANALYTICS])
async def get_metrics() -> PlainTextResponse:
    """Expose Prometheus text metrics (format version 0.0.4)."""
    return PlainTextResponse(
        content=format_metrics(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


@router.get("/metrics/prometheus", response_class=PlainTextResponse, dependencies=[_ACCESS_ANALYTICS])
async def get_prometheus_metrics() -> PlainTextResponse:
    """Expose StoryForge request/pipeline/SSE metrics in Prometheus text format.

    Metrics exposed:
    - storyforge_requests_total
    - storyforge_request_duration_seconds
    - storyforge_pipeline_runs_total
    - storyforge_active_sse_connections
    - storyforge_uptime_seconds
    """
    return PlainTextResponse(
        content=prometheus_metrics.format_prometheus(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
