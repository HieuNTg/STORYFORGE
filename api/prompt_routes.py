"""Prompt management API routes — list, preview, A/B test prompts."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from middleware.rbac import Permission, require_permission_if_enabled
from services.prompt_registry import (
    get_prompt_version,
    list_prompt_versions,
    get_active_prompts,
    get_prompt_diff,
)
from services.prompt_ab_bridge import bridge

router = APIRouter(prefix="/prompts", tags=["prompts"])
_CONFIGURE_PIPELINE = Depends(require_permission_if_enabled(Permission.CONFIGURE_PIPELINE))


# ---------------------------------------------------------------------------
# Existing prompt-registry routes
# ---------------------------------------------------------------------------

@router.get("/version", summary="Get current prompt version")
def current_version():
    """Return metadata about the active prompt version."""
    return get_prompt_version()


@router.get("/versions", summary="List all available prompt versions")
def all_versions():
    """List prompt YAML files in the prompts directory with version metadata."""
    return {"versions": list_prompt_versions()}


@router.get("/active", summary="Get all active prompts")
def active_prompts():
    """Return all active prompts from the current version."""
    prompts = get_active_prompts()
    return {"prompt_count": len(prompts), "prompts": list(prompts.keys())}


@router.get("/diff", summary="Compare two prompt versions")
def diff_versions(a: str, b: str):
    """Compare prompt keys between two version files."""
    return get_prompt_diff(a, b)


# ---------------------------------------------------------------------------
# PromptManager routes (requires services/prompt_manager.py from Feature-2 P1)
# ---------------------------------------------------------------------------

@router.get("", summary="List all prompts with metadata")
def list_prompts():
    """Return all registered prompts with version metadata."""
    try:
        from services.prompt_manager import prompt_manager  # noqa: PLC0415
        return {"prompts": prompt_manager.list_prompts()}
    except ImportError:
        raise HTTPException(status_code=503, detail="PromptManager not available yet")


@router.get("/experiments", summary="List active A/B experiments")
def list_experiments():
    """Return all active prompt A/B experiments."""
    return {"experiments": bridge.list_active_experiments()}


@router.get("/experiments/{prompt_name}/results", summary="Get A/B results for a prompt")
def experiment_results(prompt_name: str):
    """Return per-variant aggregated results for a prompt's A/B experiment."""
    try:
        return bridge.get_experiment_results(prompt_name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/{name}", summary="Get prompt details and raw template")
def get_prompt(name: str):
    """Return prompt metadata and raw (unformatted) template."""
    try:
        from services.prompt_manager import prompt_manager  # noqa: PLC0415
        raw = prompt_manager.get_raw(name)
        return {"name": name, "template": raw}
    except ImportError:
        raise HTTPException(status_code=503, detail="PromptManager not available yet")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/{name}/preview", summary="Preview formatted prompt with sample vars")
def preview_prompt(name: str, genre: str = "Tiên Hiệp", **kwargs):
    """Return formatted prompt using provided query params as template variables."""
    try:
        from services.prompt_manager import prompt_manager  # noqa: PLC0415
        formatted = prompt_manager.get(name, genre=genre, **kwargs)
        return {"name": name, "genre": genre, "preview": formatted}
    except ImportError:
        raise HTTPException(status_code=503, detail="PromptManager not available yet")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ---------------------------------------------------------------------------
# A/B experiment management
# ---------------------------------------------------------------------------

class CreateExperimentBody(BaseModel):
    prompt_name: str = Field(..., min_length=1, max_length=128)
    variants: list[str] = Field(..., min_length=2)


@router.post(
    "/experiments",
    status_code=201,
    summary="Create a prompt A/B experiment",
    dependencies=[_CONFIGURE_PIPELINE],
)
def create_experiment(body: CreateExperimentBody):
    """Create an A/B experiment testing different versions of a prompt."""
    try:
        experiment_id = bridge.create_prompt_experiment(body.prompt_name, body.variants)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"experiment_id": experiment_id, "prompt_name": body.prompt_name}
