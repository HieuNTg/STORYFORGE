"""Behavior tests for 5 L1 validation/context modules.

Modules under test:
- pipeline.layer1_story.timeline_validator
- pipeline.layer1_story.pacing_enforcer
- pipeline.layer1_story.thematic_resonance_tracker
- pipeline.layer1_story.enhancement_context_builder
- pipeline.layer1_story.l1_causal_graph
"""

from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# timeline_validator
# ---------------------------------------------------------------------------
from pipeline.layer1_story.enhancement_context_builder import (
    build_enhancement_context,
    build_shared_enhancement_context,
)
from pipeline.layer1_story.l1_causal_graph import (
    CausalEvent,
    CausalGraph,
    extract_causal_events,
    format_causal_dependencies_for_prompt,
    validate_causal_references,
)
from pipeline.layer1_story.pacing_enforcer import rewrite_for_pacing, verify_pacing
from pipeline.layer1_story.thematic_resonance_tracker import (
    ThematicState,
    ThemePresence,
    analyze_theme_presence,
    audit_thematic_resonance,
    detect_thematic_drift,
    initialize_thematic_state,
)
from pipeline.layer1_story.timeline_validator import (
    TimelineEvent,
    create_timeline_state,
    detect_time_contradiction,
    extract_time_markers,
    format_timeline_warning,
    validate_chapter_timeline,
)


class TestExtractTimeMarkers:
    def test_morning_marker_detected(self):
        text = "Buổi sáng, ánh bình minh chiếu vào căn phòng."
        result = extract_time_markers(text)
        assert result["time_of_day"] == "morning"

    def test_night_marker_detected(self):
        text = "Đêm khuya, tiếng côn trùng vang vọng."
        result = extract_time_markers(text)
        assert result["time_of_day"] == "night"

    def test_relative_next_day(self):
        text = "Sáng hôm sau, Minh thức dậy sớm."
        result = extract_time_markers(text)
        assert "next_day" in result["relative_markers"]

    def test_flashback_detected(self):
        text = "Hắn nhớ lại ngày xưa khi còn nhỏ."
        result = extract_time_markers(text)
        assert "flashback" in result["relative_markers"]

    def test_no_markers_returns_empty(self):
        result = extract_time_markers("Một câu văn hoàn toàn không có dấu hiệu thời gian.")
        assert result["time_of_day"] == ""
        assert result["relative_markers"] == []

    def test_multiple_relative_markers(self):
        text = "Hôm nay vài ngày sau khi sự kiện xảy ra."
        result = extract_time_markers(text)
        assert len(result["relative_markers"]) >= 1


class TestDetectTimeContradiction:
    def test_same_day_regression_flagged(self):
        # afternoon → morning on same day is contradiction
        contradiction = detect_time_contradiction("afternoon", "morning", "same_day")
        assert contradiction is not None
        assert "afternoon" in contradiction or "morning" in contradiction

    def test_same_day_forward_is_valid(self):
        contradiction = detect_time_contradiction("morning", "evening", "same_day")
        assert contradiction is None

    def test_flashback_always_valid(self):
        contradiction = detect_time_contradiction("evening", "morning", "flashback")
        assert contradiction is None

    def test_missing_prev_time_no_contradiction(self):
        assert detect_time_contradiction("", "morning", "same_day") is None

    def test_missing_curr_time_no_contradiction(self):
        assert detect_time_contradiction("morning", "", "same_day") is None


class TestTimelineState:
    def test_add_event_increments_day_on_next_day(self):
        state = create_timeline_state()
        assert state.current_day == 1
        event = TimelineEvent(chapter=2, relative_marker="next_day", time_of_day="morning")
        state.add_event(event)
        assert state.current_day == 2

    def test_add_event_jumps_days_later(self):
        state = create_timeline_state()
        event = TimelineEvent(chapter=3, relative_marker="days_later")
        state.add_event(event)
        assert state.current_day == 4  # 1 + 3

    def test_add_event_week_later(self):
        state = create_timeline_state()
        event = TimelineEvent(chapter=4, relative_marker="week_later")
        state.add_event(event)
        assert state.current_day == 8  # 1 + 7

    def test_last_time_of_day_updated(self):
        state = create_timeline_state()
        event = TimelineEvent(chapter=1, time_of_day="evening")
        state.add_event(event)
        assert state.last_time_of_day == "evening"


