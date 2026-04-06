"""Branch reader API — choose-your-own-adventure endpoints."""

import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.branch_narrative import manager
from services.llm_client import LLMClient

router = APIRouter(prefix="/branch", tags=["branch"])
logger = logging.getLogger(__name__)
llm = LLMClient()

_SYSTEM_PROMPT = (
    "You are a creative storyteller. Continue the story based on the reader's choice. "
    "Return JSON with 'continuation' (story text, 200-400 words) and "
    "'choices' (list of 2-3 short options for what the reader should do next)."
)


# ── Request models ──────────────────────────────────────────────────────────

class StartBody(BaseModel):
    text: str = Field(..., min_length=10, max_length=20000)
    genre: str = Field(default="", max_length=64)


class ChooseBody(BaseModel):
    choice_index: int = Field(..., ge=0, le=9)


class GotoBody(BaseModel):
    node_id: str = Field(..., min_length=1, max_length=64)


# ── Routes ──────────────────────────────────────────────────────────────────

@router.post("/start", status_code=201)
def start_session(body: StartBody):
    """Create a new branch session from story text."""
    data = manager.start_session(body.text)
    return data


@router.get("/{session_id}/current")
def get_current(session_id: str):
    """Return current node with text and available choices."""
    try:
        node = manager.get_current_node(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"node": node}


@router.post("/{session_id}/choose")
def choose_branch(session_id: str, body: ChooseBody):
    """Select a choice; generate continuation via LLM if not already visited."""
    try:
        existing = manager.choose_branch(session_id, body.choice_index)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    if existing is not None:
        return {"node": existing, "generated": False}

    # Need LLM generation — get context first
    try:
        current = manager.get_current_node(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    choices = current.get("choices", [])
    if body.choice_index >= len(choices):
        raise HTTPException(
            status_code=400,
            detail=f"choice_index {body.choice_index} out of range ({len(choices)} choices)",
        )
    choice_text = choices[body.choice_index]
    context = current["text"]

    try:
        result = llm.generate_json(
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=(
                f"Story so far:\n{context}\n\n"
                f"The reader chose: {choice_text}\n\nContinue the story."
            ),
            temperature=0.9,
        )
    except Exception as exc:
        logger.error(f"LLM generation failed: {exc}")
        raise HTTPException(status_code=502, detail=f"LLM generation failed: {exc}")

    continuation = result.get("continuation") or result.get("text", "")
    new_choices = result.get("choices", ["Continue", "Take a different path"])
    if not isinstance(new_choices, list):
        new_choices = ["Continue", "Take a different path"]
    new_choices = [str(c) for c in new_choices[:3]]

    try:
        node = manager.add_generated_node(session_id, body.choice_index, continuation, new_choices)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return {"node": node, "generated": True}


@router.post("/{session_id}/back")
def go_back(session_id: str):
    """Navigate to parent node."""
    try:
        node = manager.go_back(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"node": node}


@router.post("/{session_id}/goto")
def goto_node(session_id: str, body: GotoBody):
    """Jump to any existing node in the session tree."""
    try:
        node = manager.goto_node(session_id, body.node_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"node": node}


@router.get("/{session_id}/tree")
def get_tree(session_id: str):
    """Return full tree structure for visualization."""
    try:
        tree = manager.get_tree(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return tree
