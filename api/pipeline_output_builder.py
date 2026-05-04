"""Build JSON-serializable summary from PipelineOutput for API responses."""

from services.text_utils import sanitize_story_html as _san


def build_output_summary(output) -> dict:
    """Convert PipelineOutput to a JSON-friendly dict for the frontend.

    All LLM-generated text fields are sanitized with nh3 to prevent XSS.
    """
    result = {"has_draft": False, "has_enhanced": False}

    if output.story_draft:
        d = output.story_draft
        result["has_draft"] = True
        result["draft"] = {
            "title": _san(d.title),
            "genre": _san(d.genre),
            "synopsis": _san(d.synopsis),
            "characters": [
                {"name": _san(c.name), "personality": _san(c.personality)}
                for c in d.characters
            ],
            "chapters": [
                {
                    "number": ch.chapter_number,
                    "title": _san(ch.title),
                    "content": _san(ch.content),
                }
                for ch in d.chapters
            ],
        }

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
            "suggestions": [_san(sg) for sg in (s.drama_suggestions[:5] if s.drama_suggestions else [])],
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
