"""Pipeline utility functions for reliability, validation, and caching.

Contains:
- LLM retry helper with fail-fast for critical paths (Bug #1)
- Draft integrity validator for L1→L2 handoff (Bug #2)
- Summary/plot_events cache (Bug #8)
- Emotional whiplash detector (Bug #11)
"""

import hashlib
import logging
import time
from typing import Callable, TypeVar, Optional

logger = logging.getLogger(__name__)

T = TypeVar('T')

# ══════════════════════════════════════════════════════════════════════════════
# Bug #1: LLM Retry Helper with fail-fast for critical paths
# ══════════════════════════════════════════════════════════════════════════════


class LLMCallError(Exception):
    """Raised when LLM call fails after all retries."""
    pass


def llm_call_with_retry(
    fn: Callable[[], T],
    max_retries: int = 2,
    backoff_base: float = 1.5,
    critical: bool = False,
    operation_name: str = "LLM call",
) -> T:
    """Execute LLM call with retry logic.

    Args:
        fn: Zero-arg callable that performs the LLM call
        max_retries: Max retry attempts (default 2)
        backoff_base: Exponential backoff multiplier
        critical: If True, raises LLMCallError on failure; if False, returns None
        operation_name: Name for logging

    Returns:
        Result of fn() on success

    Raises:
        LLMCallError: If critical=True and all retries exhausted
    """
    delay = 1.0
    last_error = None

    for attempt in range(max_retries + 1):
        try:
            return fn()
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                logger.warning(
                    "%s attempt %d/%d failed: %s, retrying in %.1fs",
                    operation_name, attempt + 1, max_retries + 1, str(e)[:100], delay
                )
                time.sleep(delay)
                delay *= backoff_base
            else:
                logger.error(
                    "%s failed after %d attempts: %s",
                    operation_name, max_retries + 1, str(e)[:200]
                )

    if critical:
        raise LLMCallError(f"{operation_name} failed: {last_error}")
    return None


# ══════════════════════════════════════════════════════════════════════════════
# Bug #2: Draft Integrity Validator for L1→L2 handoff
# ══════════════════════════════════════════════════════════════════════════════


class DraftIntegrityError(Exception):
    """Raised when draft fails integrity checks."""
    pass


def verify_draft_integrity(
    draft,
    require_chapters: bool = True,
    require_outlines: bool = True,
    require_characters: bool = True,
    min_chapters: int = 1,
    raise_on_error: bool = False,
) -> dict:
    """Validate draft integrity before L2 processing.

    Checks:
    - chapters.len == outlines.len (if both present)
    - All chapter summaries non-empty
    - character_states present
    - No null/empty critical fields

    Args:
        draft: StoryDraft to validate
        require_chapters: Fail if no chapters
        require_outlines: Fail if no outlines
        require_characters: Fail if no characters
        min_chapters: Minimum required chapters
        raise_on_error: Raise DraftIntegrityError on first critical issue

    Returns:
        dict with 'valid' bool, 'errors' list, 'warnings' list
    """
    errors = []
    warnings = []

    chapters = getattr(draft, 'chapters', []) or []
    outlines = getattr(draft, 'outlines', []) or []
    characters = getattr(draft, 'characters', []) or []

    # Critical checks
    if require_chapters and len(chapters) < min_chapters:
        errors.append(f"Draft has {len(chapters)} chapters, need >= {min_chapters}")

    if require_outlines and not outlines:
        errors.append("Draft has no outlines")

    if require_characters and not characters:
        errors.append("Draft has no characters")

    # Consistency checks
    if chapters and outlines and len(chapters) != len(outlines):
        errors.append(
            f"Chapter/outline count mismatch: {len(chapters)} chapters vs {len(outlines)} outlines"
        )

    # Content quality checks
    empty_summaries = sum(1 for ch in chapters if not getattr(ch, 'summary', ''))
    if empty_summaries > 0:
        warnings.append(f"{empty_summaries}/{len(chapters)} chapters have empty summaries")

    empty_content = sum(1 for ch in chapters if not getattr(ch, 'content', ''))
    if empty_content > 0:
        errors.append(f"{empty_content}/{len(chapters)} chapters have empty content")

    # Character state check
    char_states = getattr(draft, 'character_states', []) or []
    if chapters and not char_states:
        warnings.append("No character states extracted from chapters")

    # Plot events check
    plot_events = getattr(draft, 'plot_events', []) or []
    if len(chapters) > 2 and not plot_events:
        warnings.append("No plot events extracted from chapters")

    result = {
        'valid': len(errors) == 0,
        'errors': errors,
        'warnings': warnings,
        'chapter_count': len(chapters),
        'outline_count': len(outlines),
        'character_count': len(characters),
    }

    if raise_on_error and errors:
        raise DraftIntegrityError("; ".join(errors))

    if errors:
        logger.warning("Draft integrity issues: %s", "; ".join(errors))
    if warnings:
        logger.info("Draft integrity warnings: %s", "; ".join(warnings))

    return result


# ══════════════════════════════════════════════════════════════════════════════
# Bug #8: Summary/Plot Events Cache
# ══════════════════════════════════════════════════════════════════════════════


