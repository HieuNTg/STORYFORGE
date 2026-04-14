"""Continue-story logic: outline generation and chapter loop for story continuation."""

import logging
from concurrent.futures import ThreadPoolExecutor

from models.schemas import ChapterOutline, StoryDraft
from services import prompts
from pipeline.layer1_story.post_processing import process_chapter_post_write

logger = logging.getLogger(__name__)


def generate_continuation_outlines(
    generator,
    draft: StoryDraft,
    additional_chapters: int = 5,
    progress_callback=None,
) -> list[ChapterOutline]:
    """Generate outlines for continuation without writing chapters.

    Returns list of ChapterOutline objects that can be edited by user before writing.
    """
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

    _macro_arcs = getattr(draft, 'macro_arcs', None) or []
    macro_arcs_text = "\n".join(
        f"- Arc {getattr(a, 'arc_number', i+1)}: {getattr(a, 'title', 'N/A')} "
        f"(ch.{getattr(a, 'start_chapter', '?')}-{getattr(a, 'end_chapter', '?')}): "
        f"{getattr(a, 'description', '')}"
        for i, a in enumerate(_macro_arcs)
    ) or "N/A"
    _conflict_web = getattr(draft, 'conflict_web', None) or []
    conflict_web_text = "\n".join(
        f"- {getattr(c, 'parties', 'N/A')}: {getattr(c, 'description', '')} "
        f"[status={getattr(c, 'status', 'active')}, arc {getattr(c, 'arc_range', 'N/A')}]"
        for c in _conflict_web
    ) or "N/A"
    _foreshadowing = getattr(draft, 'foreshadowing_plan', None) or []
    foreshadowing_text = "\n".join(
        f"- {getattr(f, 'description', '')}: plant ch.{getattr(f, 'plant_chapter', '?')}, "
        f"payoff ch.{getattr(f, 'payoff_chapter', '?')} "
        f"[planted={getattr(f, 'planted', False)}, paid_off={getattr(f, 'paid_off', False)}]"
        for f in _foreshadowing
    ) or "N/A"
    _open_threads = getattr(draft, 'open_threads', None) or []
    threads_text = "\n".join(
        f"- {t.thread_id}: {t.description} [status={t.status}, planted ch.{t.planted_chapter}]"
        for t in _open_threads if t.status != "resolved"
    ) or "N/A"

    result = generator.llm.generate_json(
        system_prompt="Bạn là biên kịch tài năng viết truyện bằng tiếng Việt. BẮT BUỘC: Toàn bộ output phải viết bằng tiếng Việt, không được dùng ngôn ngữ khác. Trả về JSON.",
        user_prompt=prompts.CONTINUE_OUTLINE.format(
            genre=draft.genre, title=draft.title,
            characters=chars_text, world=world_text,
            existing_chapters=len(draft.chapters),
            synopsis=draft.synopsis,
            existing_outlines=existing_outlines_text,
            macro_arcs=macro_arcs_text,
            conflict_web=conflict_web_text,
            foreshadowing_plan=foreshadowing_text,
            open_threads=threads_text,
            character_states=states_text,
            plot_events=events_text,
            additional_chapters=additional_chapters,
            start_chapter=start_chapter,
        ),
        temperature=0.9,
        model=generator._layer_model,
    )
    outlines = [ChapterOutline(**o) for o in result.get("outlines", [])]
    _log(f"Generated {len(outlines)} outlines.")
    return outlines


