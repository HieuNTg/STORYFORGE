"""Continue-story logic: outline generation and chapter loop for story continuation."""

import logging
from concurrent.futures import ThreadPoolExecutor

from models.schemas import Chapter, ChapterOutline, StoryDraft
from services import prompts
from pipeline.layer1_story.post_processing import process_chapter_post_write

logger = logging.getLogger(__name__)


def renumber_chapters(draft: StoryDraft, from_position: int, delta: int = 1) -> None:
    """Renumber chapters and all references from a position onward.

    Args:
        draft: StoryDraft to modify in-place
        from_position: Chapters with number >= this get incremented
        delta: Amount to increment (default 1 for insertion)
    """
    # Renumber chapters
    for ch in draft.chapters:
        if ch.chapter_number >= from_position:
            ch.chapter_number += delta

    # Renumber outlines
    for outline in draft.outlines:
        if outline.chapter_number >= from_position:
            outline.chapter_number += delta

    # Update plot_events chapter references
    for event in draft.plot_events:
        if event.chapter_number >= from_position:
            event.chapter_number += delta

    # Update foreshadowing plant/payoff chapters
    foreshadowing = getattr(draft, 'foreshadowing_plan', None) or []
    for f in foreshadowing:
        if hasattr(f, 'plant_chapter') and f.plant_chapter >= from_position:
            f.plant_chapter += delta
        if hasattr(f, 'payoff_chapter') and f.payoff_chapter >= from_position:
            f.payoff_chapter += delta

    # Update open_threads chapter references
    threads = getattr(draft, 'open_threads', None) or []
    for t in threads:
        if hasattr(t, 'planted_chapter') and t.planted_chapter >= from_position:
            t.planted_chapter += delta
        if hasattr(t, 'last_mentioned_chapter') and t.last_mentioned_chapter >= from_position:
            t.last_mentioned_chapter += delta
        if hasattr(t, 'resolution_chapter') and t.resolution_chapter and t.resolution_chapter >= from_position:
            t.resolution_chapter += delta

    # Update macro_arcs chapter ranges
    arcs = getattr(draft, 'macro_arcs', None) or []
    for arc in arcs:
        if hasattr(arc, 'start_chapter') and arc.start_chapter >= from_position:
            arc.start_chapter += delta
        if hasattr(arc, 'end_chapter') and arc.end_chapter >= from_position:
            arc.end_chapter += delta


def insert_chapter_impl(
    generator,
    draft: StoryDraft,
    insert_after: int,
    title: str = "",
    summary: str = "",
    word_count: int = 2000,
    style: str = "",
    progress_callback=None,
    stream_callback=None,
) -> StoryDraft:
    """Insert a new chapter after the specified position.

    Args:
        generator: StoryGenerator instance
        draft: StoryDraft to modify
        insert_after: Insert after this chapter number (0 = insert at beginning)
        title: Optional title for the new chapter
        summary: Optional summary/direction for the new chapter
        word_count: Target word count
        style: Writing style override
        progress_callback: Progress reporting function
        stream_callback: Streaming content callback

    Returns:
        Modified StoryDraft with inserted chapter
    """
    context_window = generator.config.pipeline.context_window_chapters
    effective_style = style or generator.config.pipeline.writing_style

    def _log(msg):
        logger.info(msg)
        if progress_callback:
            progress_callback(msg)

    # Validate position
    total_chapters = len(draft.chapters)
    if insert_after < 0 or insert_after > total_chapters:
        raise ValueError(f"Invalid insert_after={insert_after}. Story has {total_chapters} chapters.")

    new_chapter_number = insert_after + 1
    _log(f"Inserting new chapter at position {new_chapter_number}...")

    # First, renumber all existing chapters from insertion point
    renumber_chapters(draft, new_chapter_number, delta=1)

    # Build bidirectional context: chapters before AND after insertion point
    before_context = ""
    after_context = ""

    if insert_after > 0:
        # Get summary of chapter(s) before insertion point
        before_chapters = [ch for ch in draft.chapters if ch.chapter_number < new_chapter_number]
        before_context = "\n".join(
            f"Ch.{ch.chapter_number}: {ch.summary}" for ch in before_chapters[-context_window:]
        )

    # After renumbering, chapters that were after insertion point now have +1 numbers
    after_chapters = [ch for ch in draft.chapters if ch.chapter_number > new_chapter_number]
    if after_chapters:
        after_context = "\n".join(
            f"Ch.{ch.chapter_number}: {ch.summary}" for ch in after_chapters[:context_window]
        )

    # Generate outline for inserted chapter using bidirectional context
    chars_text = "\n".join(
        f"- {c.name} ({c.role}): {c.personality}" for c in draft.characters
    )

    outline_prompt = f"""Tạo dàn ý cho chương {new_chapter_number} được chèn vào giữa câu chuyện.

Thể loại: {draft.genre}
Tiêu đề truyện: {draft.title}
Nhân vật: {chars_text}

Bối cảnh TRƯỚC vị trí chèn:
{before_context or "Đây là chương đầu tiên"}

Bối cảnh SAU vị trí chèn:
{after_context or "Không có chương sau"}

{"Tiêu đề gợi ý: " + title if title else ""}
{"Hướng dẫn: " + summary if summary else ""}

Yêu cầu: Tạo chương kết nối mạch truyện từ nội dung trước đến nội dung sau.
Trả về JSON: {{"chapter_number": {new_chapter_number}, "title": "...", "summary": "...", "key_events": [...]}}"""

    _log("Generating outline for inserted chapter...")
    result = generator.llm.generate_json(
        system_prompt="Bạn là biên kịch viết truyện tiếng Việt. Trả về JSON.",
        user_prompt=outline_prompt,
        temperature=0.9,
        model=generator._layer_model,
    )

    outline = ChapterOutline(
        chapter_number=new_chapter_number,
        title=result.get("title", title or f"Chương {new_chapter_number}"),
        summary=result.get("summary", summary or ""),
        key_events=result.get("key_events", []),
    )

    # Rebuild context for chapter writing
    story_context = generator.rebuild_context(draft)
    story_context.current_chapter = new_chapter_number
    story_context.total_chapters = total_chapters + 1

    # Get narrative context
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
        current_arc = get_arc_for_chapter(macro_arcs, new_chapter_number)
        arc_num = current_arc.arc_number if current_arc else 1
        active_conflicts = get_active_conflicts(conflict_web, arc_num)
        seeds = get_seeds_to_plant(foreshadowing_plan, new_chapter_number)
        payoffs = get_payoffs_due(foreshadowing_plan, new_chapter_number)
        pacing = validate_pacing(getattr(outline, 'pacing_type', '') or '')
    except Exception as e:
        logger.warning("Narrative context resolution failed for ch%d: %s", new_chapter_number, e)

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
        logger.debug("Enhancement context build failed for ch%d: %s", new_chapter_number, e)

    # Write the chapter
    _log(f"Writing inserted chapter {new_chapter_number}: {outline.title}...")
    all_chapter_texts = [ch.content for ch in draft.chapters if ch.chapter_number < new_chapter_number and ch.content]

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

    # Insert chapter and outline at correct positions
    # Find insertion index (chapters are now renumbered)
    insert_idx = insert_after  # 0-based index for list insertion
    draft.chapters.insert(insert_idx, chapter)
    draft.outlines.insert(insert_idx, outline)

    # Run post-processing
    self_reviewer = generator._get_self_reviewer() if generator.config.pipeline.enable_self_review else None
    with ThreadPoolExecutor(max_workers=3) as executor:
        _log(f"Extracting context for inserted chapter {new_chapter_number}...")
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

    _log(f"Chapter {new_chapter_number} inserted successfully! Story now has {len(draft.chapters)} chapters.")
    return draft


