"""Quality scores API — read-only access to L1/L2 chapter scoring data.

Surfaces the per-chapter quality breakdown that the orchestrator already
computes (via ``services.quality_scorer.QualityScorer``) and persists onto
``PipelineOutput.quality_scores``. Accepts either an active orchestrator
session UUID or a checkpoint filename (``*.json``), reusing the same
``_get_story_data`` resolver as the image routes.

This endpoint NEVER triggers scoring — checkpoints without scores return an
empty ``chapters`` list and a null ``overall``, so the reader can degrade
gracefully on legacy stories generated before scoring was enabled.

Also exposes ``GET /quality/`` (batch summary), used by the library list to
show overall + weakest-chapter pills without opening each story.
"""

import json
import logging
import os
import pathlib
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.export_routes import _get_story_data

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/quality", tags=["quality"])

_PROJECT_ROOT = pathlib.Path(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
).resolve()
_CHECKPOINT_DIR = _PROJECT_ROOT / "output" / "checkpoints"


class OverallQuality(BaseModel):
    """Aggregate scores for the highest-layer scoring run available."""
    scoring_layer: int = 0
    overall: float = 0.0
    avg_coherence: float = 0.0
    avg_character: float = 0.0
    avg_drama: float = 0.0
    avg_writing: float = 0.0
    weakest_chapter: int = 0


class ChapterQuality(BaseModel):
    chapter_number: int
    title: str = ""
    scoring_layer: int = 0
    scores: dict[str, float]
    notes: str = ""


class QualityResponse(BaseModel):
    overall: Optional[OverallQuality] = None
    chapters: list[ChapterQuality]


def _chapter_titles(output) -> dict[int, str]:
    """Build chapter_number → title map from enhanced_story (preferred) or story_draft."""
    story = output.enhanced_story or output.story_draft
    titles: dict[int, str] = {}
    if story and getattr(story, "chapters", None):
        for ch in story.chapters:
            num = getattr(ch, "chapter_number", None)
            if num is not None:
                titles[num] = getattr(ch, "title", "") or ""
    return titles


def _score_to_dict(cs) -> dict[str, float]:
    """Project a ChapterScore into the response payload (drop chapter_number/notes)."""
    return {
        "coherence": cs.coherence,
        "character_consistency": cs.character_consistency,
        "drama": cs.drama,
        "writing_quality": cs.writing_quality,
        "thematic_alignment": cs.thematic_alignment,
        "dialogue_depth": cs.dialogue_depth,
        "overall": cs.overall,
    }


def _normalize_quality(output) -> Optional[QualityResponse]:
    """L2-wins normalization: merge L1+L2 scores, prefer the highest layer.

    Returns ``QualityResponse(overall=None, chapters=[])`` when there are no
    scores at all (the per-session endpoint surfaces this; the summary endpoint
    converts it to ``None``).

    Returns ``None`` only when ``output`` itself is missing (defensive).
    """
    if output is None:
        return None
    quality_scores = list(output.quality_scores or [])
    if not quality_scores:
        return QualityResponse(overall=None, chapters=[])

    titles = _chapter_titles(output)

    # Merge per-chapter: walk L1 then L2 so later (higher) layer overrides.
    merged: dict[int, tuple[int, object]] = {}  # chapter_number → (layer, ChapterScore)
    for story_score in sorted(quality_scores, key=lambda s: s.scoring_layer):
        for cs in story_score.chapter_scores:
            existing = merged.get(cs.chapter_number)
            if existing is None or story_score.scoring_layer >= existing[0]:
                merged[cs.chapter_number] = (story_score.scoring_layer, cs)

    chapters: list[ChapterQuality] = []
    for chapter_number in sorted(merged.keys()):
        layer, cs = merged[chapter_number]
        chapters.append(
            ChapterQuality(
                chapter_number=cs.chapter_number,
                title=titles.get(cs.chapter_number, ""),
                scoring_layer=layer,
                scores=_score_to_dict(cs),
                notes=cs.notes or "",
            )
        )

    # Overall: pick the latest (highest-layer) StoryScore aggregate.
    latest = max(quality_scores, key=lambda s: s.scoring_layer)
    overall = OverallQuality(
        scoring_layer=latest.scoring_layer,
        overall=latest.overall,
        avg_coherence=latest.avg_coherence,
        avg_character=latest.avg_character,
        avg_drama=latest.avg_drama,
        avg_writing=latest.avg_writing,
        weakest_chapter=latest.weakest_chapter,
    )
    return QualityResponse(overall=overall, chapters=chapters)


def _summarize_quality(output) -> Optional[dict]:
    """Compact per-story summary for the library list: overall + weakest only.

    Returns ``None`` for unscored stories so the frontend can render a neutral
    "unscored" state. Reuses ``_normalize_quality`` so the L2-wins rule is
    defined exactly once.
    """
    normalized = _normalize_quality(output)
    if normalized is None or normalized.overall is None:
        return None
    overall = normalized.overall
    # Weakest chapter score: look it up from the merged chapter list.
    weakest_score = 0.0
    for ch in normalized.chapters:
        if ch.chapter_number == overall.weakest_chapter:
            weakest_score = float(ch.scores.get("overall", 0.0))
            break
    return {
        "overall": round(overall.overall, 2),
        "weakest_chapter": overall.weakest_chapter,
        "weakest_score": round(weakest_score, 2),
        "scoring_layer": overall.scoring_layer,
    }


@router.get("")
@router.get("/")
def get_quality_summaries() -> dict:
    """Batch summary for the library list — one entry per checkpoint file.

    Scans ``output/checkpoints/*.json`` and returns ``{filename: summary | null}``.
    A ``null`` value means either parsing failed (logged) or the story has no
    quality scores. The endpoint never 500s on a single bad file.
    """
    summaries: dict[str, Optional[dict]] = {}
    if not _CHECKPOINT_DIR.exists():
        return {"summaries": summaries}

    from models.schemas import PipelineOutput

    for path in sorted(_CHECKPOINT_DIR.glob("*.json")):
        name = path.name
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            output = PipelineOutput.model_validate(data)
            summaries[name] = _summarize_quality(output)
        except Exception as e:
            logger.info(f"quality summary skip {name}: {e}")
            summaries[name] = None
    return {"summaries": summaries}


@router.get("/{session_id}", response_model=QualityResponse)
async def get_quality(session_id: str) -> QualityResponse:
    """Return per-chapter quality scores for a session or checkpoint.

    Merge rule when both L1 and L2 scoring ran: prefer the highest scoring_layer
    per chapter (L2 latest wins). Chapters without any score are omitted.
    """
    orch = await _get_story_data(session_id)
    if not orch or not orch.output:
        raise HTTPException(status_code=404, detail="Session or checkpoint not found")

    normalized = _normalize_quality(orch.output)
    # _normalize_quality only returns None when output is None (we guarded above).
    return normalized or QualityResponse(overall=None, chapters=[])
