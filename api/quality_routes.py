"""Quality scores API — read-only access to L1/L2 chapter scoring data.

Surfaces the per-chapter quality breakdown that the orchestrator already
computes (via ``services.quality_scorer.QualityScorer``) and persists onto
``PipelineOutput.quality_scores``. Accepts either an active orchestrator
session UUID or a checkpoint filename (``*.json``), reusing the same
``_get_story_data`` resolver as the image routes.

This endpoint NEVER triggers scoring — checkpoints without scores return an
empty ``chapters`` list and a null ``overall``, so the reader can degrade
gracefully on legacy stories generated before scoring was enabled.
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.export_routes import _get_story_data

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/quality", tags=["quality"])


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


@router.get("/{session_id}", response_model=QualityResponse)
async def get_quality(session_id: str) -> QualityResponse:
    """Return per-chapter quality scores for a session or checkpoint.

    Merge rule when both L1 and L2 scoring ran: prefer the highest scoring_layer
    per chapter (L2 latest wins). Chapters without any score are omitted.
    """
    orch = await _get_story_data(session_id)
    if not orch or not orch.output:
        raise HTTPException(status_code=404, detail="Session or checkpoint not found")

    output = orch.output
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
