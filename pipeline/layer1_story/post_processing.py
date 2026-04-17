"""Post-chapter processing: self-review, parallel extraction, context & bible updates."""

import logging
from concurrent.futures import ThreadPoolExecutor

from models.schemas import ChapterOutline, Chapter, StoryDraft, StoryContext, count_words
from pipeline.layer1_story.extraction_guard import tracked_extraction

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

    # Bug #8: Check extraction cache before running LLM
    from pipeline.pipeline_utils import ChapterExtractionCache
    _cache = ChapterExtractionCache()
    ch_num = outline.chapter_number

    cached_summary = _cache.get_summary(ch_num, chapter.content)
    cached_events = _cache.get_plot_events(ch_num, chapter.content)

    # Parallel extraction (skip cached)
    summary_f = None if cached_summary else executor.submit(summarize_chapter, llm, chapter.content)
    states_f = executor.submit(extract_character_states, llm, chapter.content, characters)
    events_f = None if cached_events else executor.submit(extract_plot_events, llm, chapter.content, outline.chapter_number)

    _TIMEOUT = 120

    summary = ""
    if cached_summary:
        summary = cached_summary
        logger.debug(f"Ch{ch_num}: using cached summary")
    else:
        with tracked_extraction(story_context, ch_num, "summary"):
            summary = summary_f.result(timeout=_TIMEOUT)
            _cache.set_summary(ch_num, chapter.content, summary)

    new_states = []
    with tracked_extraction(story_context, ch_num, "character_states"):
        new_states = states_f.result(timeout=_TIMEOUT)

    new_events = []
    if cached_events:
        new_events = cached_events
        logger.debug(f"Ch{ch_num}: using cached plot_events")
    else:
        with tracked_extraction(story_context, ch_num, "plot_events"):
            new_events = events_f.result(timeout=_TIMEOUT)
            _cache.set_plot_events(ch_num, chapter.content, new_events)
    for e in new_events:
        if any(kw in e.event.lower() for kw in _CRITICAL_KEYWORDS):
            e.critical = True

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

    # Bug #6: Dialogue voice consistency check (uses cheap LLM tier)
    _voice_check_enabled = getattr(pipeline_config, "enable_dialogue_voice_check", False) \
        if pipeline_config else False
    if _voice_check_enabled and voice_profiles:
        try:
            from pipeline.layer1_story.dialogue_consistency_checker import dialogue_consistency_check
            passed, warning = dialogue_consistency_check(
                llm, chapter.content, characters,
                threshold=0.7,
            )
            if not passed and warning:
                story_context.voice_consistency_warnings = getattr(
                    story_context, "voice_consistency_warnings", []
                ) or []
                story_context.voice_consistency_warnings.append({
                    "chapter": outline.chapter_number,
                    "warning": warning,
                })
                if progress_callback:
                    progress_callback(f"⚠️ Ch{outline.chapter_number}: voice consistency issue")
        except Exception as e:
            logger.debug(f"Dialogue voice check failed (non-fatal): {e}")

    # Feature #12: POV drift detection
    _pov_check_enabled = getattr(pipeline_config, "enable_pov_drift_check", False) \
        if pipeline_config else False
    if _pov_check_enabled:
        try:
            from pipeline.layer1_story.pov_drift_detector import validate_chapter_pov
            passed, warning = validate_chapter_pov(llm, chapter.content, characters)
            if not passed and warning:
                story_context.pov_drift_warnings = getattr(
                    story_context, "pov_drift_warnings", []
                ) or []
                story_context.pov_drift_warnings.append({
                    "chapter": outline.chapter_number,
                    "warning": warning,
                })
                if progress_callback:
                    progress_callback(f"⚠️ Ch{outline.chapter_number}: POV drift detected")
        except Exception as e:
            logger.debug(f"POV drift check failed (non-fatal): {e}")

    # Feature #16: Dialogue attribution validation
    _attr_check_enabled = getattr(pipeline_config, "enable_dialogue_attribution_check", False) \
        if pipeline_config else False
    if _attr_check_enabled:
        try:
            from pipeline.layer1_story.dialogue_attribution_validator import (
                validate_dialogue_attribution, detect_rapid_exchange,
            )
            attr_result = validate_dialogue_attribution(llm, chapter.content, characters)
            rapid = detect_rapid_exchange(chapter.content)
            if attr_result["clarity_score"] < 0.7 or rapid:
                story_context.dialogue_attribution_warnings = getattr(
                    story_context, "dialogue_attribution_warnings", []
                ) or []
                story_context.dialogue_attribution_warnings.append({
                    "chapter": outline.chapter_number,
                    "clarity_score": attr_result["clarity_score"],
                    "unclear_count": len(attr_result["unclear_lines"]),
                    "rapid_exchanges": len(rapid),
                })
        except Exception as e:
            logger.debug(f"Dialogue attribution check failed (non-fatal): {e}")

    # Feature #13: Timeline validation
    _timeline_enabled = getattr(pipeline_config, "enable_timeline_validation", False) \
        if pipeline_config else False
    if _timeline_enabled:
        try:
            from pipeline.layer1_story.timeline_validator import (
                validate_chapter_timeline, create_timeline_state, format_timeline_warning,
            )
            # Get or create timeline state
            timeline_state = getattr(story_context, "timeline_state", None)
            if timeline_state is None:
                timeline_state = create_timeline_state()
                story_context.timeline_state = timeline_state

            tl_result = validate_chapter_timeline(
                llm, chapter.content, outline.chapter_number, timeline_state,
            )
            if not tl_result["valid"]:
                story_context.timeline_warnings = getattr(
                    story_context, "timeline_warnings", []
                ) or []
                story_context.timeline_warnings.extend(tl_result["contradictions"])
                if progress_callback:
                    progress_callback(f"⚠️ Ch{outline.chapter_number}: timeline contradiction")
        except Exception as e:
            logger.debug(f"Timeline validation failed (non-fatal): {e}")

    # Feature #14: Secret tracking
    _secret_enabled = getattr(pipeline_config, "enable_secret_tracking", False) \
        if pipeline_config else False
    if _secret_enabled:
        try:
            from pipeline.layer1_story.character_secret_tracker import (
                check_secret_reveal, initialize_secrets,
            )
            # Get or create secret registry
            secret_registry = getattr(story_context, "secret_registry", None)
            if secret_registry is None:
                secret_registry = initialize_secrets(characters)
                story_context.secret_registry = secret_registry

            secret_result = check_secret_reveal(
                llm, chapter.content, outline.chapter_number, secret_registry,
            )
            if secret_result["premature"]:
                story_context.premature_reveals = getattr(
                    story_context, "premature_reveals", []
                ) or []
                story_context.premature_reveals.extend(secret_result["premature"])
                if progress_callback:
                    progress_callback(
                        f"⚠️ Ch{outline.chapter_number}: {len(secret_result['premature'])} premature reveal(s)"
                    )
        except Exception as e:
            logger.debug(f"Secret tracking failed (non-fatal): {e}")

    # Feature #15: Thematic resonance
    _thematic_enabled = getattr(pipeline_config, "enable_thematic_resonance", False) \
        if pipeline_config else False
    if _thematic_enabled:
        try:
            from pipeline.layer1_story.thematic_resonance_tracker import (
                analyze_theme_presence, detect_thematic_drift,
                initialize_thematic_state, format_thematic_guidance,
            )
            # Get or create thematic state
            thematic_state = getattr(story_context, "thematic_state", None)
            if thematic_state is None:
                premise = getattr(draft, "premise", None)
                thematic_state = initialize_thematic_state(premise)
                story_context.thematic_state = thematic_state

            if thematic_state.core_themes:
                presences = analyze_theme_presence(
                    llm, chapter.content, outline.chapter_number,
                    thematic_state.core_themes,
                )
                for p in presences:
                    thematic_state.add_presence(p)

                drift = detect_thematic_drift(
                    thematic_state, outline.chapter_number, story_context.total_chapters,
                )
                if drift["drifting"]:
                    story_context.thematic_drift_warning = format_thematic_guidance(
                        drift, thematic_state, outline.chapter_number,
                    )
        except Exception as e:
            logger.debug(f"Thematic resonance tracking failed (non-fatal): {e}")

    # Extract world state changes (permanent, irreversible changes to the setting)
    with tracked_extraction(story_context, ch_num, "world_state"):
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

    # Extract timeline positions and character locations (1 cheap LLM call)
    prev_locations = dict(story_context.character_locations)
    new_loc = story_context.character_locations
    with tracked_extraction(story_context, ch_num, "timeline_location"):
        new_tl, new_loc = extract_timeline_and_locations(
            llm, chapter.content, outline.chapter_number,
            story_context.timeline_positions, story_context.character_locations,
        )
        story_context.timeline_positions = new_tl
        story_context.character_locations = new_loc

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

    # L1-E: Post-write foreshadowing payoff verification.
    # Previously: verify_payoffs_semantic existed but was never called — planted seeds
    # whose payoff chapter == current chapter could slip through with no check.
    _verify_payoff_enabled = getattr(pipeline_config, "enable_foreshadowing_payoff_verify", False) \
        if pipeline_config else False
    if _verify_payoff_enabled and foreshadowing_plan:
        try:
            from pipeline.layer1_story.foreshadowing_manager import (
                get_payoffs_due, verify_payoffs_semantic,
            )
            _threshold = float(getattr(pipeline_config, "semantic_foreshadowing_threshold", 0.7))
            _due = get_payoffs_due(foreshadowing_plan, outline.chapter_number)
            if _due:
                with tracked_extraction(story_context, ch_num, "foreshadowing"):
                    verify_payoffs_semantic(
                        llm, chapter.content, _due,
                        model=None, threshold=_threshold,
                    )
                _missing = [p for p in _due if not p.paid_off]
                if _missing:
                    story_context.foreshadowing_payoff_missing = [
                        {
                            "hint": p.hint,
                            "confidence": p.planted_confidence or 0.0,
                            "payoff_chapter": p.payoff_chapter,
                            "plant_chapter": p.plant_chapter,
                        }
                        for p in _missing
                    ]
                    logger.warning(
                        "Ch%d: %d payoff(s) due but not detected: %s",
                        outline.chapter_number, len(_missing),
                        [p.hint[:40] for p in _missing],
                    )
                    if progress_callback:
                        progress_callback(
                            f"⚠️ Ch{outline.chapter_number}: {len(_missing)} payoff chưa được thực hiện"
                        )
                else:
                    # Clear stale missing list when all payoffs detected
                    story_context.foreshadowing_payoff_missing = []
        except Exception as e:
            logger.warning(f"Foreshadowing payoff verification failed (non-fatal): {e}")

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
    with tracked_extraction(story_context, ch_num, "structured_summary"):
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

            # Bug #11: Detect emotional whiplash
            try:
                from pipeline.pipeline_utils import detect_emotional_whiplash, format_whiplash_warning
                whiplash_events = detect_emotional_whiplash(
                    story_context.emotional_history, threshold=1.2, window=3,
                )
                if whiplash_events:
                    warning = format_whiplash_warning(whiplash_events)
                    story_context.emotional_whiplash_warning = warning
                    if progress_callback:
                        progress_callback(
                            f"⚠️ Ch{outline.chapter_number}: emotional whiplash detected"
                        )
                else:
                    story_context.emotional_whiplash_warning = ""
            except Exception as wh_err:
                logger.debug("Emotional whiplash detection failed (non-fatal): %s", wh_err)

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

    # Plot thread tracking
    with tracked_extraction(story_context, ch_num, "plot_threads"):
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

    # Emotional memory extraction (Phase 5)
    if pipeline_config and getattr(pipeline_config, "enable_emotional_memory", False):
        with tracked_extraction(story_context, ch_num, "emotional_memory"):
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

    # Causal event extraction (Phase 5)
    if pipeline_config and getattr(pipeline_config, "enable_l1_causal_graph", False):
        with tracked_extraction(story_context, ch_num, "causal_events"):
            from pipeline.layer1_story.l1_causal_graph import (
                extract_causal_events, CausalGraph,
            )
            char_names = [c.name if hasattr(c, 'name') else str(c) for c in characters]
            causal_new_events = extract_causal_events(
                llm, chapter.content, outline.chapter_number, char_names,
            )
            if causal_new_events:
                if not hasattr(story_context, "causal_graph") or story_context.causal_graph is None:
                    story_context.causal_graph = CausalGraph()
                for evt in causal_new_events:
                    story_context.causal_graph.add_event(evt)
                logger.debug("Ch%d causal events: %d extracted", outline.chapter_number, len(causal_new_events))

    # Conflict status update (heuristic, no LLM call)
    with tracked_extraction(story_context, ch_num, "conflict_status"):
        from pipeline.layer1_story.conflict_web_builder import update_conflict_status
        if story_context.conflict_map:
            update_conflict_status(
                story_context.conflict_map, chapter.content, outline.chapter_number, llm=llm,
            )

    # Mark foreshadowing as planted/paid off (semantic when available, keyword fallback)
    with tracked_extraction(story_context, ch_num, "foreshadowing"):
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

    # --- Arc execution validation (Phase 6, non-fatal) ---
    if pipeline_config and getattr(pipeline_config, "enable_arc_execution_validation", True):
        with tracked_extraction(story_context, ch_num, "arc_execution"):
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
            # L1-C: append to per-character arc progression cache
            try:
                from pipeline.layer1_story.arc_waypoint_generator import update_arc_progression_cache
                update_arc_progression_cache(
                    story_context.arc_progression_cache, arc_results, outline.chapter_number,
                )
            except Exception as e:
                logger.debug("arc_progression_cache update failed (non-fatal): %s", e)

    # --- Quality validators (1 cheap LLM call each, non-fatal) ---

    # World rules validation
    with tracked_extraction(story_context, ch_num, "world_rules"):
        if world_rules:
            from pipeline.layer1_story.quality_validators import validate_world_rules
            violations = validate_world_rules(llm, chapter.content, world_rules, outline.chapter_number)
            story_context.world_rule_violations = violations
            if violations:
                logger.warning("Ch%d world rule violations: %s", outline.chapter_number, violations)

    # Merge location warnings into world_rule_violations (after world rule check)
    if _location_warnings:
        story_context.world_rule_violations = (
            list(story_context.world_rule_violations) + _location_warnings
        )[-5:]

    # Dialogue voice validation
    with tracked_extraction(story_context, ch_num, "dialogue_voice"):
        if voice_profiles:
            from pipeline.layer1_story.quality_validators import validate_dialogue_voice
            voice_warnings = validate_dialogue_voice(llm, chapter.content, voice_profiles, outline.chapter_number)
            # Overwrite: only latest chapter's warnings guide the next chapter
            story_context.dialogue_voice_warnings = voice_warnings
            if voice_warnings:
                logger.warning("Ch%d voice warnings: %s", outline.chapter_number, voice_warnings)

    # Pacing history tracking
    story_context.pacing_history.append(getattr(outline, "pacing_type", None) or "rising")
    story_context.pacing_history = story_context.pacing_history[-10:]

    return chapter, summary, new_states, new_events
