"""Post-chapter processing: self-review, parallel extraction, context & bible updates."""

import logging
from concurrent.futures import ThreadPoolExecutor

from models.schemas import ChapterOutline, Chapter, StoryDraft, StoryContext, count_words

if __name__ == "__main__":
    pass  # not a script

logger = logging.getLogger(__name__)


_CRITICAL_KEYWORDS = [
    "chết", "phản bội", "tiết lộ bí mật", "kết thúc", "chiến thắng",
    "thất bại hoàn toàn", "hi sinh", "phá hủy", "sụp đổ", "bị phản",
]


def _prune_plot_events(events: list) -> list:
    """Smart prune: always keep critical events + recent 30 + top older by length. Cap 50 non-critical."""
    critical = [e for e in events if getattr(e, 'critical', False)]
    non_critical = [e for e in events if not getattr(e, 'critical', False)]
    if len(non_critical) <= 50:
        return events  # nothing to prune
    recent = non_critical[-30:]
    older = sorted(non_critical[:-30], key=lambda e: len(e.event), reverse=True)[:20]
    return critical + older + recent


def process_chapter_post_write(
    chapter: Chapter,
    outline: ChapterOutline,
    story_context: StoryContext,
    characters: list,
    context_window: int,
    executor: ThreadPoolExecutor,
    llm,
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
    world_rules=None,
    voice_profiles=None,
    # Phase 5 wiring
    pipeline_config=None,
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
        # Arc trajectory context is now passed in extraction prompt (character_generator.py).
        # Check for arc regression (position contradicts expected trajectory)
        if new_states and characters and config.enable_arc_waypoints:
            try:
                from pipeline.layer1_story.consistency_validators import detect_arc_drift
                total_chapters = getattr(story_context, 'total_chapters', chapter_num + 10)
                arc_warnings = detect_arc_drift(new_states, characters, chapter_num, total_chapters)
                for w in arc_warnings:
                    logger.warning(w)
            except Exception as arc_e:
                logger.debug(f"Arc drift check failed (non-fatal): {arc_e}")
    except Exception as e:
        logger.warning(f"Character state extraction failed: {e}")
        new_states = []
        states_f.cancel()

    try:
        new_events = events_f.result(timeout=_TIMEOUT)
        # Tag critical events based on keywords (non-LLM, cheap heuristic)
        for e in new_events:
            if any(kw in e.event.lower() for kw in _CRITICAL_KEYWORDS):
                e.critical = True
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

    # --- Consistency validators (non-fatal) ---
    try:
        from pipeline.layer1_story.consistency_validators import (
            validate_character_names, detect_arc_drift, extract_timeline_and_locations,
        )
        # Name validation (regex, zero LLM cost)
        name_warnings = validate_character_names(chapter.content, characters)
        story_context.name_warnings = name_warnings
        if name_warnings:
            logger.warning("Ch%d name issues: %s", outline.chapter_number, name_warnings)

        # Arc drift detection (heuristic, zero LLM cost)
        drift_warnings = detect_arc_drift(
            story_context.character_states, characters,
            outline.chapter_number, story_context.total_chapters,
        )
        story_context.arc_drift_warnings = drift_warnings
        for w in drift_warnings:
            logger.warning(w)
    except Exception as e:
        logger.warning(f"Consistency validation failed: {e}")

    # Extract world state changes (permanent, irreversible changes to the setting)
    try:
        world_changes_result = llm.generate_json(
            system_prompt="Trích xuất thay đổi thế giới. Trả về JSON.",
            user_prompt=(
                f"Chương {outline.chapter_number}:\n{chapter.content[:3000]}\n\n"
                "Liệt kê các thay đổi CỐ ĐỊNH, KHÔNG THỂ ĐẢO NGƯỢC đối với thế giới/bối cảnh "
                "(ví dụ: thành phố bị thiêu rụi, vua chết, cầu bị phá). "
                "BỎ QUA: trạng thái nhân vật, cảm xúc, thông tin nhân vật biết.\n"
                '{"world_changes": ["mô tả thay đổi ngắn gọn"]}'
            ),
            temperature=0.2,
            max_tokens=300,
            model_tier="cheap",
        )
        new_world_changes = world_changes_result.get("world_changes", [])
        if new_world_changes and hasattr(story_context, 'world_state_changes'):
            seen = set(story_context.world_state_changes)
            for change in new_world_changes:
                if change and change not in seen:
                    story_context.world_state_changes.append(change)
                    seen.add(change)
            # Cap at 30 world state changes
            story_context.world_state_changes = story_context.world_state_changes[-30:]
    except Exception as e:
        logger.warning(f"World state extraction failed: {e}")

    # Extract timeline positions and character locations (1 cheap LLM call)
    prev_locations = dict(story_context.character_locations)
    try:
        new_tl, new_loc = extract_timeline_and_locations(
            llm, chapter.content, outline.chapter_number,
            story_context.timeline_positions, story_context.character_locations,
        )
        story_context.timeline_positions = new_tl
        story_context.character_locations = new_loc
    except Exception as e:
        logger.warning(f"Timeline/location extraction failed: {e}")
        new_loc = story_context.character_locations

    # Location transition validation (pure Python, zero LLM cost)
    # Store separately — world_rule_violations may be overwritten by quality validators later
    _location_warnings: list[str] = []
    try:
        from pipeline.layer1_story.consistency_validators import validate_location_transitions
        _location_warnings = validate_location_transitions(
            prev_locations, new_loc, chapter.content,
        )
        for w in _location_warnings:
            logger.warning("Ch%d location: %s", outline.chapter_number, w)
    except Exception as e:
        logger.debug("Location validation failed (non-fatal): %s", e)

    # Update Story Bible (always-on)
    if draft.story_bible and bible_manager:
        bible_manager.update_after_chapter(
            draft.story_bible, chapter,
            list(story_context.character_states), new_events,
            timeline_positions=story_context.timeline_positions,
            character_locations=story_context.character_locations,
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
        # Always overwrite hook — clears stale hook if this chapter has none
        story_context.chapter_ending_hook = structured.chapter_ending_hook
        # Track emotional arc history across chapters
        if structured.actual_emotional_arc:
            story_context.emotional_history.append(structured.actual_emotional_arc)
            # Store 10 for future analysis; chapter_writer shows last 3
            story_context.emotional_history = story_context.emotional_history[-10:]
        # Pacing feedback loop: compare intended vs actual, compute correction
        try:
            from pipeline.layer1_story.pacing_controller import compute_pacing_adjustment
            intended_pacing = getattr(outline, "pacing_type", "") or ""
            actual_arc = structured.actual_emotional_arc
            adjustment = compute_pacing_adjustment(
                intended_pacing, actual_arc, list(story_context.pacing_history),
            )
            story_context.pacing_adjustment = adjustment
            if adjustment:
                logger.info("Pacing mismatch ch%d: %s", outline.chapter_number, adjustment)
        except Exception as pace_err:
            logger.debug("Pacing feedback failed (non-fatal): %s", pace_err)
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
        # Stale thread detection (zero LLM cost)
        try:
            from pipeline.layer1_story.plot_thread_tracker import get_stale_threads
            stale_gap = min(10, max(3, story_context.total_chapters // 3))
            stale = get_stale_threads(updated_threads, outline.chapter_number, stale_gap)
            story_context.stale_thread_warnings = [
                f"Tuyến '{t.description}' (mở từ ch.{t.planted_chapter}, "
                f"lần cuối nhắc ch.{t.last_mentioned_chapter}) — đã {outline.chapter_number - t.last_mentioned_chapter} chương không nhắc đến"
                for t in stale
            ]
        except Exception as e:
            logger.warning(f"Stale thread detection failed: {e}")
    except Exception as e:
        logger.warning(f"Plot thread tracking failed: {e}")

    # Emotional memory extraction (Phase 5)
    if pipeline_config and getattr(pipeline_config, "enable_emotional_memory", False):
        try:
            from pipeline.layer1_story.character_memory_bank import (
                extract_emotional_memories, merge_memory_banks,
            )
            char_names = [c.name if hasattr(c, 'name') else str(c) for c in characters]
            new_banks = extract_emotional_memories(
                llm, chapter.content, char_names, outline.chapter_number,
            )
            if new_banks:
                existing_banks = getattr(story_context, "emotional_memory_banks", {}) or {}
                merged = merge_memory_banks(existing_banks, new_banks)
                story_context.emotional_memory_banks = merged
                logger.debug("Ch%d emotional memory: %d characters tracked", outline.chapter_number, len(merged))
        except Exception as e:
            logger.warning(f"Emotional memory extraction failed: {e}")

    # Causal event extraction (Phase 5)
    if pipeline_config and getattr(pipeline_config, "enable_l1_causal_graph", False):
        try:
            from pipeline.layer1_story.l1_causal_graph import (
                extract_causal_events, CausalGraph,
            )
            char_names = [c.name if hasattr(c, 'name') else str(c) for c in characters]
            new_events = extract_causal_events(
                llm, chapter.content, outline.chapter_number, char_names,
            )
            if new_events:
                if not hasattr(story_context, "causal_graph") or story_context.causal_graph is None:
                    story_context.causal_graph = CausalGraph()
                for evt in new_events:
                    story_context.causal_graph.add_event(evt)
                logger.debug("Ch%d causal events: %d extracted", outline.chapter_number, len(new_events))
        except Exception as e:
            logger.warning(f"Causal event extraction failed: {e}")

    # Conflict status update (heuristic, no LLM call)
    try:
        from pipeline.layer1_story.conflict_web_builder import update_conflict_status
        if story_context.conflict_map:
            update_conflict_status(
                story_context.conflict_map, chapter.content, outline.chapter_number, llm=llm,
            )
    except Exception as e:
        logger.warning(f"Conflict status update failed: {e}")

    # Mark foreshadowing as planted/paid off (semantic when available, keyword fallback)
    try:
        from pipeline.layer1_story.foreshadowing_manager import (
            mark_planted, mark_paid_off, get_seeds_to_plant, get_payoffs_due,
            verify_seeds_semantic, verify_payoffs_semantic,
        )
        if foreshadowing_plan:
            seeds_due = get_seeds_to_plant(foreshadowing_plan, outline.chapter_number)
            payoffs_due = get_payoffs_due(foreshadowing_plan, outline.chapter_number)
            if seeds_due and llm:
                try:
                    verify_seeds_semantic(llm, chapter.content, seeds_due)
                except Exception:
                    mark_planted(foreshadowing_plan, outline.chapter_number, chapter.content)
            else:
                mark_planted(foreshadowing_plan, outline.chapter_number, chapter.content)
            if payoffs_due and llm:
                try:
                    verify_payoffs_semantic(llm, chapter.content, payoffs_due)
                except Exception:
                    mark_paid_off(foreshadowing_plan, outline.chapter_number)
            else:
                mark_paid_off(foreshadowing_plan, outline.chapter_number)
    except Exception as e:
        logger.warning(f"Foreshadowing tracking failed: {e}")

    # --- Arc execution validation (Phase 6, non-fatal) ---
    if pipeline_config and getattr(pipeline_config, "enable_arc_execution_validation", True):
        try:
            from pipeline.layer1_story.arc_execution_validator import (
                validate_all_arcs, format_arc_warnings,
            )
            use_llm = getattr(pipeline_config, "arc_validation_use_llm", False)
            arc_results = validate_all_arcs(
                chapter, characters, outline.chapter_number,
                llm=llm if use_llm else None,
                use_llm_for_critical=use_llm,
            )
            arc_warnings = format_arc_warnings(arc_results)
            if arc_warnings:
                story_context.arc_execution_warnings = arc_warnings
                for w in arc_warnings:
                    logger.warning("Ch%d arc: %s", outline.chapter_number, w)
            else:
                story_context.arc_execution_warnings = []
        except Exception as e:
            logger.warning(f"Arc execution validation failed: {e}")

    # --- Quality validators (1 cheap LLM call each, non-fatal) ---

    # World rules validation
    try:
        if world_rules:
            from pipeline.layer1_story.quality_validators import validate_world_rules
            violations = validate_world_rules(llm, chapter.content, world_rules, outline.chapter_number)
            story_context.world_rule_violations = violations
            if violations:
                logger.warning("Ch%d world rule violations: %s", outline.chapter_number, violations)
    except Exception as e:
        logger.warning(f"World rules validation failed: {e}")

    # Merge location warnings into world_rule_violations (after world rule check)
    if _location_warnings:
        story_context.world_rule_violations = (
            list(story_context.world_rule_violations) + _location_warnings
        )[-5:]

    # Dialogue voice validation
    try:
        if voice_profiles:
            from pipeline.layer1_story.quality_validators import validate_dialogue_voice
            voice_warnings = validate_dialogue_voice(llm, chapter.content, voice_profiles, outline.chapter_number)
            # Overwrite: only latest chapter's warnings guide the next chapter
            story_context.dialogue_voice_warnings = voice_warnings
            if voice_warnings:
                logger.warning("Ch%d voice warnings: %s", outline.chapter_number, voice_warnings)
    except Exception as e:
        logger.warning(f"Dialogue voice validation failed: {e}")

    # Pacing history tracking
    story_context.pacing_history.append(getattr(outline, "pacing_type", None) or "rising")
    story_context.pacing_history = story_context.pacing_history[-10:]

    return chapter, summary, new_states, new_events
