"""Post-chapter processing: self-review, parallel extraction, context & bible updates."""

import logging
from concurrent.futures import ThreadPoolExecutor

from models.schemas import ChapterOutline, Chapter, StoryDraft, StoryContext, count_words

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
    # NEW:
    open_threads=None,
    foreshadowing_plan=None,
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
                    f"Chương {outline.chapter_number} đã được cải thiện "
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
            prev = existing.get(s.name)
            if prev:
                # Accumulate knowledge and relationship changes across chapters
                seen_knowledge = set(prev.cumulative_knowledge)
                merged_knowledge = list(prev.cumulative_knowledge)
                for k in s.knowledge:
                    if k and k not in seen_knowledge:
                        merged_knowledge.append(k)
                        seen_knowledge.add(k)
                seen_rels = set(prev.cumulative_relationships)
                merged_rels = list(prev.cumulative_relationships)
                for r in s.relationship_changes:
                    if r and r not in seen_rels:
                        merged_rels.append(r)
                        seen_rels.add(r)
                # Keep last 20 each to prevent unbounded growth
                s.cumulative_knowledge = merged_knowledge[-20:]
                s.cumulative_relationships = merged_rels[-20:]
            else:
                s.cumulative_knowledge = list(s.knowledge)
                s.cumulative_relationships = list(s.relationship_changes)
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

    # --- New narrative tracking (non-fatal, sequential) ---

    # Structured summary extraction
    try:
        from pipeline.layer1_story.structured_summary_extractor import extract_structured_summary
        structured, brief = extract_structured_summary(
            llm, chapter.content, outline.chapter_number,
            open_threads or [],
        )
        chapter.structured_summary = structured
        if brief:
            chapter.summary = brief  # override basic summary with structured brief
    except Exception as e:
        logger.warning(f"Structured summary extraction failed: {e}")

    # Plot thread tracking
    try:
        from pipeline.layer1_story.plot_thread_tracker import extract_plot_threads, update_threads
        thread_result = extract_plot_threads(
            llm, chapter.content, outline.chapter_number,
            open_threads or [],
        )
        updated_threads = update_threads(
            open_threads or [], thread_result, outline.chapter_number,
        )
        story_context.open_threads = updated_threads
    except Exception as e:
        logger.warning(f"Plot thread tracking failed: {e}")

    # Conflict status update (heuristic, no LLM call)
    try:
        from pipeline.layer1_story.conflict_web_builder import update_conflict_status
        if story_context.conflict_map:
            update_conflict_status(
                story_context.conflict_map, chapter.content, outline.chapter_number,
            )
    except Exception as e:
        logger.warning(f"Conflict status update failed: {e}")

    # Mark foreshadowing as planted/paid off
    try:
        from pipeline.layer1_story.foreshadowing_manager import mark_planted, mark_paid_off
        if foreshadowing_plan:
            mark_planted(foreshadowing_plan, outline.chapter_number)
            mark_paid_off(foreshadowing_plan, outline.chapter_number)
    except Exception as e:
        logger.warning(f"Foreshadowing tracking failed: {e}")

    # Pacing history tracking
    story_context.pacing_history.append(getattr(outline, "pacing_type", None) or "rising")
    story_context.pacing_history = story_context.pacing_history[-10:]

    return chapter, summary, new_states, new_events