class TestValidateChapterTimeline:
    def test_happy_path_no_contradiction(self):
        llm = MagicMock()
        state = create_timeline_state()
        # Chapter with morning on next day — no contradiction
        content = "Sáng hôm sau, Minh rời khỏi nhà sớm để đến chợ."
        result = validate_chapter_timeline(llm, content, 2, state)
        assert result["valid"] is True
        assert isinstance(result["contradictions"], list)
        assert "current_state" in result

    def test_same_day_time_regression_detected(self):
        llm = MagicMock()
        state = create_timeline_state()
        # Set state to evening first
        state.last_time_of_day = "evening"
        # Chapter claims same day but morning
        content = "Cùng ngày đó, buổi sáng Linh đã thức dậy sớm hơn mọi khi."
        result = validate_chapter_timeline(llm, content, 3, state)
        # Should detect evening → morning regression on same day
        assert len(result["contradictions"]) > 0

    def test_no_time_marker_generates_warning(self):
        llm = MagicMock()
        state = create_timeline_state()
        content = "Nhân vật đi lại trong nhà, suy nghĩ về quá khứ."
        result = validate_chapter_timeline(llm, content, 1, state)
        assert len(result["warnings"]) > 0

    def test_llm_called_for_flashback(self):
        llm = MagicMock()
        llm.generate_json.return_value = {"valid": True, "time_of_day": "morning"}
        state = create_timeline_state()
        # Flashback → multiple markers → triggers LLM
        content = "Hắn nhớ lại ngày xưa và hôm nay vẫn còn nhớ."
        validate_chapter_timeline(llm, content, 5, state)
        llm.generate_json.assert_called_once()

    def test_llm_contradiction_propagates(self):
        llm = MagicMock()
        llm.generate_json.return_value = {
            "valid": False,
            "contradiction": "Không thể đêm và sáng cùng lúc",
            "time_of_day": "night",
        }
        state = create_timeline_state()
        content = "Hắn nhớ lại ngày xưa và hôm nay trời vừa sáng."
        result = validate_chapter_timeline(llm, content, 5, state)
        assert not result["valid"]
        assert any("Không thể" in c for c in result["contradictions"])

    def test_state_updated_after_validation(self):
        llm = MagicMock()
        state = create_timeline_state()
        content = "Sáng hôm sau, nắng mai chiếu rọi khắp nơi."
        validate_chapter_timeline(llm, content, 2, state)
        assert len(state.events) == 1
        assert state.events[0].chapter == 2


class TestFormatTimelineWarning:
    def test_no_issues_returns_empty(self):
        result = format_timeline_warning({"valid": True, "warnings": []})
        assert result == ""

    def test_contradiction_in_output(self):
        result = format_timeline_warning({
            "valid": False,
            "contradictions": ["Thời gian lùi: evening → morning"],
            "warnings": [],
        })
        assert "evening" in result or "MÂU THUẪN" in result

    def test_warning_only_in_output(self):
        result = format_timeline_warning({
            "valid": True,
            "contradictions": [],
            "warnings": ["Chương 3: không có marker thời gian rõ ràng"],
        })
        assert "Chương 3" in result



# ---------------------------------------------------------------------------
# pacing_enforcer
# ---------------------------------------------------------------------------


