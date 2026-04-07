"""Continue-story logic: outline generation and chapter loop for story continuation."""

import logging
from concurrent.futures import ThreadPoolExecutor

from models.schemas import ChapterOutline, StoryDraft
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

    # Format structural context for outline generation
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
    new_outlines = [ChapterOutline(**o) for o in result.get("outlines", [])]
    if not new_outlines:
        _log("No outlines generated. Aborting continuation.")
        return draft

    draft.outlines.extend(new_outlines)
    story_context = generator.rebuild_context(draft)
    all_chapter_texts = [ch.content for ch in draft.chapters if ch.content]
    final_total = len(draft.chapters) + len(new_outlines)
    self_reviewer = generator._get_self_reviewer() if generator.config.pipeline.enable_self_review else None

    # NOTE (async-migration): ThreadPoolExecutor is kept here intentionally.
    # The executor is passed to process_chapter_post_write which runs three LLM extraction
    # tasks (summarize, extract_character_states, extract_plot_events) in parallel while the
    # main loop moves to the next chapter. The pattern requires a long-lived executor shared
    # across the sequential chapter loop. Migration to asyncio requires an async LLMClient
    # (future work, see async-migration-plan.md #5).
    macro_arcs = getattr(draft, 'macro_arcs', None) or []
    conflict_web = getattr(draft, 'conflict_web', None) or []
    foreshadowing_plan = getattr(draft, 'foreshadowing_plan', None) or []

    with ThreadPoolExecutor(max_workers=3) as executor:
        for outline in new_outlines:
            story_context.current_chapter = outline.chapter_number
            story_context.total_chapters = final_total

            # Resolve per-chapter narrative context (same as full pipeline)
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
                )
            draft.chapters.append(chapter)
            all_chapter_texts.append(chapter.content)
            _log(f"Extracting context for chapter {outline.chapter_number}...")
            process_chapter_post_write(
                chapter, outline, story_context, draft.characters, context_window,
                executor, generator.llm,
                bool(draft.story_bible),
                draft, generator.bible_manager,
                progress_callback, draft.genre, word_count,
                generator.config.pipeline.enable_self_review, self_reviewer,
                open_threads=list(story_context.open_threads),
                foreshadowing_plan=foreshadowing_plan,
            )

    draft.character_states = list(story_context.character_states)
    draft.plot_events = list(story_context.plot_events)
    draft.open_threads = list(story_context.open_threads)
    # Sync conflict web status back to draft after new chapters
    if story_context.conflict_map:
        draft.conflict_web = list(story_context.conflict_map)
    _log(f"Continuation complete — {len(new_outlines)} chapters added!")
    return draft