class ChapterExtractionCache:
    """Thread-safe cache for chapter summaries and plot events.

    Prevents re-computation when resuming from checkpoint or retrying.
    Cache key: (chapter_number, content_hash)
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._summaries = {}
            cls._instance._plot_events = {}
        return cls._instance

    @staticmethod
    def _content_hash(content: str) -> str:
        """Full-content SHA-256 hash. Truncated md5(first 5KB) caused stale-cache
        bugs because rewrites target chapter tails (payoffs/endings) and would
        not invalidate the cached pre-rewrite summary."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def get_summary(self, chapter_number: int, content: str) -> Optional[str]:
        """Get cached summary if exists."""
        key = (chapter_number, self._content_hash(content))
        return self._summaries.get(key)

    def set_summary(self, chapter_number: int, content: str, summary: str) -> None:
        """Cache summary."""
        key = (chapter_number, self._content_hash(content))
        self._summaries[key] = summary

    def get_plot_events(self, chapter_number: int, content: str) -> Optional[list]:
        """Get cached plot events if exists."""
        key = (chapter_number, self._content_hash(content))
        return self._plot_events.get(key)

    def set_plot_events(self, chapter_number: int, content: str, events: list) -> None:
        """Cache plot events."""
        key = (chapter_number, self._content_hash(content))
        self._plot_events[key] = events

    def clear(self) -> None:
        """Clear all caches."""
        self._summaries.clear()
        self._plot_events.clear()


# ══════════════════════════════════════════════════════════════════════════════
# Bug #11: Emotional Whiplash Detector
# ══════════════════════════════════════════════════════════════════════════════


EMOTION_VALENCE = {
    # Positive emotions
    'vui': 0.8, 'hạnh phúc': 0.9, 'phấn khích': 0.7, 'hy vọng': 0.6,
    'yêu thương': 0.8, 'bình yên': 0.5, 'hài lòng': 0.6, 'tự hào': 0.7,
    'phấn khởi': 0.7, 'hân hoan': 0.9, 'lạc quan': 0.6, 'thư giãn': 0.4,
    # Negative emotions
    'buồn': -0.7, 'đau khổ': -0.9, 'tuyệt vọng': -1.0, 'giận dữ': -0.8,
    'sợ hãi': -0.7, 'lo âu': -0.5, 'ghen tị': -0.4, 'xấu hổ': -0.5,
    'thất vọng': -0.6, 'cô đơn': -0.6, 'hận thù': -0.9, 'bi thương': -0.8,
    # Neutral/mixed
    'bất ngờ': 0.0, 'ngạc nhiên': 0.0, 'căng thẳng': -0.3, 'hồi hộp': 0.1,
    'mơ hồ': 0.0, 'hoang mang': -0.2, 'quyết tâm': 0.3, 'kiên định': 0.3,
}


def detect_emotional_whiplash(
    emotional_history: list[str],
    threshold: float = 1.2,
    window: int = 3,
) -> list[dict]:
    """Detect emotional whiplash (jarring emotional transitions).

    Args:
        emotional_history: List of emotion descriptors per chapter
        threshold: Valence swing threshold (0-2 scale)
        window: Number of chapters to analyze

    Returns:
        List of whiplash events: [{chapter_from, chapter_to, emotion_from, emotion_to, swing}]
    """
    if len(emotional_history) < 2:
        return []

    whiplash_events = []
    recent = emotional_history[-window:] if len(emotional_history) > window else emotional_history

    for i in range(1, len(recent)):
        prev_emotion = recent[i - 1].lower().strip()
        curr_emotion = recent[i].lower().strip()

        # Get valence scores (default to 0 for unknown emotions)
        prev_valence = EMOTION_VALENCE.get(prev_emotion, 0.0)
        curr_valence = EMOTION_VALENCE.get(curr_emotion, 0.0)

        # Calculate swing (absolute change)
        swing = abs(curr_valence - prev_valence)

        if swing >= threshold:
            chapter_offset = len(emotional_history) - len(recent)
            whiplash_events.append({
                'chapter_from': chapter_offset + i,
                'chapter_to': chapter_offset + i + 1,
                'emotion_from': prev_emotion,
                'emotion_to': curr_emotion,
                'valence_from': prev_valence,
                'valence_to': curr_valence,
                'swing': swing,
            })

    return whiplash_events


def format_whiplash_warning(events: list[dict]) -> str:
    """Format whiplash events as warning text for prompts."""
    if not events:
        return ""

    lines = ["## ⚠️ CẢNH BÁO EMOTIONAL WHIPLASH:"]
    for ev in events[:3]:  # Limit to 3 warnings
        direction = "↑" if ev['valence_to'] > ev['valence_from'] else "↓"
        lines.append(
            f"- Ch{ev['chapter_from']}→{ev['chapter_to']}: "
            f"{ev['emotion_from']} {direction} {ev['emotion_to']} "
            f"(swing={ev['swing']:.1f})"
        )
    lines.append("Cân nhắc thêm cảnh chuyển tiếp cảm xúc mềm mại hơn.")
    return "\n".join(lines)


def get_emotional_momentum(emotional_history: list[str], window: int = 3) -> str:
    """Calculate current emotional momentum for prompt injection.

    Returns: 'ascending' | 'descending' | 'plateau' | 'volatile'
    """
    if len(emotional_history) < 2:
        return "plateau"

    recent = emotional_history[-window:] if len(emotional_history) > window else emotional_history
    valences = [EMOTION_VALENCE.get(e.lower().strip(), 0.0) for e in recent]

    # Calculate trend
    diffs = [valences[i] - valences[i-1] for i in range(1, len(valences))]

    if not diffs:
        return "plateau"

    avg_diff = sum(diffs) / len(diffs)
    variance = sum((d - avg_diff) ** 2 for d in diffs) / len(diffs)

    if variance > 0.5:
        return "volatile"
    elif avg_diff > 0.2:
        return "ascending"
    elif avg_diff < -0.2:
        return "descending"
    else:
        return "plateau"