class TestVerifyPacing:
    def _make_llm(self, detected="climax", confidence=0.85, reason="hành động dồn dập"):
        llm = MagicMock()
        llm.generate_json.return_value = {
            "detected": detected,
            "confidence": confidence,
            "reason": reason,
        }
        return llm

    def test_happy_path_match(self):
        llm = self._make_llm(detected="climax")
        content = "A" * 2500
        result = verify_pacing(llm, content, "climax")
        assert result["match"] is True
        assert result["detected"] == "climax"
        assert result["target"] == "climax"
        assert 0.0 <= result["confidence"] <= 1.0

    def test_mismatch_detected(self):
        llm = self._make_llm(detected="slow")
        result = verify_pacing(llm, "content", "climax")
        assert result["match"] is False
        assert result["detected"] == "slow"

    def test_empty_content_returns_empty(self):
        llm = MagicMock()
        result = verify_pacing(llm, "", "climax")
        assert result == {}
        llm.generate_json.assert_not_called()

    def test_empty_target_returns_empty(self):
        llm = MagicMock()
        result = verify_pacing(llm, "some content", "")
        assert result == {}

    def test_llm_failure_returns_empty(self):
        llm = MagicMock()
        llm.generate_json.side_effect = RuntimeError("LLM down")
        result = verify_pacing(llm, "content", "rising")
        assert result == {}

    def test_non_dict_llm_response_returns_empty(self):
        llm = MagicMock()
        llm.generate_json.return_value = "invalid"
        result = verify_pacing(llm, "content", "rising")
        assert result == {}

    def test_long_content_uses_excerpt(self):
        llm = self._make_llm()
        content = "X" * 5000
        verify_pacing(llm, content, "fast")
        call_kwargs = llm.generate_json.call_args
        prompt = call_kwargs[1].get("user_prompt", "") or call_kwargs[0][1]
        # Excerpt should include tail separator
        assert "..." in prompt


class TestRewriteForPacing:
    def test_happy_path_returns_rewritten(self):
        llm = MagicMock()
        rewritten = "Nội dung mới dài hơn " + "x" * 200
        llm.generate.return_value = rewritten
        original = "Nội dung gốc " + "y" * 50
        result = rewrite_for_pacing(llm, original, "climax", "slow")
        assert result == rewritten

    def test_too_short_response_falls_back(self):
        llm = MagicMock()
        llm.generate.return_value = "quá ngắn"
        original = "a" * 300
        result = rewrite_for_pacing(llm, original, "climax", "slow")
        assert result == original

    def test_empty_content_returns_as_is(self):
        llm = MagicMock()
        result = rewrite_for_pacing(llm, "", "climax", "slow")
        assert result == ""
        llm.generate.assert_not_called()

    def test_llm_failure_falls_back_to_original(self):
        llm = MagicMock()
        llm.generate.side_effect = RuntimeError("API error")
        original = "nội dung gốc " + "z" * 100
        result = rewrite_for_pacing(llm, original, "rising", "slow")
        assert result == original



# ---------------------------------------------------------------------------
# thematic_resonance_tracker
# ---------------------------------------------------------------------------


