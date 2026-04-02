"""Evaluation API routes — submit human evals and retrieve aggregate reports."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.eval_pipeline import EvalPipeline

router = APIRouter(prefix="/v1/eval", tags=["eval"])

_pipeline = EvalPipeline()


class HumanEvalRequest(BaseModel):
    story_id: str
    evaluator_id: str
    scores: dict  # metric_name -> float (0-5 scale)


@router.post("/submit", summary="Submit a human evaluation for a story")
def submit_eval(body: HumanEvalRequest):
    """Accept a human evaluator's scores for a given story.

    Scores should be a dict of metric names to float values (0-5 scale).
    """
    if not body.story_id.strip():
        raise HTTPException(status_code=422, detail="story_id required")
    if not body.evaluator_id.strip():
        raise HTTPException(status_code=422, detail="evaluator_id required")
    if not body.scores:
        raise HTTPException(status_code=422, detail="scores dict must not be empty")

    record = _pipeline.submit_human_eval(
        story_id=body.story_id,
        evaluator_id=body.evaluator_id,
        scores_dict=body.scores,
    )
    return {"status": "ok", "record": record}


@router.get("/{story_id}", summary="Get aggregate evaluation report for a story")
def get_eval_report(story_id: str):
    """Return the full evaluation report: auto metrics + human evals + aggregate score."""
    report = _pipeline.generate_report(story_id=story_id)
    return report
