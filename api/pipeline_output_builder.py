"""Build JSON-serializable summary from PipelineOutput for API responses."""


def build_output_summary(output) -> dict:
    """Convert PipelineOutput to a JSON-friendly dict for the frontend."""
    result = {"has_draft": False, "has_enhanced": False, "has_video": False}

    if output.story_draft:
        d = output.story_draft
        result["has_draft"] = True
        result["draft"] = {
            "title": d.title,
            "genre": d.genre,
            "synopsis": d.synopsis,
            "characters": [
                {"name": c.name, "personality": c.personality}
                for c in d.characters
            ],
            "chapters": [
                {"number": ch.chapter_number, "title": ch.title, "content": ch.content}
                for ch in d.chapters
            ],
        }

    if output.enhanced_story:
        es = output.enhanced_story
        result["has_enhanced"] = True
        result["enhanced"] = {
            "title": es.title,
            "drama_score": getattr(es, "drama_score", 0),
            "chapters": [
                {"number": ch.chapter_number, "title": ch.title, "content": ch.content}
                for ch in es.chapters
            ],
        }

    if output.simulation_result:
        s = output.simulation_result
        result["simulation"] = {
            "events_count": len(s.events),
            "events": [
                {
                    "type": e.event_type,
                    "description": e.description,
                    "drama_score": round(e.drama_score, 2),
                }
                for e in s.events[:20]
            ],
            "suggestions": s.drama_suggestions[:5] if s.drama_suggestions else [],
        }

    if output.video_script:
        vs = output.video_script
        result["has_video"] = True
        result["video"] = {
            "title": vs.title,
            "duration_seconds": vs.total_duration_seconds,
            "panels_count": len(vs.panels),
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

    return result