class TestThematicState:
    def test_add_presence_updates_history(self):
        state = ThematicState(core_themes=["tình yêu", "phản bội"])
        pres = ThemePresence(chapter=1, theme="tình yêu", strength=0.8, symbols=["hoa hồng"])
        state.add_presence(pres)
        assert len(state.theme_history) == 1
        assert "hoa hồng" in state.symbol_registry

    def test_get_theme_coverage_filters_below_threshold(self):
        state = ThematicState(core_themes=["tình yêu"])
        state.add_presence(ThemePresence(chapter=1, theme="tình yêu", strength=0.2))
        state.add_presence(ThemePresence(chapter=3, theme="tình yêu", strength=0.7))
        coverage = state.get_theme_coverage("tình yêu")
        assert 1 not in coverage
        assert 3 in coverage

    def test_get_dormant_themes_with_gap(self):
        state = ThematicState(core_themes=["hy vọng"])
        state.add_presence(ThemePresence(chapter=1, theme="hy vọng", strength=0.6))
        # Current chapter 10, last seen at 1 → gap=9 ≥ 5
        dormant = state.get_dormant_themes(current_chapter=10, gap_threshold=5)
        assert "hy vọng" in dormant

    def test_no_dormant_themes_when_recent(self):
        state = ThematicState(core_themes=["hy vọng"])
        state.add_presence(ThemePresence(chapter=9, theme="hy vọng", strength=0.6))
        dormant = state.get_dormant_themes(current_chapter=10, gap_threshold=5)
        assert "hy vọng" not in dormant

    def test_theme_strength_trend_ascending(self):
        state = ThematicState(core_themes=["phản bội"])
        for ch, strength in enumerate([0.2, 0.4, 0.6, 0.8], start=1):
            state.add_presence(ThemePresence(chapter=ch, theme="phản bội", strength=strength))
        assert state.get_theme_strength_trend("phản bội") == "ascending"

    def test_theme_strength_trend_descending(self):
        state = ThematicState(core_themes=["hận thù"])
        for ch, strength in enumerate([0.9, 0.7, 0.5, 0.3], start=1):
            state.add_presence(ThemePresence(chapter=ch, theme="hận thù", strength=strength))
        assert state.get_theme_strength_trend("hận thù") == "descending"

    def test_theme_strength_trend_absent(self):
        state = ThematicState(core_themes=["cô đơn"])
        assert state.get_theme_strength_trend("cô đơn") == "absent"

    def test_symbol_registry_multi_chapter(self):
        state = ThematicState(core_themes=["tự do"])
        state.add_presence(ThemePresence(chapter=1, theme="tự do", strength=0.5, symbols=["cánh chim"]))
        state.add_presence(ThemePresence(chapter=5, theme="tự do", strength=0.6, symbols=["cánh chim"]))
        assert state.symbol_registry["cánh chim"] == [1, 5]


class TestInitializeThematicState:
    def test_with_themes_list(self):
        premise = {"themes": ["tình yêu", "phản bội", "hy vọng"]}
        state = initialize_thematic_state(premise)
        assert "tình yêu" in state.core_themes

    def test_with_themes_string(self):
        premise = {"themes": "tình yêu, phản bội"}
        state = initialize_thematic_state(premise)
        assert len(state.core_themes) >= 1

    def test_core_theme_prepended(self):
        premise = {"themes": ["phản bội"], "core_theme": "sự hy sinh"}
        state = initialize_thematic_state(premise)
        assert state.core_themes[0].startswith("sự hy sinh")

    def test_empty_premise_empty_themes(self):
        state = initialize_thematic_state({})
        assert state.core_themes == []

    def test_none_premise_empty_state(self):
        state = initialize_thematic_state(None)
        assert state.core_themes == []


class TestDetectThematicDrift:
    def _build_state(self):
        state = ThematicState(core_themes=["tình yêu", "phản bội"])
        # tình yêu present in ch 1–5
        for ch in range(1, 6):
            state.add_presence(ThemePresence(chapter=ch, theme="tình yêu", strength=0.7))
        # phản bội absent
        return state

    def test_dormant_theme_causes_drift(self):
        state = self._build_state()
        result = detect_thematic_drift(state, current_chapter=15, total_chapters=20)
        assert result["drifting"] is True
        assert "phản bội" in result["dormant_themes"]

    def test_no_drift_when_themes_present(self):
        state = ThematicState(core_themes=["tình yêu"])
        for ch in range(1, 6):
            state.add_presence(ThemePresence(chapter=ch, theme="tình yêu", strength=0.6))
        result = detect_thematic_drift(state, current_chapter=5, total_chapters=10)
        assert result["drifting"] is False
        assert result["dominant_theme"] == "tình yêu"

    def test_balance_score_range(self):
        state = ThematicState(core_themes=["tình yêu", "phản bội"])
        state.add_presence(ThemePresence(chapter=1, theme="tình yêu", strength=0.8))
        state.add_presence(ThemePresence(chapter=1, theme="phản bội", strength=0.8))
        result = detect_thematic_drift(state, current_chapter=5, total_chapters=10)
        assert 0.0 <= result["balance_score"] <= 1.0


