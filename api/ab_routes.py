"""A/B testing API routes."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from middleware.auth_middleware import get_current_user
from services.ab_testing import manager

router = APIRouter(prefix="/ab", tags=["ab-testing"])


class CreateExperimentBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    variants: list[str] = Field(..., min_length=2)


class AssignBody(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=64)


class ResultBody(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=64)
    metric: str = Field(..., min_length=1, max_length=128)
    value: float


@router.post("/experiments", status_code=201)
def create_experiment(body: CreateExperimentBody, _user=Depends(get_current_user)):
    """Create a new A/B experiment."""
    try:
        experiment_id = manager.create_experiment(body.name, body.variants)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"experiment_id": experiment_id}


@router.get("/experiments")
def list_experiments():
    """List all experiments with metadata."""
    return {"experiments": manager.list_experiments()}


@router.post("/experiments/{experiment_id}/assign")
def assign_variant(experiment_id: str, body: AssignBody):
    """Return deterministic variant for a session."""
    try:
        variant = manager.assign_variant(experiment_id, body.session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"variant": variant}


@router.post("/experiments/{experiment_id}/result", status_code=201)
def record_result(experiment_id: str, body: ResultBody, _user=Depends(get_current_user)):
    """Record an outcome for a session."""
    try:
        manager.record_result(experiment_id, body.session_id, body.metric, body.value)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"status": "ok"}


@router.get("/experiments/{experiment_id}/results")
def get_results(experiment_id: str):
    """Return per-variant aggregated results."""
    try:
        results = manager.get_results(experiment_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"results": results}
