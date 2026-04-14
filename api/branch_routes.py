"""Branch reader API — choose-your-own-adventure endpoints."""

import json
import logging
import tempfile
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel, Field

from services.branch_narrative import manager
from services.llm_client import LLMClient
from services.export.branch_epub_exporter import BranchEPUBExporter

router = APIRouter(prefix="/branch", tags=["branch"])
logger = logging.getLogger(__name__)
llm = LLMClient()

MAX_BRANCH_DEPTH = 10


def _build_system_prompt(
    context: dict,
    node_states: dict | None = None,
    path_summary: str | None = None,
) -> str:
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

    if path_summary:
        parts.append(f"Story path so far (summarized):\n{path_summary}")

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


class BookmarkBody(BaseModel):
    node_id: str = Field(..., min_length=1, max_length=64, description="Node to bookmark")
    label: str = Field(default="", max_length=100, description="Optional bookmark label")


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

    # Build context-aware system prompt with per-node character states and path summary
    story_context = manager.get_context(session_id)
    node_states = manager.get_node_states(session_id)
    path_summary = manager.get_path_summary(session_id, max_tokens=500)
    system_prompt = _build_system_prompt(story_context, node_states, path_summary)

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


@router.post("/{session_id}/choose/stream")
def choose_branch_stream(session_id: str, body: ChooseBody):
    """Select a choice; stream continuation via SSE for real-time UX."""
    try:
        existing = manager.choose_branch(session_id, body.choice_index)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    if existing is not None:
        # Already generated — return immediately as SSE
        def _cached():
            yield f"data: {json.dumps({'type': 'complete', 'node': existing, 'generated': False})}\n\n"
        return StreamingResponse(
            _cached(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

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

    # Build context-aware system prompt with per-node character states and path summary
    story_context = manager.get_context(session_id)
    node_states = manager.get_node_states(session_id)
    path_summary = manager.get_path_summary(session_id, max_tokens=500)
    system_prompt = _build_system_prompt(story_context, node_states, path_summary)

    at_depth_limit = current_depth >= MAX_BRANCH_DEPTH - 1

    def event_generator():
        accumulated_text = ""

        try:
            if at_depth_limit:
                user_prompt = (
                    f"Story so far:\n{story_text}\n\n"
                    f"The reader chose: {choice_text}\n\n"
                    "Write a satisfying conclusion to this branch (200-300 words). "
                    "Return JSON with 'continuation' (the ending text), 'choices' as an empty list [], "
                    "and 'character_states' for any characters that changed."
                )
            else:
                user_prompt = (
                    f"Story so far:\n{story_text}\n\n"
                    f"The reader chose: {choice_text}\n\nContinue the story."
                )

            # Stream LLM response
            for chunk in llm.generate_stream(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.9,
            ):
                accumulated_text += chunk
                yield f"data: {json.dumps({'type': 'chunk', 'text': chunk})}\n\n"

            # Parse accumulated JSON
            try:
                # Try to extract JSON from markdown code blocks
                import re
                json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', accumulated_text)
                if json_match:
                    result = json.loads(json_match.group(1))
                else:
                    result = json.loads(accumulated_text)
            except json.JSONDecodeError:
                # Fallback: treat accumulated text as continuation
                result = {
                    "continuation": accumulated_text,
                    "choices": [] if at_depth_limit else ["Continue", "Take a different path"],
                    "character_states": {},
                }

            continuation = result.get("continuation") or result.get("text", accumulated_text)
            if at_depth_limit:
                new_choices = []
            else:
                new_choices = result.get("choices", ["Continue", "Take a different path"])
                if not isinstance(new_choices, list):
                    new_choices = ["Continue", "Take a different path"]
                new_choices = [str(c) for c in new_choices[:3]]

            # Extract and merge character states
            new_states = result.get("character_states", {})
            if not isinstance(new_states, dict):
                new_states = {}
            merged_states = {**node_states, **new_states}

            # Add node to tree
            node = manager.add_generated_node(
                session_id, body.choice_index, continuation, new_choices,
                character_states=merged_states,
            )

            yield f"data: {json.dumps({'type': 'complete', 'node': node, 'generated': True})}\n\n"

        except Exception as exc:
            logger.error(f"SSE branch generation failed: {exc}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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


@router.post("/{session_id}/undo")
def undo_navigation(session_id: str):
    """Undo last navigation — go back in history without losing redo."""
    try:
        node = manager.undo(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "node": node,
        "can_undo": manager.can_undo(session_id),
        "can_redo": manager.can_redo(session_id),
    }


@router.post("/{session_id}/redo")
def redo_navigation(session_id: str):
    """Redo previously undone navigation."""
    try:
        node = manager.redo(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "node": node,
        "can_undo": manager.can_undo(session_id),
        "can_redo": manager.can_redo(session_id),
    }


@router.get("/{session_id}/undo-redo-status")
def get_undo_redo_status(session_id: str):
    """Check if undo/redo are available."""
    try:
        return {
            "can_undo": manager.can_undo(session_id),
            "can_redo": manager.can_redo(session_id),
        }
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


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


@router.get("/{session_id}/tree/layout")
def get_tree_layout(session_id: str):
    """Return tree with computed layout positions for visualization.

    Includes X/Y positions for each node, bounds, and stats.
    """
    try:
        layout = manager.get_tree_layout(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return layout


@router.get("/{session_id}/tree/minimap")
def get_minimap_data(session_id: str):
    """Return simplified tree data for minimap rendering.

    Includes node positions, edges, and bounds.
    """
    try:
        minimap = manager.get_minimap_data(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return minimap


@router.get("/{session_id}/merge/preview")
def get_merge_preview(session_id: str, node_a: str, node_b: str):
    """Get a preview diff of two nodes before merging.

    Shows side-by-side comparison, conflict detection, and path info.
    """
    try:
        preview = manager.get_merge_preview(session_id, node_a, node_b)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return preview


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


# ── Bookmarks ──────────────────────────────────────────────────────────────


@router.post("/{session_id}/bookmarks")
def add_bookmark(session_id: str, body: BookmarkBody):
    """Add a bookmark to a node."""
    try:
        bookmark = manager.add_bookmark(session_id, body.node_id, body.label)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"bookmark": bookmark}


@router.get("/{session_id}/bookmarks")
def list_bookmarks(session_id: str):
    """List all bookmarks for a session."""
    try:
        bookmarks = manager.list_bookmarks(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"bookmarks": bookmarks}


@router.delete("/{session_id}/bookmarks/{bookmark_id}")
def remove_bookmark(session_id: str, bookmark_id: str):
    """Remove a bookmark."""
    try:
        removed = manager.remove_bookmark(session_id, bookmark_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    if not removed:
        raise HTTPException(status_code=404, detail=f"Bookmark {bookmark_id!r} not found")
    return {"removed": True}


@router.post("/{session_id}/bookmarks/{bookmark_id}/goto")
def goto_bookmark(session_id: str, bookmark_id: str):
    """Navigate to a bookmarked node."""
    try:
        node = manager.goto_bookmark(session_id, bookmark_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"node": node}


# ── Auto-explore ───────────────────────────────────────────────────────────


class AutoExploreBody(BaseModel):
    num_paths: int = Field(default=3, ge=2, le=5, description="Number of paths to generate")
    depth: int = Field(default=2, ge=1, le=3, description="Depth to explore each path")


class StateChangesBody(BaseModel):
    node_id: str = Field(..., min_length=1, max_length=64)
    state_changes: dict = Field(..., description="State changes, e.g., {'gold': 10, 'reputation': -5}")


class ChoiceConditionsBody(BaseModel):
    node_id: str = Field(..., min_length=1, max_length=64)
    conditions: list[dict] = Field(..., description="Conditions, e.g., [{'index': 0, 'requires': {'gold': 50}}]")


@router.post("/{session_id}/auto-explore")
def auto_explore_branches(session_id: str, body: AutoExploreBody):
    """Auto-generate multiple branch paths for preview.

    Generates num_paths parallel continuations, each exploring depth levels deep.
    Useful for seeing what different choices lead to before committing.
    """
    try:
        paths = manager.auto_explore(
            session_id,
            num_paths=body.num_paths,
            depth=body.depth,
            llm=llm,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"paths": paths, "total_paths": len(paths)}


# ── Analytics ──────────────────────────────────────────────────────────────


@router.get("/{session_id}/analytics")
def get_session_analytics(session_id: str):
    """Get analytics for a branch session.

    Returns choice popularity, total choices made, and popular paths.
    """
    try:
        analytics = manager.get_analytics(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return analytics


# ── State Variables ────────────────────────────────────────────────────────


@router.get("/{session_id}/state")
def get_state_variables(session_id: str):
    """Get current accumulated state variables (gold, reputation, etc.)."""
    try:
        state = manager.get_state_variables(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"state": state}


@router.post("/{session_id}/state/changes")
def set_node_state_changes(session_id: str, body: StateChangesBody):
    """Set state changes for a node (applied when player reaches this node)."""
    try:
        changes = manager.set_state_changes(session_id, body.node_id, body.state_changes)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"state_changes": changes}


@router.post("/{session_id}/state/conditions")
def set_choice_conditions(session_id: str, body: ChoiceConditionsBody):
    """Set conditions for choices (e.g., requires certain state to unlock)."""
    try:
        conditions = manager.set_choice_conditions(session_id, body.node_id, body.conditions)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"conditions": conditions}


@router.get("/{session_id}/choices")
def get_available_choices(session_id: str):
    """Get current node's choices with availability based on state conditions."""
    try:
        choices = manager.get_available_choices(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"choices": choices}


# ── Export ─────────────────────────────────────────────────────────────────


@router.get("/{session_id}/export/epub")
def export_branch_epub(
    session_id: str,
    title: str = "Interactive Story",
    author: str = "StoryForge AI",
):
    """Export branch tree as EPUB with all paths as chapters.

    Returns downloadable EPUB file.
    """
    try:
        tree = manager.get_tree(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    # Create temp file for EPUB
    with tempfile.NamedTemporaryFile(delete=False, suffix=".epub") as tmp:
        output_path = tmp.name

    result = BranchEPUBExporter.export(
        tree_data=tree,
        output_path=output_path,
        title=title,
        author=author,
    )

    if not result:
        raise HTTPException(status_code=500, detail="Failed to generate EPUB")

    # Return file for download
    safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in title)[:50]
    return FileResponse(
        path=output_path,
        media_type="application/epub+zip",
        filename=f"{safe_title}.epub",
        background=None,  # Let FastAPI handle cleanup
    )
