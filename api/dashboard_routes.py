"""Dashboard API routes — aggregated metrics summary + HTML serving."""

import re
import time
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from services import metrics as m
from services.onboarding_analytics import tracker

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

_DASHBOARD_PATH = Path(__file__).parent.parent / "web" / "dashboard.html"
_DASHBOARD_CACHE: str | None = None

# ---------------------------------------------------------------------------
# Prometheus text parser helpers
# ---------------------------------------------------------------------------

def _parse_prometheus(text: str) -> dict:
    """Parse Prometheus text exposition into a plain dict."""
    data: dict = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # metric_name{labels} value  OR  metric_name value
        match = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)(\{[^}]*\})?\s+([\d.e+\-]+)$', line)
        if not match:
            continue
        name, labels_str, value = match.group(1), match.group(2) or "", match.group(3)
        key = name + labels_str
        data[key] = float(value)
    return data


def _label_val(key: str, label: str) -> str | None:
    m2 = re.search(rf'{label}="([^"]*)"', key)
    return m2.group(1) if m2 else None


# ---------------------------------------------------------------------------
# Summary endpoint
# ---------------------------------------------------------------------------

@router.get("/summary")
def dashboard_summary():
    raw = m.format_metrics()
    parsed = _parse_prometheus(raw)

    # Pipeline counters
    success = parsed.get('pipeline_runs_total{status="success"}', 0)
    error = parsed.get('pipeline_runs_total{status="error"}', 0)
    active = parsed.get("active_pipelines", 0)

    # LLM counters (sum across all label combos)
    llm_total = sum(v for k, v in parsed.items() if k.startswith("llm_requests_total"))
    llm_errors = sum(v for k, v in parsed.items() if k.startswith("llm_errors_total"))

    # Quality histogram buckets
    buckets = {}
    q_sum = parsed.get("quality_score_histogram_sum", 0)
    q_count = parsed.get("quality_score_histogram_count", 0)
    for k, v in parsed.items():
        if k.startswith("quality_score_histogram_bucket"):
            le = _label_val(k, "le")
            if le:
                buckets[le] = v

    return {
        "pipeline": {
            "total": int(success + error),
            "success": int(success),
            "error": int(error),
            "active": int(active),
        },
        "llm": {
            "total_requests": int(llm_total),
            "total_errors": int(llm_errors),
        },
        "quality": {
            "buckets": buckets,
            "sum": q_sum,
            "count": int(q_count),
        },
        "onboarding": {
            "funnel": tracker.get_funnel(),
        },
        "timestamp": time.time(),
    }


# ---------------------------------------------------------------------------
# Dashboard HTML
# ---------------------------------------------------------------------------

@router.get("", response_class=HTMLResponse)
async def serve_dashboard():
    """Serve the analytics dashboard HTML."""
    global _DASHBOARD_CACHE
    if _DASHBOARD_CACHE is None:
        _DASHBOARD_CACHE = _DASHBOARD_PATH.read_text(encoding="utf-8")
    return HTMLResponse(_DASHBOARD_CACHE)
