"""Branch reader API — choose-your-own-adventure endpoints."""

import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.branch_narrative import manager
from services.llm_client import LLMClient

router = APIRouter(prefix="/branch", tags=["branch"])
logger = logging.getLogger(__name__)
llm = LLMClient()

MAX_BRANCH_DEPTH = 10


def _build_system_prompt(context: dict, node_states: dict | None = None) -> str:
    """Build story-aware system prompt from session context and per-node character states."""
    parts = ["You are a creative storyteller. Continue the story based on the reader's choice."]

    if context.get("genre"):
        parts.append(f"Genre: {context['genre']}.")

    if context.get("characters"):
        char_lines = []
        for c in context["characters"]:
            if not c.get("name"):
                continue
            line = f"- {c['name']} ({c.get('role', '')}): {c.get('personality', '')}"
            if node_states and c["name"] in node_states:
                st = node_states[c["name"]]
                line += f" [mood: {st.get('mood', '?')}, arc: {st.get('arc_position', '?')}]"
            char_lines.append(line)
        if char_lines:
            parts.append("Key characters:\n" + "\n".join(char_lines))

    if context.get("world_summary"):
        parts.append(f"World: {context['world_summary']}")

    if context.get("conflict_summary"):
        parts.append(f"Active conflicts: {context['conflict_summary']}")

    parts.append(
        "Return JSON with:\n"
        "- 'continuation': story text (200-400 words)\n"
        "- 'choices': list of 2-3 short options\n"
        "- 'character_states': dict of {name: {mood, arc_position}} for characters that changed"
    )
    return "\n\n".join(parts)


# ── Request models ──────────────────────────────────────────────────────────

class BranchCharacter(BaseModel):
    name: str = ""
    role: str = ""
    personality: str = ""


class StartBody(BaseModel):
    text: str = Field(..., min_length=10, max_length=20000)
    genre: str = Field(default="", max_length=64)
    characters: list[BranchCharacter] = Field(default_factory=list, max_length=10)
    world_summary: str = Field(default="", max_length=500)
    conflict_summary: str = Field(default="", max_length=500)


class ChooseBody(BaseModel):
    choice_index: int = Field(..., ge=0, le=9)


class GotoBody(BaseModel):
    node_id: str = Field(..., min_length=1, max_length=64)


class MergeBody(BaseModel):
    node_a_id: str = Field(..., min_length=1, max_length=64, description="First node to merge")
    node_b_id: str = Field(..., min_length=1, max_length=64, description="Second node to merge")
    strategy: str = Field(default="auto", description="Merge strategy: 'auto', 'prefer_a', 'prefer_b'")


# ── Routes ──────────────────────────────────────────────────────────────────

@router.post("/start", status_code=201)
def start_session(body: StartBody):
    """Create a new branch session from story text."""
    context = {
        "genre": body.genre,
        "characters": [c.model_dump() for c in body.characters] if body.characters else [],
        "world_summary": body.world_summary,
        "conflict_summary": body.conflict_summary,
    }
    data = manager.start_session(body.text, context=context)
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
    story_text = current["text"]
    current_depth = current.get("depth", 0)

    # Build context-aware system prompt with per-node character states
    story_context = manager.get_context(session_id)
    node_states = manager.get_node_states(session_id)
    system_prompt = _build_system_prompt(story_context, node_states)

    # Enforce depth limit — generate ending node at max depth
    at_depth_limit = current_depth >= MAX_BRANCH_DEPTH - 1

    if at_depth_limit:
        try:
            result = llm.generate_json(
                system_prompt=system_prompt,
                user_prompt=(
                    f"Story so far:\n{story_text}\n\n"
                    f"The reader chose: {choice_text}\n\n"
                    "Write a satisfying conclusion to this branch (200-300 words). "
                    "Return JSON with 'continuation' (the ending text), 'choices' as an empty list [], "
                    "and 'character_states' for any characters that changed."
                ),
                temperature=0.9,
            )
        except Exception as exc:
            logger.error(f"LLM generation failed: {exc}")
            raise HTTPException(status_code=502, detail="LLM generation failed. Please try again.")
        continuation = result.get("continuation") or result.get("text", "")
        new_choices: list[str] = []
    else:
        try:
            result = llm.generate_json(
                system_prompt=system_prompt,
                user_prompt=(
                    f"Story so far:\n{story_text}\n\n"
                    f"The reader chose: {choice_text}\n\nContinue the story."
                ),
                temperature=0.9,
            )
        except Exception as exc:
            logger.error(f"LLM generation failed: {exc}")
            raise HTTPException(status_code=502, detail="LLM generation failed. Please try again.")

        continuation = result.get("continuation") or result.get("text", "")
        new_choices = result.get("choices", ["Continue", "Take a different path"])
        if not isinstance(new_choices, list):
            new_choices = ["Continue", "Take a different path"]
        new_choices = [str(c) for c in new_choices[:3]]

    # Extract and merge character states from LLM response
    new_states = result.get("character_states", {})
    if not isinstance(new_states, dict):
        new_states = {}
    merged_states = {**node_states, **new_states}

    try:
        node = manager.add_generated_node(
            session_id, body.choice_index, continuation, new_choices,
            character_states=merged_states,
        )
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


@router.post("/{session_id}/merge")
def merge_branches(session_id: str, body: MergeBody):
    """Merge two branch paths into a single canonical node.

    Detects contradictions between the branches and resolves them based on strategy:
    - 'auto': Use LLM to intelligently merge narratives
    - 'prefer_a': Keep node_a's version when conflicts occur
    - 'prefer_b': Keep node_b's version when conflicts occur
    """
    if body.strategy not in ("auto", "prefer_a", "prefer_b"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid strategy '{body.strategy}'. Must be 'auto', 'prefer_a', or 'prefer_b'",
        )

    try:
        result = manager.merge_branches(
            session_id=session_id,
            node_a_id=body.node_a_id,
            node_b_id=body.node_b_id,
            strategy=body.strategy,
            llm=llm if body.strategy == "auto" else None,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {
        "merged_node": result["merged_node"],
        "conflicts_resolved": result["conflicts_resolved"],
        "conflicts_unresolved": result["conflicts_unresolved"],
        "common_ancestor": result["common_ancestor"],
    }
