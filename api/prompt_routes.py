"""Prompt management API routes — version info, listing, comparison."""

from fastapi import APIRouter

from services.prompt_registry import (
    get_prompt_version,
    list_prompt_versions,
    get_active_prompts,
    get_prompt_diff,
)

router = APIRouter(prefix="/prompts", tags=["prompts"])


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
