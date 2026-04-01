"""Continue-story logic: outline generation and chapter loop for story continuation."""

import logging
from concurrent.futures import ThreadPoolExecutor

from models.schemas import ChapterOutline, StoryDraft, StoryContext
from services import prompts
from pipeline.layer1_story.post_processing import process_chapter_post_write

logger = logging.getLogger(__name__)


def continue_story(
    generator,
    draft: StoryDraft,
    additional_chapters: int = 5,
    word_count: int = 2000,
    style: str = "",
    progress_callback=None,
    stream_callback=None,
) -> StoryDraft:
    """Continue writing from existing StoryDraft by adding more chapters.

    `generator` is a StoryGenerator instance (passed to avoid circular import).
    """
    context_window = generator.config.pipeline.context_window_chapters
    effective_style = style or generator.config.pipeline.writing_style

    def _log(msg):
        logger.info(msg)
        if progress_callback:
            progress_callback(msg)

    start_chapter = len(draft.chapters) + 1
    _log(f"Generating outlines for chapters {start_chapter}-{start_chapter + additional_chapters - 1}...")

    chars_text = "\n".join(
        f"- {c.name} ({c.role}): {c.personality}, Động lực: {c.motivation}"
        for c in draft.characters
    )
    existing_outlines_text = "\n".join(
        f"Ch.{o.chapter_number}: {o.title} — {o.summary}"
        for o in draft.outlines
    )
    states_text = "\n".join(
        f"- {s.name}: mood={s.mood}, arc={s.arc_position}, last={s.last_action}"
        for s in draft.character_states
    ) or "N/A"
    events_text = "\n".join(
        f"- Ch.{e.chapter_number}: {e.event}"
        for e in draft.plot_events[-20:]
    ) or "N/A"
    world_text = f"{draft.world.name}: {draft.world.description}" if draft.world else "N/A"

    result = generator.llm.generate_json(
        system_prompt="Bạn là biên kịch tài năng. Trả về JSON.",
        user_prompt=prompts.CONTINUE_OUTLINE.format(
            genre=draft.genre, title=draft.title,
            characters=chars_text, world=world_text,
            existing_chapters=len(draft.chapters),
            synopsis=draft.synopsis,
            existing_outlines=existing_outlines_text,
            character_states=states_text,
            plot_events=events_text,
            additional_chapters=additional_chapters,
            start_chapter=start_chapter,
        ),
        temperature=0.9,
        model=generator._layer_model,
    )
    new_outlines = [ChapterOutline(**o) for o in result.get("outlines", [])]
    if not new_outlines:
        _log("No outlines generated. Aborting continuation.")
        return draft

    draft.outlines.extend(new_outlines)
    story_context = generator.rebuild_context(draft)
    all_chapter_texts = [ch.content for ch in draft.chapters if ch.content]
    final_total = len(draft.chapters) + len(new_outlines)
    self_reviewer = generator._get_self_reviewer() if generator.config.pipeline.enable_self_review else None

    with ThreadPoolExecutor(max_workers=3) as executor:
        for outline in new_outlines:
            story_context.current_chapter = outline.chapter_number
            story_context.total_chapters = final_total
            _log(f"Writing chapter {outline.chapter_number}: {outline.title}...")
            if stream_callback:
                chapter = generator.write_chapter_stream(
                    draft.title, draft.genre, effective_style,
                    draft.characters, draft.world, outline,
                    word_count=word_count, context=story_context,
                    stream_callback=stream_callback,
                )
            else:
                chapter = generator._write_chapter_with_long_context(
                    draft.title, draft.genre, effective_style,
                    draft.characters, draft.world, outline,
                    word_count, story_context, all_chapter_texts,
                )
            draft.chapters.append(chapter)
            all_chapter_texts.append(chapter.content)
            _log(f"Extracting context for chapter {outline.chapter_number}...")
            process_chapter_post_write(
                chapter, outline, story_context, draft.characters, context_window,
                executor, generator.llm, False, draft, generator.bible_manager,
                progress_callback, draft.genre, word_count,
                generator.config.pipeline.enable_self_review, self_reviewer,
            )

    draft.character_states = list(story_context.character_states)
    draft.plot_events = list(story_context.plot_events)
    _log(f"Continuation complete — {len(new_outlines)} chapters added!")
    return draft