def write_from_outlines(
    generator,
    draft: StoryDraft,
    outlines: list[ChapterOutline],
    word_count: int = 2000,
    style: str = "",
    progress_callback=None,
    stream_callback=None,
) -> StoryDraft:
    """Write chapters from pre-generated (possibly user-edited) outlines.

    Does not generate new outlines - uses provided ones directly.
    """
    if not outlines:
        return draft

    context_window = generator.config.pipeline.context_window_chapters
    effective_style = style or generator.config.pipeline.writing_style

    def _log(msg):
        logger.info(msg)
        if progress_callback:
            progress_callback(msg)

    # Add outlines to draft
    draft.outlines.extend(outlines)
    story_context = generator.rebuild_context(draft)
    all_chapter_texts = [ch.content for ch in draft.chapters if ch.content]
    final_total = len(draft.chapters) + len(outlines)
    self_reviewer = generator._get_self_reviewer() if generator.config.pipeline.enable_self_review else None

    macro_arcs = getattr(draft, 'macro_arcs', None) or []
    conflict_web = getattr(draft, 'conflict_web', None) or []
    foreshadowing_plan = getattr(draft, 'foreshadowing_plan', None) or []
    premise = getattr(draft, "premise", None) or {}
    voice_profiles = getattr(draft, "voice_profiles", None) or []

    _log(f"Writing {len(outlines)} chapters from provided outlines...")

    with ThreadPoolExecutor(max_workers=3) as executor:
        for outline in outlines:
            story_context.current_chapter = outline.chapter_number
            story_context.total_chapters = final_total

            # Resolve per-chapter narrative context
            active_conflicts = []
            seeds = []
            payoffs = []
            pacing = ""
            try:
                from pipeline.layer1_story.macro_outline_builder import get_arc_for_chapter
                from pipeline.layer1_story.conflict_web_builder import get_active_conflicts
                from pipeline.layer1_story.foreshadowing_manager import get_seeds_to_plant, get_payoffs_due
                from pipeline.layer1_story.pacing_controller import validate_pacing
                current_arc = get_arc_for_chapter(macro_arcs, outline.chapter_number)
                arc_num = current_arc.arc_number if current_arc else 1
                active_conflicts = get_active_conflicts(conflict_web, arc_num)
                seeds = get_seeds_to_plant(foreshadowing_plan, outline.chapter_number)
                payoffs = get_payoffs_due(foreshadowing_plan, outline.chapter_number)
                pacing = validate_pacing(getattr(outline, "pacing_type", "") or "")
            except Exception as e:
                logger.warning("Narrative context resolution failed for ch%d: %s", outline.chapter_number, e)

            # Build enhancement context
            enhancement_context = ""
            try:
                from pipeline.layer1_story.enhancement_context_builder import build_enhancement_context
                enhancement_context = build_enhancement_context(
                    config=generator.config, llm=generator.llm,
                    genre=draft.genre, pacing=pacing,
                    premise=premise, voice_profiles=voice_profiles,
                    outline=outline, characters=draft.characters,
                    world=draft.world, layer_model=generator._layer_model,
                )
            except Exception as e:
                logger.debug("Enhancement context build failed for ch%d: %s", outline.chapter_number, e)

            _log(f"Writing chapter {outline.chapter_number}: {outline.title}...")
            if stream_callback:
                chapter = generator.write_chapter_stream(
                    draft.title, draft.genre, effective_style,
                    draft.characters, draft.world, outline,
                    word_count=word_count, context=story_context,
                    stream_callback=stream_callback,
                    open_threads=list(story_context.open_threads),
                    active_conflicts=active_conflicts,
                    foreshadowing_to_plant=seeds,
                    foreshadowing_to_payoff=payoffs,
                    pacing_type=pacing,
                    enhancement_context=enhancement_context,
                )
            else:
                chapter = generator._write_chapter_with_long_context(
                    draft.title, draft.genre, effective_style,
                    draft.characters, draft.world, outline,
                    word_count, story_context, all_chapter_texts,
                    open_threads=list(story_context.open_threads),
                    active_conflicts=active_conflicts,
                    foreshadowing_to_plant=seeds,
                    foreshadowing_to_payoff=payoffs,
                    pacing_type=pacing,
                    enhancement_context=enhancement_context,
                )
            draft.chapters.append(chapter)
            all_chapter_texts.append(chapter.content)
            _log(f"Extracting context for chapter {outline.chapter_number}...")
            process_chapter_post_write(
                chapter, outline, story_context, draft.characters, context_window,
                executor, generator.llm,
                draft, generator.bible_manager,
                progress_callback, draft.genre, word_count,
                generator.config.pipeline.enable_self_review, self_reviewer,
                open_threads=list(story_context.open_threads),
                foreshadowing_plan=foreshadowing_plan,
                world_rules=getattr(draft.world, 'rules', None) or [],
                voice_profiles=voice_profiles,
            )

    draft.character_states = list(story_context.character_states)
    draft.plot_events = list(story_context.plot_events)
    draft.open_threads = list(story_context.open_threads)
    if story_context.conflict_map:
        draft.conflict_web = list(story_context.conflict_map)
    _log(f"Writing complete — {len(outlines)} chapters added!")
    return draft


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
    This is a convenience wrapper that generates outlines and writes chapters in one step.
    For two-step flow (preview → edit → write), use generate_continuation_outlines + write_from_outlines.
    """
    # Step 1: Generate outlines
    new_outlines = generate_continuation_outlines(
        generator, draft, additional_chapters, progress_callback
    )
    if not new_outlines:
        if progress_callback:
            progress_callback("No outlines generated. Aborting continuation.")
        return draft

    # Step 2: Write chapters from outlines
    return write_from_outlines(
        generator, draft, new_outlines, word_count, style, progress_callback, stream_callback
    )


def regenerate_chapter_impl(
    generator,
    draft: StoryDraft,
    chapter_number: int,
    word_count: int = 2000,
    style: str = "",
    preserve_outline: bool = True,
    progress_callback=None,
    stream_callback=None,
) -> StoryDraft:
    """Regenerate a specific chapter without affecting subsequent chapters.

    `generator` is a StoryGenerator instance (passed to avoid circular import).
    """
    context_window = generator.config.pipeline.context_window_chapters
    effective_style = style or generator.config.pipeline.writing_style

    def _log(msg):
        logger.info(msg)
        if progress_callback:
            progress_callback(msg)

    # Get outline for this chapter
    chapter_idx = chapter_number - 1
    if chapter_idx >= len(draft.outlines):
        raise ValueError(f"No outline for chapter {chapter_number}")
    outline = draft.outlines[chapter_idx]

    _log(f"Regenerating chapter {chapter_number}: {outline.title}...")

    # Rebuild context from chapters BEFORE this one
    story_context = generator.rebuild_context(draft)
    # Limit context to chapters before target
    story_context.recent_summaries = [
        ch.summary for ch in draft.chapters[:chapter_idx]
        if ch.summary
    ][-context_window:]
    story_context.current_chapter = chapter_number
    story_context.total_chapters = len(draft.chapters)

    # Get narrative context for this chapter
    macro_arcs = getattr(draft, 'macro_arcs', None) or []
    conflict_web = getattr(draft, 'conflict_web', None) or []
    foreshadowing_plan = getattr(draft, 'foreshadowing_plan', None) or []
    premise = getattr(draft, 'premise', None) or {}
    voice_profiles = getattr(draft, 'voice_profiles', None) or []

    active_conflicts = []
    seeds = []
    payoffs = []
    pacing = ""
    try:
        from pipeline.layer1_story.macro_outline_builder import get_arc_for_chapter
        from pipeline.layer1_story.conflict_web_builder import get_active_conflicts
        from pipeline.layer1_story.foreshadowing_manager import get_seeds_to_plant, get_payoffs_due
        from pipeline.layer1_story.pacing_controller import validate_pacing
        current_arc = get_arc_for_chapter(macro_arcs, chapter_number)
        arc_num = current_arc.arc_number if current_arc else 1
        active_conflicts = get_active_conflicts(conflict_web, arc_num)
        seeds = get_seeds_to_plant(foreshadowing_plan, chapter_number)
        payoffs = get_payoffs_due(foreshadowing_plan, chapter_number)
        pacing = validate_pacing(getattr(outline, 'pacing_type', '') or '')
    except Exception as e:
        logger.warning("Narrative context resolution failed for ch%d: %s", chapter_number, e)

    # Build enhancement context
    enhancement_context = ""
    try:
        from pipeline.layer1_story.enhancement_context_builder import build_enhancement_context
        enhancement_context = build_enhancement_context(
            config=generator.config, llm=generator.llm,
            genre=draft.genre, pacing=pacing,
            premise=premise, voice_profiles=voice_profiles,
            outline=outline, characters=draft.characters,
            world=draft.world, layer_model=generator._layer_model,
        )
    except Exception as e:
        logger.debug("Enhancement context build failed for ch%d: %s", chapter_number, e)

    # Write the chapter
    all_chapter_texts = [ch.content for ch in draft.chapters[:chapter_idx] if ch.content]
    if stream_callback:
        chapter = generator.write_chapter_stream(
            draft.title, draft.genre, effective_style,
            draft.characters, draft.world, outline,
            word_count=word_count, context=story_context,
            stream_callback=stream_callback,
            open_threads=list(story_context.open_threads),
            active_conflicts=active_conflicts,
            foreshadowing_to_plant=seeds,
            foreshadowing_to_payoff=payoffs,
            pacing_type=pacing,
            enhancement_context=enhancement_context,
        )
    else:
        chapter = generator._write_chapter_with_long_context(
            draft.title, draft.genre, effective_style,
            draft.characters, draft.world, outline,
            word_count, story_context, all_chapter_texts,
            open_threads=list(story_context.open_threads),
            active_conflicts=active_conflicts,
            foreshadowing_to_plant=seeds,
            foreshadowing_to_payoff=payoffs,
            pacing_type=pacing,
            enhancement_context=enhancement_context,
        )

    # Replace the chapter in draft
    draft.chapters[chapter_idx] = chapter

    # Run post-processing to update context
    self_reviewer = generator._get_self_reviewer() if generator.config.pipeline.enable_self_review else None
    with ThreadPoolExecutor(max_workers=3) as executor:
        process_chapter_post_write(
            chapter, outline, story_context, draft.characters, context_window,
            executor, generator.llm,
            draft, generator.bible_manager,
            progress_callback, draft.genre, word_count,
            generator.config.pipeline.enable_self_review, self_reviewer,
            open_threads=list(story_context.open_threads),
            foreshadowing_plan=foreshadowing_plan,
            world_rules=getattr(draft.world, 'rules', None) or [],
            voice_profiles=voice_profiles,
        )

    _log(f"Chapter {chapter_number} regenerated successfully!")
    return draft
