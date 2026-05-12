"""Evaluation API routes — submit human evals and retrieve aggregate reports."""

import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator

from middleware.rbac import Permission, require_permission_if_enabled
from services.eval_pipeline import EvalPipeline

router = APIRouter(
    prefix="/v1/eval",
    tags=["eval"],
    dependencies=[Depends(require_permission_if_enabled(Permission.ACCESS_ANALYTICS))],
)

_pipeline = EvalPipeline()

# Safe ID pattern: alphanumeric + hyphens, 1-64 chars
_SAFE_ID_RE = re.compile(r"^[a-zA-Z0-9_\-]{1,64}$")


def _validate_safe_id(value: str, field_name: str) -> None:
    """Raise 400 if ID contains path-traversal or special characters."""
    if not _SAFE_ID_RE.match(value):
        raise HTTPException(status_code=400, detail=f"Invalid {field_name}")


class HumanEvalRequest(BaseModel):
    story_id: str
    evaluator_id: str
    scores: dict[str, float]  # metric_name -> float (0-5 scale)

    @field_validator("scores")
    @classmethod
    def validate_scores(cls, v: dict[str, float]) -> dict[str, float]:
        if not v:
            raise ValueError("scores must not be empty")
        for key, val in v.items():
            if not isinstance(val, (int, float)) or val < 0 or val > 5:
                raise ValueError(f"Score '{key}' must be between 0 and 5")
        return v


@router.post("/submit", summary="Submit a human evaluation for a story")
def submit_eval(body: HumanEvalRequest):
    """Accept a human evaluator's scores for a given story.

    Scores should be a dict of metric names to float values (0-5 scale).
    """
    _validate_safe_id(body.story_id, "story_id")
    _validate_safe_id(body.evaluator_id, "evaluator_id")

    record = _pipeline.submit_human_eval(
        story_id=body.story_id,
        evaluator_id=body.evaluator_id,
        scores_dict=body.scores,
    )
    return {"status": "ok", "record": record}


@router.get("/golden", summary="Run golden dataset regression test")
def run_golden_eval():
    """Run automated scoring against the golden evaluation dataset.

    Compares actual scores against baseline expectations to detect
    prompt quality regressions.
    """
    return _pipeline.run_golden_eval()


@router.get("/{story_id}", summary="Get aggregate evaluation report for a story")
def get_eval_report(story_id: str):
    """Return the full evaluation report: auto metrics + human evals + aggregate score."""
    _validate_safe_id(story_id, "story_id")
    report = _pipeline.generate_report(story_id=story_id)
    return report
