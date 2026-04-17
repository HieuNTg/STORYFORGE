"""Context-health tracking for post-chapter extractions.

Wrap every extraction call in `tracked_extraction(...)`. The contextmanager
records success/failure + duration into `story_context.extraction_health`
so the orchestrator circuit-breaker can halt the pipeline when corruption
crosses threshold, instead of silently continuing on empty fallback state.
"""
from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Iterator

from models.schemas import ExtractionHealth, StoryContext

logger = logging.getLogger(__name__)

_HEALTH_CAP = 200  # retain last N records to bound memory


@contextmanager
def tracked_extraction(
    story_context: StoryContext,
    chapter_num: int,
    extraction_type: str,
    *,
    swallow: bool = True,
) -> Iterator[ExtractionHealth]:
    """Track an extraction attempt.

    Args:
        story_context: target StoryContext; health record appended in-place.
        chapter_num: chapter number this extraction belongs to.
        extraction_type: identifier (e.g. "summary", "character_states").
        swallow: if True (default) swallow exceptions after recording so
            callers can keep their existing empty-fallback flow. If False
            re-raise so callers can decide.

    Yields:
        The ExtractionHealth record (not yet finalized).
    """
    start = time.time()
    record = ExtractionHealth(
        chapter_number=chapter_num,
        extraction_type=extraction_type,
    )
    try:
        yield record
        record.success = True
    except Exception as exc:  # noqa: BLE001 — tracking everything is the point
        record.success = False
        record.error = str(exc)[:200]
        logger.warning(
            "[EXTRACTION] ch%s %s failed: %s", chapter_num, extraction_type, exc
        )
        if not swallow:
            raise
    finally:
        record.duration_ms = int((time.time() - start) * 1000)
        story_context.extraction_health.append(record)
        if len(story_context.extraction_health) > _HEALTH_CAP:
            story_context.extraction_health = story_context.extraction_health[-_HEALTH_CAP:]