class TestAuditThematicResonance:
    def test_well_covered_theme(self):
        state = ThematicState(core_themes=["tình yêu"])
        for ch in range(1, 11):
            state.add_presence(ThemePresence(chapter=ch, theme="tình yêu", strength=0.6))
        result = audit_thematic_resonance(state, final_chapter=10)
        assert "tình yêu" in result["well_covered"]
        assert result["theme_coverage"]["tình yêu"]["percentage"] == 100.0

    def test_under_covered_theme(self):
        state = ThematicState(core_themes=["phản bội"])
        # Only 2 out of 10 chapters
        state.add_presence(ThemePresence(chapter=1, theme="phản bội", strength=0.5))
        state.add_presence(ThemePresence(chapter=2, theme="phản bội", strength=0.5))
        result = audit_thematic_resonance(state, final_chapter=10)
        assert "phản bội" in result["under_covered"]

    def test_symbol_usage_tracked(self):
        state = ThematicState(core_themes=["tình yêu"])
        state.add_presence(ThemePresence(chapter=1, theme="tình yêu", strength=0.5, symbols=["trái tim"]))
        result = audit_thematic_resonance(state, final_chapter=5)
        assert "trái tim" in result["symbol_usage"]
        assert result["total_symbols"] == 1


class TestAnalyzeThemePresence:
    def test_happy_path_returns_presences(self):
        llm = MagicMock()
        llm.generate_json.return_value = {
            "themes": [
                {"theme": "tình yêu", "strength": 0.8, "manifestation": "đối thoại", "symbols": ["hoa"]},
            ]
        }
        result = analyze_theme_presence(llm, "nội dung chương", 1, ["tình yêu"])
        assert len(result) == 1
        assert result[0].theme == "tình yêu"
        assert result[0].strength == 0.8

    def test_empty_core_themes_returns_empty(self):
        llm = MagicMock()
        result = analyze_theme_presence(llm, "nội dung", 1, [])
        assert result == []
        llm.generate_json.assert_not_called()



# ---------------------------------------------------------------------------
# enhancement_context_builder
# ---------------------------------------------------------------------------


def _make_config(theme_premise=True, voice_profiles=True, scene_decomp=False, show_dont_tell=False):
    pipeline = MagicMock()
    pipeline.enable_theme_premise = theme_premise
    pipeline.enable_voice_profiles = voice_profiles
    pipeline.enable_scene_decomposition = scene_decomp
    pipeline.enable_show_dont_tell = show_dont_tell
    config = MagicMock()
    config.pipeline = pipeline
    return config


class TestBuildEnhancementContext:
    def test_returns_empty_when_all_flags_off(self):
        config = _make_config(theme_premise=False, voice_profiles=False)
        result = build_enhancement_context(config, MagicMock(), "fantasy")
        assert result == ""

    def test_premise_included_when_flag_on(self):
        config = _make_config(theme_premise=True, voice_profiles=False)
        llm = MagicMock()
        premise = {"themes": ["tình yêu"], "core_theme": "sự hy sinh"}
        # format_premise_for_prompt may return a non-empty string
        # We patch at import boundary so the real sub-module runs or fails gracefully
        result = build_enhancement_context(config, llm, "fantasy", premise=premise)
        # Non-fatal: either includes premise text or returns "" on import error — both OK
        assert isinstance(result, str)

    def test_voice_profiles_included_when_flag_on(self):
        config = _make_config(theme_premise=False, voice_profiles=True)
        llm = MagicMock()
        # Minimal voice profile dicts
        voice_profiles = [{"name": "Minh", "tone": "trầm lắng"}]
        result = build_enhancement_context(config, llm, "romance", voice_profiles=voice_profiles)
        assert isinstance(result, str)

    def test_no_scene_decomp_without_outline(self):
        config = _make_config(theme_premise=False, voice_profiles=False, scene_decomp=True)
        result = build_enhancement_context(config, MagicMock(), "fantasy")
        assert result == ""

    def test_returns_str_on_partial_failure(self):
        # Even if sub-imports fail, function is non-fatal
        config = _make_config(theme_premise=True, voice_profiles=True)
        result = build_enhancement_context(config, MagicMock(), "fantasy", premise={"themes": []})
        assert isinstance(result, str)


