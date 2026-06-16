"""Scene-level preparation before writing a chapter in the sequential path.

Extracted verbatim from BatchChapterGenerator._run_batch_sequential, which
inlined three steps between enhancement-context assembly and the chapter
write call:

1. scene beats for climax/twist chapters, appended to the enhancement
   context (Fix #12);
2. optional scene decomposition (3-5 scenes per chapter, behind the
   ``enable_scene_decomposition`` flag);
3. optional per-beat chapter writing (behind ``enable_scene_beat_writing``;
   incompatible with stream mode) — on success the chapter is fully written
   here and the normal write call is skipped.

All three steps are best-effort: failures log a warning and the caller
falls back to the standard write path.
"""

from __future__ import annotations

import logging

from models.schemas import Chapter

logger = logging.getLogger(__name__)


def prepare_scene_context_and_beat_chapter(
    batch_gen,
    *,
    outline,
    characters,
    world,
    genre,
    title,
    style,
    word_count,
    story_context,
    enhancement_context,
    stream_callback,
    idea: str = "",
    idea_summary: str = "",
) -> tuple[str, list[dict], Chapter | None]:
    """Run scene-beat and decomposition prep for one sequential chapter.

    Args:
        batch_gen: The BatchChapterGenerator instance (source of llm,
            config and the layer model tier).
        outline: ChapterOutline being written.
        characters / world / genre / title / style / word_count: Story
            inputs forwarded to beat generation and beat writing.
        story_context: Live StoryContext (recent summaries feed the beat
            writer's context).
        enhancement_context: Enhancement context built so far; scene beats
            are appended to it.
        stream_callback: Stream callback if streaming — disables per-beat
            writing.
        idea / idea_summary: Original idea passthrough for beat writing.

    Returns:
        Tuple of (enhancement_context, chapter_scenes, beat_chapter).
        *beat_chapter* is a fully written Chapter when per-beat writing
        succeeded, else None and the caller writes the chapter normally.
    """
    # Append scene beats for climax/twist chapters (Fix #12)
    from pipeline.layer1_story.scene_beat_generator import (
        generate_scene_beats,
        format_beats_for_prompt,
    )

    scene_beats_list = generate_scene_beats(
        batch_gen.llm,
        outline,
        characters,
        world,
        genre,
        model_tier=batch_gen.gen._layer_model or "cheap",
    )
    if scene_beats_list:
        scene_beats_text = format_beats_for_prompt(scene_beats_list)
        enhancement_context = (
            f"{enhancement_context}\n\n{scene_beats_text}"
            if enhancement_context
            else scene_beats_text
        )

    # Scene decomposition: decompose chapter into 3-5 scenes before writing
    chapter_scenes: list[dict] = []
    if getattr(batch_gen.config.pipeline, "enable_scene_decomposition", False):
        try:
            from pipeline.layer1_story.scene_decomposer import (
                decompose_chapter_scenes,
            )

            chapter_scenes = decompose_chapter_scenes(
                batch_gen.llm,
                outline,
                characters,
                world,
                genre,
                model=batch_gen.gen._layer_model,
            )
        except Exception as e:
            logger.warning(
                "Scene decomposition failed for ch%d (non-fatal): %s",
                outline.chapter_number,
                e,
            )

    # Scene beat writing: per-beat generation when enabled
    beat_chapter: Chapter | None = None
    use_beat_writing = (
        getattr(batch_gen.config.pipeline, "enable_scene_beat_writing", False)
        and scene_beats_list
        and not stream_callback  # stream mode not compatible
    )

    if use_beat_writing:
        try:
            from pipeline.layer1_story.chapter_writer import (
                write_chapter_by_beats,
            )

            beat_context = {
                "previous_summary": "\n".join(story_context.recent_summaries[-2:]),
                "characters_text": ", ".join(c.name for c in characters[:5]),
                "world_text": getattr(world, "setting", "") if world else "",
            }
            chapter_content = write_chapter_by_beats(
                batch_gen.llm,
                scene_beats_list,
                beat_context,
                title,
                genre,
                style,
                word_count,
                model=batch_gen.gen._layer_model,
                idea=idea,
                idea_summary=idea_summary,
            )
            from models.schemas import count_words

            beat_chapter = Chapter(
                chapter_number=outline.chapter_number,
                title=outline.title,
                content=chapter_content,
                word_count=count_words(chapter_content),
            )
        except Exception as e:
            logger.warning(
                "Beat writing failed for ch%d, falling back: %s",
                outline.chapter_number,
                e,
            )

    return enhancement_context, chapter_scenes, beat_chapter
