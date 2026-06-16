"""Build JSON-serializable summary from PipelineOutput for API responses."""

from services.text_utils import sanitize_story_html as _san


def _media_url(path: str) -> str:
    """Convert a stored chapter-image path into a public ``/media`` URL.

    Chapter images are persisted as paths relative to OUTPUT_ROOT (see
    ``rel_to_output_root`` in services/output_paths.py), e.g.
    ``my-slug/images/ch01_panel01.png``. The ``/media`` static mount serves
    OUTPUT_ROOT, so the URL is just ``/media/<rel>``. Already-absolute URLs
    (http/https) and already-prefixed ``/media/...`` values pass through.
    """
    if not path:
        return path
    if path.startswith(("http://", "https://", "/media/")):
        return path
    return "/media/" + path.lstrip("/")


def _chapter_image_urls(ch) -> list:
    """List of ``/media`` URLs for a chapter's generated panels (may be empty)."""
    return [_media_url(p) for p in (getattr(ch, "images", None) or []) if p]


def build_output_summary(output) -> dict:
    """Convert PipelineOutput to a JSON-friendly dict for the frontend.

    All LLM-generated text fields are sanitized with nh3 to prevent XSS.
    """
    result = {"has_draft": False, "has_enhanced": False}

    # Comic panels are generated onto the *enhanced* chapters (pipeline media
    # stage / on-demand regen both target enhanced_story when it exists). The
    # reader, however, renders the draft chapter list, so build a
    # chapter_number → image-urls map from the enhanced story and merge it down
    # onto the draft chapters below.
    enhanced_images: dict = {}
    if getattr(output, "enhanced_story", None):
        for _ch in output.enhanced_story.chapters:
            _urls = _chapter_image_urls(_ch)
            if _urls:
                enhanced_images[_ch.chapter_number] = _urls

    if output.story_draft:
        d = output.story_draft
        result["has_draft"] = True
        result["draft"] = {
            "title": _san(d.title),
            "genre": _san(d.genre),
            "synopsis": _san(d.synopsis),
            "target_total_chapters": getattr(d, "target_total_chapters", None),
            "written_chapters": len(d.chapters),
            "characters": [
                {"name": _san(c.name), "personality": _san(c.personality)}
                for c in d.characters
            ],
            "chapters": [
                {
                    "number": ch.chapter_number,
                    "title": _san(ch.title),
                    "content": _san(ch.content),
                    # Prefer images set directly on the draft chapter; otherwise
                    # fall back to the enhanced chapter's panels (same number).
                    "images": _chapter_image_urls(ch)
                    or enhanced_images.get(ch.chapter_number, []),
                }
                for ch in d.chapters
            ],
        }
        # Surface conflict_web for CharacterGraph co-occurrence in the theater.
        # Pull from story_draft (L1 output); omit silently if absent / empty.
        _cw = getattr(d, "conflict_web", None)
        if _cw:
            result["conflict_web"] = [
                {
                    "conflict_id": getattr(c, "conflict_id", ""),
                    "conflict_type": getattr(c, "conflict_type", ""),
                    "characters": getattr(c, "characters", []),
                    "description": _san(getattr(c, "description", "")),
                    "arc_range": getattr(c, "arc_range", ""),
                }
                for c in _cw
            ]

    if output.enhanced_story:
        es = output.enhanced_story
        result["has_enhanced"] = True
        result["enhanced"] = {
            "title": _san(es.title),
            "drama_score": getattr(es, "drama_score", 0),
            "chapters": [
                {
                    "number": ch.chapter_number,
                    "title": _san(ch.title),
                    "content": _san(ch.content),
                    "images": _chapter_image_urls(ch),
                }
                for ch in es.chapters
            ],
        }

    if output.simulation_result:
        s = output.simulation_result
        result["simulation"] = {
            "events_count": len(s.events),
            "events": [
                {
                    "type": _san(e.event_type),
                    "description": _san(e.description),
                    "drama_score": round(e.drama_score, 2),
                }
                for e in s.events[:20]
            ],
            "suggestions": [
                _san(sg)
                for sg in (s.drama_suggestions[:5] if s.drama_suggestions else [])
            ],
        }

    if output.quality_scores:
        result["quality"] = [
            {
                "layer": qs.scoring_layer,
                "overall": qs.overall,
                "coherence": qs.avg_coherence,
                "character": qs.avg_character,
                "drama": qs.avg_drama,
                "writing": qs.avg_writing,
            }
            for qs in output.quality_scores
        ]

    # P6: handoff health for Pipeline Health panel (no sanitisation needed — enum strings only)
    if output.handoff_health:
        result["handoff_health"] = output.handoff_health
        # Extract story_id from envelope if present (for diagnostics API fetch)
        _envelope = getattr(output, "handoff_envelope", None)
        if isinstance(_envelope, dict):
            _sid = _envelope.get("story_id") or ""
        elif output.handoff_health:
            # Fallback: peek at draft story_id
            _draft = getattr(output, "story_draft", None)
            _sid = getattr(_draft, "story_id", "") if _draft else ""
        else:
            _sid = ""
        if _sid:
            result["story_id"] = _sid

    return result