def generate_continuation_outlines(
    generator,
    draft: StoryDraft,
    additional_chapters: int = 5,
    progress_callback=None,
    arc_directives: list = None,
) -> list[ChapterOutline]:
    """Generate outlines for continuation without writing chapters.

    Args:
        arc_directives: List of ArcDirective objects for character arc steering

    Returns list of ChapterOutline objects that can be edited by user before writing.
    """
    arc_directives = arc_directives or []

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

    # Build base prompt
    base_prompt = prompts.CONTINUE_OUTLINE.format(
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
    )

    # Append arc directives if provided
    if arc_directives:
        arc_text = "\n".join(
            f"- {d.character}: {d.from_state} → {d.to_state} trong {d.chapter_span} chương"
            + (f" ({d.notes})" if getattr(d, 'notes', '') else "")
            for d in arc_directives
        )
        base_prompt += f"""

CHỈ THỊ ARC NHÂN VẬT (QUAN TRỌNG - phải tuân theo):
{arc_text}

Các dàn ý PHẢI thể hiện sự chuyển đổi arc của nhân vật theo chỉ thị trên. Chia đều tiến trình arc qua các chương."""

    result = generator.llm.generate_json(
        system_prompt="Bạn là biên kịch tài năng viết truyện bằng tiếng Việt. BẮT BUỘC: Toàn bộ output phải viết bằng tiếng Việt, không được dùng ngôn ngữ khác. Trả về JSON.",
        user_prompt=base_prompt,
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
    arc_directives: list = None,
) -> StoryDraft:
    """Write chapters from pre-generated (possibly user-edited) outlines.

    Args:
        arc_directives: List of ArcDirective objects for character arc steering

    Does not generate new outlines - uses provided ones directly.
    """
    arc_directives = arc_directives or []
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

            # Add arc steering context if directives provided
            if arc_directives:
                start_ch = len(draft.chapters) + 1 - len(outlines) + outlines.index(outline)
                arc_lines = []
                for d in arc_directives:
                    ch_in_arc = outline.chapter_number - start_ch + 1
                    if 1 <= ch_in_arc <= d.chapter_span:
                        progress = ch_in_arc / d.chapter_span
                        stage = "khởi đầu" if progress <= 0.3 else "giữa chặng" if progress <= 0.7 else "gần đạt"
                        arc_lines.append(
                            f"- {d.character}: đang ở giai đoạn {stage} ({int(progress*100)}%) "
                            f"từ '{d.from_state}' → '{d.to_state}'"
                        )
                if arc_lines:
                    enhancement_context += f"\n\nCHỈ THỊ ARC NHÂN VẬT CHƯƠNG NÀY:\n" + "\n".join(arc_lines)

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
    arc_directives: list = None,
) -> StoryDraft:
    """Continue writing from existing StoryDraft by adding more chapters.

    `generator` is a StoryGenerator instance (passed to avoid circular import).
    This is a convenience wrapper that generates outlines and writes chapters in one step.
    For two-step flow (preview → edit → write), use generate_continuation_outlines + write_from_outlines.

    Args:
        arc_directives: List of ArcDirective objects for character arc steering
    """
    arc_directives = arc_directives or []

    # Step 1: Generate outlines
    new_outlines = generate_continuation_outlines(
        generator, draft, additional_chapters, progress_callback, arc_directives
    )
    if not new_outlines:
        if progress_callback:
            progress_callback("No outlines generated. Aborting continuation.")
        return draft

    # Step 2: Write chapters from outlines
    return write_from_outlines(
        generator, draft, new_outlines, word_count, style, progress_callback, stream_callback, arc_directives
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