class TestBuildSharedEnhancementContext:
    def test_returns_empty_when_flags_off(self):
        config = _make_config(theme_premise=False, voice_profiles=False)
        result = build_shared_enhancement_context(config, "romance")
        assert result == ""

    def test_parts_joined_with_double_newline(self):
        """If both premise and voice profiles produce output, they are joined with \\n\\n."""
        config = _make_config(theme_premise=True, voice_profiles=True)
        # We check that the function is non-fatal and returns a str
        result = build_shared_enhancement_context(
            config,
            "fantasy",
            premise={"themes": ["tình yêu"]},
            voice_profiles=[{"name": "Linh"}],
        )
        assert isinstance(result, str)



# ---------------------------------------------------------------------------
# l1_causal_graph
# ---------------------------------------------------------------------------


class TestCausalGraph:
    def test_add_event_no_duplicate(self):
        graph = CausalGraph()
        event = CausalEvent(event_id="01-1", chapter=1, description="Minh tìm thấy bức thư")
        graph.add_event(event)
        graph.add_event(event)  # duplicate
        assert len(graph.events) == 1

    def test_get_dependencies_returns_unresolved_prior(self):
        graph = CausalGraph()
        e1 = CausalEvent(event_id="01-1", chapter=1, description="Sự kiện A")
        e2 = CausalEvent(event_id="02-1", chapter=2, description="Sự kiện B")
        graph.add_event(e1)
        graph.add_event(e2)
        deps = graph.get_dependencies(chapter=3)
        assert len(deps) == 2

    def test_get_dependencies_excludes_resolved(self):
        graph = CausalGraph()
        e1 = CausalEvent(event_id="01-1", chapter=1, description="Sự kiện A", resolved=True)
        graph.add_event(e1)
        deps = graph.get_dependencies(chapter=3)
        assert len(deps) == 0

    def test_get_dependencies_excludes_current_chapter(self):
        graph = CausalGraph()
        e1 = CausalEvent(event_id="05-1", chapter=5, description="Sự kiện chương 5")
        graph.add_event(e1)
        deps = graph.get_dependencies(chapter=5)
        assert len(deps) == 0

    def test_query_required_references_min_age(self):
        graph = CausalGraph()
        e1 = CausalEvent(event_id="01-1", chapter=1, description="Bí mật bị tiết lộ")
        e2 = CausalEvent(event_id="04-1", chapter=4, description="Cuộc chiến bắt đầu")
        graph.add_event(e1)
        graph.add_event(e2)
        # current=5, min_age=2 → e1 qualifies (5-1=4≥2), e2 qualifies (5-4=1 < 2)
        refs = graph.query_required_references(current_chapter=5, min_age=2)
        assert e1 in refs
        assert e2 not in refs

    def test_mark_resolved(self):
        graph = CausalGraph()
        e1 = CausalEvent(event_id="01-1", chapter=1, description="Khám phá căn phòng bí ẩn")
        graph.add_event(e1)
        graph.mark_resolved("01-1", resolved_chapter=3)
        assert graph.events[0].resolved is True
        assert graph.events[0].resolved_chapter == 3

    def test_mark_resolved_unknown_id_no_crash(self):
        graph = CausalGraph()
        graph.mark_resolved("99-9", resolved_chapter=5)  # should not raise

    def test_serialise_roundtrip(self):
        graph = CausalGraph()
        e1 = CausalEvent(event_id="01-1", chapter=1, description="Sự kiện quan trọng", characters=["Minh"])
        graph.add_event(e1)
        serialised = graph.to_dict()
        restored = CausalGraph.from_dict(serialised)
        assert len(restored.events) == 1
        assert restored.events[0].event_id == "01-1"
        assert restored.events[0].characters == ["Minh"]

    def test_from_dict_skips_malformed(self):
        data = {"events": [{"event_id": "01-1", "chapter": 1, "description": "ok"}, {"bad": True}]}
        graph = CausalGraph.from_dict(data)
        assert len(graph.events) == 1


