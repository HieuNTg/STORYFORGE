"""Codex API routes — serve Story Bible data for the World Codex viewer."""

import json
import logging
import os
import pathlib

from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/codex", tags=["codex"])

_PROJECT_ROOT = pathlib.Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))).resolve()
_CHECKPOINT_DIR = _PROJECT_ROOT / "output" / "checkpoints"


@router.get("/{story_id}")
def get_codex(story_id: str):
    """Return the story bible, characters, world, and plot data for a checkpoint.

    story_id is the checkpoint filename (same as /pipeline/checkpoints/{filename}).
    """
    safe_name = pathlib.Path(story_id).name
    if not safe_name or ".." in story_id:
        raise HTTPException(status_code=400, detail="Invalid story_id")

    checkpoint_path = (_CHECKPOINT_DIR / safe_name).resolve()
    if not str(checkpoint_path).startswith(str(_CHECKPOINT_DIR)):
        raise HTTPException(status_code=400, detail="Invalid story_id")
    if not checkpoint_path.exists():
        raise HTTPException(status_code=404, detail="Story not found")

    try:
        with open(str(checkpoint_path), "r", encoding="utf-8") as f:
            data = json.load(f)

        from models.schemas import PipelineOutput
        output = PipelineOutput(**data)
        draft = output.story_draft

        if not draft:
            raise HTTPException(status_code=404, detail="No story data in checkpoint")

        # Build codex payload
        characters = [c.model_dump() for c in draft.characters]
        world = draft.world.model_dump() if draft.world else None
        bible = draft.story_bible.model_dump() if draft.story_bible else None

        # Chapter timeline: chapter number + title + summary + key events
        timeline = [
            {
                "chapter_number": ch.chapter_number,
                "title": ch.title,
                "summary": ch.summary,
            }
            for ch in draft.chapters
            if ch.summary
        ]
        # Fall back to outlines if chapters lack summaries
        if not timeline:
            timeline = [
                {
                    "chapter_number": o.chapter_number,
                    "title": o.title,
                    "summary": o.summary,
                    "key_events": o.key_events,
                }
                for o in draft.outlines
            ]

        # Character states (latest mood / arc)
        char_states = {cs.name: cs.model_dump() for cs in draft.character_states}

        return {
            "title": draft.title,
            "genre": draft.genre,
            "synopsis": draft.synopsis,
            "characters": characters,
            "world": world,
            "story_bible": bible,
            "timeline": timeline,
            "character_states": char_states,
            "total_chapters": len(draft.chapters),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to build codex for {safe_name}: {e}")
        raise HTTPException(status_code=500, detail="Failed to load story codex")
