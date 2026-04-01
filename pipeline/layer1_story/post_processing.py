"""Post-chapter processing: self-review, parallel extraction, context & bible updates."""

import logging
from concurrent.futures import ThreadPoolExecutor

from models.schemas import Character, ChapterOutline, Chapter, StoryDraft, StoryContext, count_words

if __name__ == "__main__":
    pass  # not a script

logger = logging.getLogger(__name__)


def _prune_plot_events(events: list) -> list:
    """Smart prune: keep recent 30 + top-20 older by event length. Cap 50."""
    if len(events) <= 50:
        return events
    recent = events[-30:]
    older = sorted(events[:-30], key=lambda e: len(e.event), reverse=True)[:20]
    return older + recent


def process_chapter_post_write(
    chapter: Chapter,
    outline: ChapterOutline,
    story_context: StoryContext,
    characters: list,
    context_window: int,
    executor: ThreadPoolExecutor,
    llm,
    bible_enabled: bool,
    draft: StoryDraft,
    bible_manager,
    progress_callback=None,
    genre: str = "",
    word_count: int = 2000,
    enable_self_review: bool = False,
    self_reviewer=None,
) -> tuple:
    """Shared post-write logic: self-review, parallel extraction, context update, bible update.

    Returns (chapter, summary, new_states, new_events) — also mutates story_context in place.
    """
    # Lazy imports for mock compat
    from pipeline.layer1_story.chapter_writer import summarize_chapter, extract_plot_events
    from pipeline.layer1_story.character_generator import extract_character_states

    # Optional self-review
    if enable_self_review and self_reviewer is not None:
        revised_content, review_scores = self_reviewer.review_and_revise(
            content=chapter.content,
            chapter_number=outline.chapter_number,
            title=outline.title,
            genre=genre,
            word_count=word_count,
        )
        if revised_content != chapter.content:
            if progress_callback:
                progress_callback(
                    f"Chuong {outline.chapter_number} da duoc cai thien "
                    f"(score: {review_scores['overall']:.1f})"
                )
            chapter.content = revised_content
            chapter.word_count = count_words(revised_content)

    # Parallel extraction
    summary_f = executor.submit(summarize_chapter, llm, chapter.content)
    states_f = executor.submit(extract_character_states, llm, chapter.content, characters)
    events_f = executor.submit(extract_plot_events, llm, chapter.content, outline.chapter_number)

    _TIMEOUT = 120
    try:
        summary = summary_f.result(timeout=_TIMEOUT)
    except Exception as e:
        logger.warning(f"Summary extraction failed: {e}")
        summary = ""
        summary_f.cancel()

    try:
        new_states = states_f.result(timeout=_TIMEOUT)
    except Exception as e:
        logger.warning(f"Character state extraction failed: {e}")
        new_states = []
        states_f.cancel()

    try:
        new_events = events_f.result(timeout=_TIMEOUT)
    except Exception as e:
        logger.warning(f"Plot event extraction failed: {e}")
        new_events = []
        events_f.cancel()

    # Update rolling context
    chapter.summary = summary
    story_context.recent_summaries.append(summary)
    story_context.recent_summaries = story_context.recent_summaries[-context_window:]

    if new_states:
        existing = {s.name: s for s in story_context.character_states}
        for s in new_states:
            existing[s.name] = s
        story_context.character_states = list(existing.values())

    story_context.plot_events.extend(new_events)
    story_context.plot_events = _prune_plot_events(story_context.plot_events)

    # Update Story Bible
    if bible_enabled and draft.story_bible:
        bible_manager.update_after_chapter(
            draft.story_bible, chapter,
            list(story_context.character_states), new_events,
        )

    return chapter, summary, new_states, new_events