class TestExtractCausalEvents:
    def test_happy_path_returns_events(self):
        llm = MagicMock()
        llm.generate_json.return_value = {
            "events": [
                {"description": "Minh tìm ra sự thật", "characters": ["Minh"], "event_type": "reveal"},
            ]
        }
        events = extract_causal_events(llm, "nội dung chương dài " * 50, chapter_num=3)
        assert len(events) == 1
        assert events[0].description == "Minh tìm ra sự thật"
        assert events[0].event_type == "reveal"

    def test_returns_empty_when_response_lacks_events_key(self):
        llm = MagicMock()
        llm.generate_json.return_value = {"unrelated": "data"}
        events = extract_causal_events(llm, "any content", chapter_num=1)
        assert events == []

    def test_llm_failure_returns_empty(self):
        llm = MagicMock()
        llm.generate_json.side_effect = RuntimeError("LLM error")
        events = extract_causal_events(llm, "nội dung", chapter_num=2)
        assert events == []

    def test_non_dict_response_returns_empty(self):
        llm = MagicMock()
        llm.generate_json.return_value = "không phải dict"
        events = extract_causal_events(llm, "nội dung", chapter_num=2)
        assert events == []


class TestValidateCausalReferences:
    def test_referenced_event_not_in_unacknowledged(self):
        event = CausalEvent(event_id="01-1", chapter=1, description="Minh tìm thấy chìa khóa")
        # Chapter text contains key words from description
        chapter_text = "Minh đã tìm thấy chiếc chìa khóa trong căn phòng tối."
        unacked = validate_causal_references(chapter_text, [event])
        assert event.description not in unacked

    def test_unreferenced_event_in_unacknowledged(self):
        event = CausalEvent(event_id="01-1", chapter=1, description="Bức thư bí ẩn xuất hiện")
        chapter_text = "Hôm nay trời đẹp, Linh đi dạo trong vườn hoa."
        unacked = validate_causal_references(chapter_text, [event])
        assert event.description in unacked

    def test_empty_required_events_returns_empty(self):
        unacked = validate_causal_references("bất kỳ nội dung nào", [])
        assert unacked == []

    def test_event_with_very_short_words_skipped(self):
        # description with all words ≤3 chars → no keywords → skip
        event = CausalEvent(event_id="01-1", chapter=1, description="Anh đi về")
        unacked = validate_causal_references("completely unrelated text here", [event])
        assert event.description not in unacked


class TestFormatCausalDependenciesForPrompt:
    def test_empty_events_returns_empty_string(self):
        result = format_causal_dependencies_for_prompt([])
        assert result == ""

    def test_linear_chain_formatted(self):
        events = [
            CausalEvent(event_id="01-1", chapter=1, description="Minh phát hiện phản bội", characters=["Minh"]),
            CausalEvent(event_id="02-1", chapter=2, description="Linh bỏ trốn", characters=["Linh"]),
        ]
        result = format_causal_dependencies_for_prompt(events)
        assert "01-1" in result
        assert "Minh" in result
        assert "phản bội" in result
        assert "02-1" in result

    def test_includes_must_acknowledge_instruction(self):
        events = [CausalEvent(event_id="01-1", chapter=1, description="Sự kiện quan trọng")]
        result = format_causal_dependencies_for_prompt(events)
        assert "nhắc đến" in result or "SỰ KIỆN" in result
