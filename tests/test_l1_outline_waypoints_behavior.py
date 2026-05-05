"""Behavior tests for 5 L1 outline/waypoint modules.

Modules:
  - outline_builder (suggest_titles, generate_title_from_idea, generate_outline, _parse_outline_response)
  - macro_outline_builder (generate_macro_arcs, get_arc_for_chapter, format_arcs_for_prompt)
  - outline_arc_validator (validate_outline_arc_coherence)
  - arc_waypoint_generator (generate_arc_waypoints, apply_waypoints_to_characters,
                             get_expected_stage, format_arc_stages_for_prompt,
                             update_arc_progression_cache, format_arc_progression_for_prompt)
  - arc_execution_validator (validate_arc_execution_heuristic, validate_all_arcs,
                              format_arc_warnings, get_arc_drift_summary)
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from models.narrative_schemas import ArcWaypoint
from models.schemas import Character, ChapterOutline, Chapter, MacroArc, WorldSetting

# ---------------------------------------------------------------------------
# Helpers / Fixtures
# ---------------------------------------------------------------------------


def _make_llm(return_value=None):
    """Return a mock LLMClient whose generate_json returns *return_value*."""
    llm = MagicMock()
    llm.generate_json.return_value = return_value or {}
    return llm


def _make_character(
    name: str = "Lan",
    role: str = "main",
    personality: str = "dũng cảm",
    motivation: str = "trả thù",
    arc_trajectory: str = "từ hèn nhát → can đảm",
    internal_conflict: str = "sợ mất gia đình",
    waypoints: list | None = None,
) -> Character:
    c = Character(
        name=name,
        role=role,
        personality=personality,
        motivation=motivation,
        arc_trajectory=arc_trajectory,
        internal_conflict=internal_conflict,
    )
    if waypoints is not None:
        c.arc_waypoints = [wp.model_dump() if isinstance(wp, ArcWaypoint) else wp for wp in waypoints]
    return c


def _make_world(name: str = "Giang hồ", description: str = "Thế giới võ lâm") -> WorldSetting:
    return WorldSetting(name=name, description=description)


def _make_outline(
    chapter_number: int = 1,
    title: str = "Chương mở đầu",
    summary: str = "Nhân vật ra đi",
    pacing_type: str = "rising",
    characters_involved: list | None = None,
    arc_id: int = 1,
) -> ChapterOutline:
    return ChapterOutline(
        chapter_number=chapter_number,
        title=title,
        summary=summary,
        pacing_type=pacing_type,
        characters_involved=characters_involved or ["Lan"],
        arc_id=arc_id,
    )


def _make_macro_arc(
    arc_number: int = 1,
    name: str = "Arc khởi đầu",
    chapter_start: int = 1,
    chapter_end: int = 10,
    central_conflict: str = "Xung đột chính",
    character_focus: list | None = None,
) -> MacroArc:
    return MacroArc(
        arc_number=arc_number,
        name=name,
        chapter_start=chapter_start,
        chapter_end=chapter_end,
        central_conflict=central_conflict,
        character_focus=character_focus or ["Lan"],
    )


def _make_waypoint(
    stage_name: str = "phủ nhận",
    chapter_range: list | None = None,
    description: str = "Từ chối thay đổi",
    emotional_state: str = "sợ hãi",
    progress_pct: float = 0.2,
) -> ArcWaypoint:
    return ArcWaypoint(
        stage_name=stage_name,
        chapter_range=chapter_range or [1, 10],
        description=description,
        emotional_state=emotional_state,
        progress_pct=progress_pct,
    )


def _make_chapter(chapter_number: int = 1, content: str = "") -> Chapter:
    return Chapter(chapter_number=chapter_number, title=f"Chương {chapter_number}", content=content)


# ===========================================================================
# 1. outline_builder
# ===========================================================================


class TestSuggestTitles:
    def test_returns_titles_from_dict(self):
        from pipeline.layer1_story.outline_builder import suggest_titles

        llm = _make_llm({"titles": ["Kiếm khách giang hồ", "Bóng tối phương đông"]})
        result = suggest_titles(llm, genre="tiên hiệp")
        assert result == ["Kiếm khách giang hồ", "Bóng tối phương đông"]

    def test_returns_list_directly_when_llm_returns_list(self):
        from pipeline.layer1_story.outline_builder import suggest_titles

        llm = _make_llm(["Trời xanh mây trắng", "Kiếm hồn"])
        result = suggest_titles(llm, genre="ngôn tình")
        assert isinstance(result, list)
        assert "Kiếm hồn" in result

    def test_empty_titles_fallback(self):
        from pipeline.layer1_story.outline_builder import suggest_titles

        llm = _make_llm({})  # no "titles" key
        result = suggest_titles(llm, genre="huyền huyễn")
        assert result == []

    def test_passes_requirements_to_prompt(self):
        from pipeline.layer1_story.outline_builder import suggest_titles

        llm = _make_llm({"titles": []})
        suggest_titles(llm, genre="tiên hiệp", requirements="cần tên đặc sắc")
        call_kwargs = llm.generate_json.call_args
        assert "cần tên đặc sắc" in call_kwargs[1].get("user_prompt", "") or \
               "cần tên đặc sắc" in str(call_kwargs)


class TestGenerateTitleFromIdea:
    def test_returns_title_from_dict(self):
        from pipeline.layer1_story.outline_builder import generate_title_from_idea

        llm = _make_llm({"title": "Huyết chiến giang hồ"})
        result = generate_title_from_idea(llm, genre="võ hiệp", idea="kẻ phản bội trở về")
        assert result == "Huyết chiến giang hồ"

    def test_returns_str_directly_when_llm_returns_string(self):
        from pipeline.layer1_story.outline_builder import generate_title_from_idea

        llm = _make_llm("Hồi kết bi tráng")
        result = generate_title_from_idea(llm, genre="hành động", idea="")
        assert result == "Hồi kết bi tráng"

    def test_fallback_when_no_title_key(self):
        from pipeline.layer1_story.outline_builder import generate_title_from_idea

        llm = _make_llm({})
        result = generate_title_from_idea(llm, genre="kinh dị", idea="ma quỷ")
        assert "kinh dị" in result  # fallback includes genre


class TestParseOutlineResponse:
    def test_parses_dict_with_outlines(self):
        from pipeline.layer1_story.outline_builder import _parse_outline_response

        raw = {
            "synopsis": "Câu chuyện bi kịch",
            "outlines": [
                {"chapter_number": 1, "title": "Mở đầu", "summary": "Nhân vật gặp khó khăn"},
            ],
        }
        synopsis, outlines = _parse_outline_response(raw)
        assert synopsis == "Câu chuyện bi kịch"
        assert len(outlines) == 1
        assert outlines[0].chapter_number == 1

    def test_parses_list_directly(self):
        from pipeline.layer1_story.outline_builder import _parse_outline_response

        raw = [
            {"chapter_number": 1, "title": "Ch1", "summary": "Bắt đầu"},
            {"chapter_number": 2, "title": "Ch2", "summary": "Tiếp theo"},
        ]
        synopsis, outlines = _parse_outline_response(raw)
        assert synopsis == ""
        assert len(outlines) == 2

    def test_fills_missing_chapter_number(self):
        from pipeline.layer1_story.outline_builder import _parse_outline_response

        raw = {"outlines": [{"title": "Auto number", "summary": "test"}]}
        _, outlines = _parse_outline_response(raw)
        assert outlines[0].chapter_number == 1

    def test_skips_non_dict_items(self):
        from pipeline.layer1_story.outline_builder import _parse_outline_response

        raw = {"outlines": ["not a dict", {"chapter_number": 1, "title": "ok", "summary": "s"}]}
        _, outlines = _parse_outline_response(raw)
        assert len(outlines) == 1

    def test_empty_outlines_returns_empty_list(self):
        from pipeline.layer1_story.outline_builder import _parse_outline_response

        synopsis, outlines = _parse_outline_response({"synopsis": "x", "outlines": []})
        assert outlines == []


class TestGenerateOutline:
    def _valid_llm(self, num_chapters: int = 3):
        outlines_data = [
            {"chapter_number": i, "title": f"Ch{i}", "summary": f"s{i}"}
            for i in range(1, num_chapters + 1)
        ]
        return _make_llm({"synopsis": "Tóm tắt test", "outlines": outlines_data})

    def test_returns_correct_count(self):
        from pipeline.layer1_story.outline_builder import generate_outline

        llm = self._valid_llm(3)
        chars = [_make_character()]
        world = _make_world()
        synopsis, outlines = generate_outline(llm, "Title", "tiên hiệp", chars, world, "idea", num_chapters=3)
        assert len(outlines) == 3
        assert synopsis == "Tóm tắt test"

    def test_trims_excess_outlines(self):
        from pipeline.layer1_story.outline_builder import generate_outline

        # LLM returns 5 but only 3 requested
        llm = self._valid_llm(5)
        chars = [_make_character()]
        world = _make_world()
        _, outlines = generate_outline(llm, "T", "g", chars, world, "i", num_chapters=3)
        assert len(outlines) == 3

    def test_retry_on_empty_first_response(self):
        from pipeline.layer1_story.outline_builder import generate_outline

        # First call returns empty; second call returns valid outlines
        valid_resp = {
            "synopsis": "retry synopsis",
            "outlines": [{"chapter_number": 1, "title": "C1", "summary": "s"}],
        }
        llm = _make_llm({})
        llm.generate_json.side_effect = [{}, valid_resp]
        chars = [_make_character()]
        world = _make_world()
        synopsis, outlines = generate_outline(llm, "T", "g", chars, world, "i", num_chapters=1)
        assert len(outlines) == 1
        assert llm.generate_json.call_count == 2

    def test_fills_missing_chapters_with_placeholders(self):
        from pipeline.layer1_story.outline_builder import generate_outline

        # LLM returns only ch1, need 3 — fill call also returns empty
        first_resp = {"synopsis": "s", "outlines": [{"chapter_number": 1, "title": "C1", "summary": "s"}]}
        fill_resp = {}  # fill call returns empty → placeholders
        llm = _make_llm({})
        llm.generate_json.side_effect = [first_resp, fill_resp]
        chars = [_make_character("Hùng")]
        world = _make_world()
        _, outlines = generate_outline(llm, "T", "g", chars, world, "i", num_chapters=3)
        assert len(outlines) == 3
        chapter_nums = {o.chapter_number for o in outlines}
        assert chapter_nums == {1, 2, 3}

    def test_injects_macro_arcs_into_prompt(self):
        from pipeline.layer1_story.outline_builder import generate_outline

        llm = self._valid_llm(1)
        chars = [_make_character()]
        world = _make_world()
        arcs = [_make_macro_arc()]
        generate_outline(llm, "T", "tiên hiệp", chars, world, "i", num_chapters=1, macro_arcs=arcs)
        call_kwargs = llm.generate_json.call_args_list[0]
        prompt = str(call_kwargs)
        assert "Arc" in prompt or "arc" in prompt


# ===========================================================================
# 2. macro_outline_builder
# ===========================================================================


class TestGenerateMacroArcs:
    def test_happy_path_returns_arcs(self):
        from pipeline.layer1_story.macro_outline_builder import generate_macro_arcs

        arc_data = [
            {"arc_number": 1, "name": "Khởi đầu", "chapter_start": 1, "chapter_end": 30,
             "central_conflict": "Xung đột A", "character_focus": ["Lan"]},
        ]
        llm = _make_llm({"macro_arcs": arc_data})
        chars = [_make_character()]
        world = _make_world()
        arcs = generate_macro_arcs(llm, "Title", "tiên hiệp", chars, world, "idea", num_chapters=100)
        assert len(arcs) == 1
        assert arcs[0].name == "Khởi đầu"

    def test_handles_list_response_directly(self):
        from pipeline.layer1_story.macro_outline_builder import generate_macro_arcs

        arc_data = [
            {"arc_number": 1, "name": "Arc A", "chapter_start": 1, "chapter_end": 10,
             "central_conflict": "conflict", "character_focus": []},
        ]
        llm = _make_llm(arc_data)  # LLM returns list directly
        chars = [_make_character()]
        world = _make_world()
        arcs = generate_macro_arcs(llm, "T", "g", chars, world, "i", num_chapters=10)
        assert len(arcs) == 1

    def test_fallback_single_arc_on_empty(self):
        from pipeline.layer1_story.macro_outline_builder import generate_macro_arcs

        llm = _make_llm({})  # no macro_arcs key
        chars = [_make_character()]
        world = _make_world()
        arcs = generate_macro_arcs(llm, "T", "g", chars, world, "i", num_chapters=20)
        assert len(arcs) == 1
        assert arcs[0].chapter_end == 20  # covers all chapters

    def test_clamps_chapter_end_to_num_chapters(self):
        from pipeline.layer1_story.macro_outline_builder import generate_macro_arcs

        arc_data = [
            {"arc_number": 1, "name": "A", "chapter_start": 1, "chapter_end": 999,
             "central_conflict": "c", "character_focus": []},
        ]
        llm = _make_llm({"macro_arcs": arc_data})
        chars = [_make_character()]
        world = _make_world()
        arcs = generate_macro_arcs(llm, "T", "g", chars, world, "i", num_chapters=50)
        assert arcs[0].chapter_end == 50

    def test_skips_arcs_starting_beyond_num_chapters(self):
        from pipeline.layer1_story.macro_outline_builder import generate_macro_arcs

        arc_data = [
            {"arc_number": 1, "name": "valid", "chapter_start": 1, "chapter_end": 10,
             "central_conflict": "c", "character_focus": []},
            {"arc_number": 2, "name": "beyond", "chapter_start": 999, "chapter_end": 1000,
             "central_conflict": "c", "character_focus": []},
        ]
        llm = _make_llm({"macro_arcs": arc_data})
        chars = [_make_character()]
        world = _make_world()
        arcs = generate_macro_arcs(llm, "T", "g", chars, world, "i", num_chapters=10)
        assert len(arcs) == 1
        assert arcs[0].name == "valid"

    def test_scales_arc_size_for_short_story(self):
        """arc_size should be scaled down when num_chapters is small."""
        from pipeline.layer1_story.macro_outline_builder import generate_macro_arcs

        arc_data = [
            {"arc_number": 1, "name": "only", "chapter_start": 1, "chapter_end": 5,
             "central_conflict": "c", "character_focus": []},
        ]
        llm = _make_llm({"macro_arcs": arc_data})
        chars = [_make_character()]
        world = _make_world()
        # arc_size=30 but num_chapters=5 → should be clamped
        arcs = generate_macro_arcs(llm, "T", "g", chars, world, "i", num_chapters=5, arc_size=30)
        assert arcs  # just ensure no crash


class TestGetArcForChapter:
    def test_returns_matching_arc(self):
        from pipeline.layer1_story.macro_outline_builder import get_arc_for_chapter

        arcs = [
            _make_macro_arc(arc_number=1, chapter_start=1, chapter_end=10),
            _make_macro_arc(arc_number=2, chapter_start=11, chapter_end=20),
        ]
        arc = get_arc_for_chapter(arcs, chapter_number=5)
        assert arc.arc_number == 1

    def test_returns_last_arc_when_no_match(self):
        from pipeline.layer1_story.macro_outline_builder import get_arc_for_chapter

        arcs = [_make_macro_arc(arc_number=1, chapter_start=1, chapter_end=5)]
        arc = get_arc_for_chapter(arcs, chapter_number=99)
        assert arc.arc_number == 1  # fallback = last arc

    def test_returns_none_for_empty_list(self):
        from pipeline.layer1_story.macro_outline_builder import get_arc_for_chapter

        result = get_arc_for_chapter([], chapter_number=1)
        assert result is None

    def test_exact_boundary_match(self):
        from pipeline.layer1_story.macro_outline_builder import get_arc_for_chapter

        arcs = [_make_macro_arc(arc_number=1, chapter_start=1, chapter_end=10)]
        assert get_arc_for_chapter(arcs, 1).arc_number == 1
        assert get_arc_for_chapter(arcs, 10).arc_number == 1


class TestFormatArcsForPrompt:
    def test_formats_single_arc(self):
        from pipeline.layer1_story.macro_outline_builder import format_arcs_for_prompt

        arcs = [_make_macro_arc(arc_number=1, name="Kiếm đạo", chapter_start=1, chapter_end=30)]
        text = format_arcs_for_prompt(arcs)
        assert "Arc 1" in text
        assert "Kiếm đạo" in text
        assert "Ch.1-30" in text

    def test_formats_multiple_arcs(self):
        from pipeline.layer1_story.macro_outline_builder import format_arcs_for_prompt

        arcs = [
            _make_macro_arc(arc_number=1, chapter_start=1, chapter_end=10),
            _make_macro_arc(arc_number=2, name="Arc kết", chapter_start=11, chapter_end=20),
        ]
        text = format_arcs_for_prompt(arcs)
        assert "Arc 1" in text
        assert "Arc 2" in text
        assert text.count("\n") >= 1  # two lines


# ===========================================================================
# 3. outline_arc_validator
# ===========================================================================


class TestValidateOutlineArcCoherence:
    def test_returns_ok_on_empty_inputs(self):
        from pipeline.layer1_story.outline_arc_validator import validate_outline_arc_coherence

        llm = _make_llm({})
        result = validate_outline_arc_coherence(llm, outlines=[], macro_arcs=[])
        assert result == {"warnings": [], "score": 5.0}
        llm.generate_json.assert_not_called()

    def test_returns_warnings_from_llm(self):
        from pipeline.layer1_story.outline_arc_validator import validate_outline_arc_coherence

        llm = _make_llm({"warnings": ["Arc 1 thiếu climax"], "score": 3.5})
        outlines = [_make_outline()]
        arcs = [_make_macro_arc()]
        result = validate_outline_arc_coherence(llm, outlines, arcs)
        assert result["warnings"] == ["Arc 1 thiếu climax"]
        assert result["score"] == pytest.approx(3.5)

    def test_returns_perfect_score_when_no_warnings(self):
        from pipeline.layer1_story.outline_arc_validator import validate_outline_arc_coherence

        llm = _make_llm({"warnings": [], "score": 5.0})
        result = validate_outline_arc_coherence(llm, [_make_outline()], [_make_macro_arc()])
        assert result["score"] == pytest.approx(5.0)
        assert result["warnings"] == []

    def test_returns_zero_score_on_llm_exception(self):
        from pipeline.layer1_story.outline_arc_validator import validate_outline_arc_coherence

        llm = MagicMock()
        llm.generate_json.side_effect = RuntimeError("LLM offline")
        result = validate_outline_arc_coherence(llm, [_make_outline()], [_make_macro_arc()])
        assert result["score"] == 0.0
        assert result["warnings"] == []

    def test_calls_llm_once(self):
        from pipeline.layer1_story.outline_arc_validator import validate_outline_arc_coherence

        llm = _make_llm({"warnings": [], "score": 4.0})
        validate_outline_arc_coherence(llm, [_make_outline()], [_make_macro_arc()])
        assert llm.generate_json.call_count == 1

    def test_missing_fields_fall_back_gracefully(self):
        from pipeline.layer1_story.outline_arc_validator import validate_outline_arc_coherence

        llm = _make_llm({})  # no warnings / score keys
        result = validate_outline_arc_coherence(llm, [_make_outline()], [_make_macro_arc()])
        assert "warnings" in result
        assert "score" in result


# ===========================================================================
# 4. arc_waypoint_generator
# ===========================================================================


class TestGenerateArcWaypoints:
    def _llm_with_waypoints(self, char_name: str = "Lan"):
        resp = {
            "characters": [
                {
                    "name": char_name,
                    "waypoints": [
                        {
                            "stage_name": "phủ nhận",
                            "chapter_start": 1,
                            "chapter_end": 10,
                            "description": "Từ chối thay đổi",
                            "emotional_state": "sợ hãi",
                            "progress_pct": 0.2,
                        }
                    ],
                }
            ]
        }
        return _make_llm(resp)

    def test_returns_waypoints_for_character(self):
        from pipeline.layer1_story.arc_waypoint_generator import generate_arc_waypoints

        chars = [_make_character("Lan")]
        result = generate_arc_waypoints(self._llm_with_waypoints("Lan"), chars, num_chapters=20, genre="tiên hiệp")
        assert "Lan" in result
        assert len(result["Lan"]) == 1
        assert result["Lan"][0].stage_name == "phủ nhận"

    def test_returns_empty_on_llm_failure(self):
        from pipeline.layer1_story.arc_waypoint_generator import generate_arc_waypoints

        llm = MagicMock()
        llm.generate_json.side_effect = RuntimeError("Network error")
        result = generate_arc_waypoints(llm, [_make_character()], num_chapters=10)
        assert result == {}

    def test_skips_character_with_no_waypoints(self):
        from pipeline.layer1_story.arc_waypoint_generator import generate_arc_waypoints

        resp = {"characters": [{"name": "Lan", "waypoints": []}]}
        llm = _make_llm(resp)
        result = generate_arc_waypoints(llm, [_make_character("Lan")], num_chapters=10)
        assert "Lan" not in result  # empty waypoints → not included

    def test_skips_entries_with_no_name(self):
        from pipeline.layer1_story.arc_waypoint_generator import generate_arc_waypoints

        resp = {"characters": [{"name": "", "waypoints": [{"stage_name": "s", "chapter_start": 1,
                                                            "chapter_end": 5, "description": "d",
                                                            "emotional_state": "e", "progress_pct": 0.1}]}]}
        llm = _make_llm(resp)
        result = generate_arc_waypoints(llm, [_make_character("X")], num_chapters=10)
        assert result == {}

    def test_multiple_characters_all_present(self):
        from pipeline.layer1_story.arc_waypoint_generator import generate_arc_waypoints

        def make_wp(name):
            return {"name": name, "waypoints": [
                {"stage_name": "khởi đầu", "chapter_start": 1, "chapter_end": 5,
                 "description": "d", "emotional_state": "bình tĩnh", "progress_pct": 0.1}
            ]}
        resp = {"characters": [make_wp("Lan"), make_wp("Hùng")]}
        llm = _make_llm(resp)
        chars = [_make_character("Lan"), _make_character("Hùng")]
        result = generate_arc_waypoints(llm, chars, num_chapters=10)
        assert "Lan" in result
        assert "Hùng" in result


class TestApplyWaypointsToCharacters:
    def test_attaches_waypoints_to_matching_character(self):
        from pipeline.layer1_story.arc_waypoint_generator import apply_waypoints_to_characters

        char = _make_character("Lan")
        wp = _make_waypoint()
        apply_waypoints_to_characters([char], {"Lan": [wp]})
        assert len(char.arc_waypoints) == 1
        assert char.arc_waypoints[0]["stage_name"] == "phủ nhận"

    def test_no_op_for_unknown_character(self):
        from pipeline.layer1_story.arc_waypoint_generator import apply_waypoints_to_characters

        char = _make_character("Hùng")
        apply_waypoints_to_characters([char], {"Lan": [_make_waypoint()]})
        assert char.arc_waypoints == []  # untouched


class TestGetExpectedStage:
    def test_returns_matching_waypoint(self):
        from pipeline.layer1_story.arc_waypoint_generator import get_expected_stage

        wp = _make_waypoint(chapter_range=[5, 15])
        char = _make_character(waypoints=[wp])
        result = get_expected_stage(char, chapter_number=10)
        assert result is not None
        assert result.stage_name == "phủ nhận"

    def test_returns_none_when_out_of_range(self):
        from pipeline.layer1_story.arc_waypoint_generator import get_expected_stage

        wp = _make_waypoint(chapter_range=[1, 5])
        char = _make_character(waypoints=[wp])
        assert get_expected_stage(char, chapter_number=20) is None

    def test_returns_none_when_no_waypoints(self):
        from pipeline.layer1_story.arc_waypoint_generator import get_expected_stage

        char = _make_character()
        assert get_expected_stage(char, chapter_number=3) is None

    def test_boundary_inclusive(self):
        from pipeline.layer1_story.arc_waypoint_generator import get_expected_stage

        wp = _make_waypoint(chapter_range=[1, 10])
        char = _make_character(waypoints=[wp])
        assert get_expected_stage(char, 1) is not None
        assert get_expected_stage(char, 10) is not None
        assert get_expected_stage(char, 11) is None


class TestFormatArcStagesForPrompt:
    def test_returns_nonempty_when_waypoint_matches(self):
        from pipeline.layer1_story.arc_waypoint_generator import format_arc_stages_for_prompt

        wp = _make_waypoint(stage_name="khủng hoảng", chapter_range=[1, 20], progress_pct=0.5)
        char = _make_character("Lan", waypoints=[wp])
        result = format_arc_stages_for_prompt([char], chapter_number=10)
        assert "Lan" in result
        assert "khủng hoảng" in result
        assert "50%" in result

    def test_returns_empty_string_when_no_match(self):
        from pipeline.layer1_story.arc_waypoint_generator import format_arc_stages_for_prompt

        char = _make_character()  # no waypoints
        result = format_arc_stages_for_prompt([char], chapter_number=5)
        assert result == ""


class TestUpdateArcProgressionCache:
    def _make_result(self, name, chapter, stage, found, confidence, severity):
        from pipeline.layer1_story.arc_execution_validator import ArcValidationResult

        return ArcValidationResult(
            character=name,
            chapter_number=chapter,
            expected_stage=stage,
            expected_emotion="sợ hãi",
            found=found,
            confidence=confidence,
            evidence="test",
            severity=severity,
        )

    def test_adds_entry_to_cache(self):
        from pipeline.layer1_story.arc_waypoint_generator import update_arc_progression_cache

        cache: dict = {}
        r = self._make_result("Lan", 1, "phủ nhận", True, 0.8, "ok")
        update_arc_progression_cache(cache, [r], chapter_number=1)
        assert "Lan" in cache
        assert cache["Lan"][0]["chapter"] == 1
        assert cache["Lan"][0]["found"] is True

    def test_deduplicates_same_chapter(self):
        from pipeline.layer1_story.arc_waypoint_generator import update_arc_progression_cache

        cache: dict = {}
        r1 = self._make_result("Lan", 3, "phủ nhận", False, 0.0, "warning")
        r2 = self._make_result("Lan", 3, "thức tỉnh", True, 0.9, "ok")
        update_arc_progression_cache(cache, [r1], 3)
        update_arc_progression_cache(cache, [r2], 3)
        assert len(cache["Lan"]) == 1
        assert cache["Lan"][0]["stage_name"] == "thức tỉnh"

    def test_caps_at_max_per_character(self):
        from pipeline.layer1_story.arc_waypoint_generator import update_arc_progression_cache

        cache: dict = {}
        for ch in range(1, 20):
            r = self._make_result("Lan", ch, "s", True, 0.5, "ok")
            update_arc_progression_cache(cache, [r], ch, cap_per_character=5)
        assert len(cache["Lan"]) == 5


class TestFormatArcProgressionForPrompt:
    def _make_result(self, name, chapter, stage, found, confidence, severity):
        from pipeline.layer1_story.arc_execution_validator import ArcValidationResult

        return ArcValidationResult(
            character=name, chapter_number=chapter, expected_stage=stage,
            expected_emotion="", found=found, confidence=confidence,
            evidence="", severity=severity,
        )

    def test_returns_empty_for_empty_cache(self):
        from pipeline.layer1_story.arc_waypoint_generator import format_arc_progression_for_prompt

        chars = [_make_character("Lan")]
        assert format_arc_progression_for_prompt({}, chars, 5) == ""

    def test_formats_history_for_character(self):
        from pipeline.layer1_story.arc_waypoint_generator import (
            format_arc_progression_for_prompt,
            update_arc_progression_cache,
        )

        cache: dict = {}
        results = [self._make_result("Lan", ch, "phủ nhận", True, 0.7, "ok") for ch in [1, 2, 3]]
        for r in results:
            update_arc_progression_cache(cache, [r], r.chapter_number)

        chars = [_make_character("Lan")]
        text = format_arc_progression_for_prompt(cache, chars, current_chapter=4, lookback=3)
        assert "Lan" in text
        assert "ch1" in text or "ch2" in text


# ===========================================================================
# 5. arc_execution_validator
# ===========================================================================


class TestFindCharacterMentions:
    def test_finds_mentions_by_full_name(self):
        from pipeline.layer1_story.arc_execution_validator import _find_character_mentions

        content = "Lan cảm thấy sợ hãi. Hùng bước vào phòng. Lan lùi lại."
        mentions = _find_character_mentions(content, "Lan")
        assert len(mentions) >= 2
        assert any("Lan" in m for m in mentions)

    def test_returns_empty_when_not_mentioned(self):
        from pipeline.layer1_story.arc_execution_validator import _find_character_mentions

        mentions = _find_character_mentions("Không có ai ở đây.", "Minh")
        assert mentions == []


class TestHeuristicEmotionMatch:
    def test_detects_fear_keyword(self):
        from pipeline.layer1_story.arc_execution_validator import _heuristic_emotion_match

        found, confidence, evidence = _heuristic_emotion_match("Cô ấy run rẩy trước mặt kẻ thù.", "sợ hãi")
        assert found is True
        assert confidence > 0.0
        assert evidence != ""

    def test_no_match_returns_false(self):
        from pipeline.layer1_story.arc_execution_validator import _heuristic_emotion_match

        found, confidence, _ = _heuristic_emotion_match("Trời xanh mây trắng đẹp lắm.", "tức giận")
        assert found is False
        assert confidence == 0.0


class TestHeuristicStageMatch:
    def test_detects_stage_keyword(self):
        from pipeline.layer1_story.arc_execution_validator import _heuristic_stage_match

        found, conf, ev = _heuristic_stage_match("Anh ta đã thức tỉnh sau biến cố lớn.", "thức tỉnh")
        assert found is True
        assert conf >= 0.6

    def test_no_stage_match(self):
        from pipeline.layer1_story.arc_execution_validator import _heuristic_stage_match

        found, _, _ = _heuristic_stage_match("Mọi người vui vẻ ăn uống.", "khủng hoảng")
        assert found is False


class TestValidateArcExecutionHeuristic:
    def test_returns_none_when_no_waypoint(self):
        from pipeline.layer1_story.arc_execution_validator import validate_arc_execution_heuristic

        char = _make_character()  # no waypoints
        chapter = _make_chapter(1, "Lan đi vào rừng.")
        assert validate_arc_execution_heuristic(chapter, char, 1) is None

    def test_warning_when_character_not_mentioned(self):
        from pipeline.layer1_story.arc_execution_validator import validate_arc_execution_heuristic

        wp = _make_waypoint(chapter_range=[1, 5])
        char = _make_character("Lan", waypoints=[wp])
        chapter = _make_chapter(1, content="Hùng đang chiến đấu dũng cảm.")
        result = validate_arc_execution_heuristic(chapter, char, 1)
        assert result is not None
        assert result.found is False
        assert result.severity == "warning"

    def test_ok_severity_when_emotion_found_with_high_confidence(self):
        from pipeline.layer1_story.arc_execution_validator import validate_arc_execution_heuristic

        wp = _make_waypoint(stage_name="phủ nhận", emotional_state="sợ hãi", chapter_range=[1, 5])
        char = _make_character("Lan", waypoints=[wp])
        # Content has "Lan" + fear keyword
        chapter = _make_chapter(1, content="Lan run rẩy khi nhìn thấy kẻ thù tiến đến.")
        result = validate_arc_execution_heuristic(chapter, char, 1)
        assert result is not None
        assert result.found is True
        assert result.severity in ("ok", "warning")

    def test_critical_when_not_found_and_high_progress(self):
        from pipeline.layer1_story.arc_execution_validator import validate_arc_execution_heuristic

        wp = _make_waypoint(
            stage_name="hy sinh",
            emotional_state="cuồng nộ",
            chapter_range=[8, 10],
            progress_pct=0.9,
        )
        char = _make_character("Lan", waypoints=[wp])
        # Content mentions Lan but has none of the sacrifice/anger keywords
        chapter = _make_chapter(9, content="Lan đang đọc sách trong thư viện.")
        result = validate_arc_execution_heuristic(chapter, char, 9)
        assert result is not None
        # severity must be either warning or critical (not ok)
        assert result.severity in ("warning", "critical")


class TestValidateAllArcs:
    def test_returns_empty_when_no_characters(self):
        from pipeline.layer1_story.arc_execution_validator import validate_all_arcs

        chapter = _make_chapter(1, "Nội dung chương 1.")
        results = validate_all_arcs(chapter, [], chapter_number=1)
        assert results == []

    def test_returns_result_per_character_with_waypoint(self):
        from pipeline.layer1_story.arc_execution_validator import validate_all_arcs

        wp = _make_waypoint(chapter_range=[1, 10])
        char = _make_character("Lan", waypoints=[wp])
        chapter = _make_chapter(5, content="Lan sợ hãi trước trận chiến.")
        results = validate_all_arcs(chapter, [char], chapter_number=5)
        assert len(results) == 1
        assert results[0].character == "Lan"

    def test_skips_character_without_waypoint_for_chapter(self):
        from pipeline.layer1_story.arc_execution_validator import validate_all_arcs

        wp = _make_waypoint(chapter_range=[1, 5])
        char = _make_character("Lan", waypoints=[wp])
        chapter = _make_chapter(10, content="Lan xuất hiện ở đây.")
        # Chapter 10 is outside waypoint range [1,5]
        results = validate_all_arcs(chapter, [char], chapter_number=10)
        assert results == []

    def test_escalates_to_llm_for_critical_ambiguous(self):
        from pipeline.layer1_story.arc_execution_validator import validate_all_arcs

        wp = _make_waypoint(stage_name="hy sinh", emotional_state="bình tĩnh",
                            chapter_range=[1, 5], progress_pct=0.9)
        char = _make_character("Lan", waypoints=[wp])
        # No matching keywords → heuristic gives critical + low confidence
        chapter = _make_chapter(1, content="Lan đang ăn cơm bình thường.")

        llm_mock = _make_llm({"found": True, "confidence": 0.8, "evidence": "Lan hy sinh"})
        results = validate_all_arcs(chapter, [char], chapter_number=1,
                                    llm=llm_mock, use_llm_for_critical=True)
        assert len(results) == 1


class TestFormatArcWarnings:
    def test_ok_results_are_filtered_out(self):
        from pipeline.layer1_story.arc_execution_validator import (
            ArcValidationResult,
            format_arc_warnings,
        )

        ok = ArcValidationResult("Lan", 1, "s", "e", True, 0.9, "ev", "ok")
        warn = ArcValidationResult("Hùng", 2, "s", "e", False, 0.0, "ev", "warning")
        warnings = format_arc_warnings([ok, warn])
        assert len(warnings) == 1
        assert "Hùng" in warnings[0]

    def test_critical_results_included(self):
        from pipeline.layer1_story.arc_execution_validator import (
            ArcValidationResult,
            format_arc_warnings,
        )

        critical = ArcValidationResult("Lan", 5, "hy sinh", "e", False, 0.1, "ev", "critical")
        warnings = format_arc_warnings([critical])
        assert len(warnings) == 1
        assert "Lan" in warnings[0]


class TestGetArcDriftSummary:
    def test_zero_results_returns_zero_drift(self):
        from pipeline.layer1_story.arc_execution_validator import get_arc_drift_summary

        summary = get_arc_drift_summary([])
        assert summary["total"] == 0
        assert summary["drift_rate"] == 0.0

    def test_all_ok_gives_zero_drift(self):
        from pipeline.layer1_story.arc_execution_validator import (
            ArcValidationResult,
            get_arc_drift_summary,
        )

        results = [ArcValidationResult("Lan", i, "s", "e", True, 0.9, "ev", "ok") for i in range(5)]
        summary = get_arc_drift_summary(results)
        assert summary["ok"] == 5
        assert summary["drift_rate"] == 0.0

    def test_mixed_results_correct_counts(self):
        from pipeline.layer1_story.arc_execution_validator import (
            ArcValidationResult,
            get_arc_drift_summary,
        )

        results = [
            ArcValidationResult("Lan", 1, "s", "e", True, 0.9, "ev", "ok"),
            ArcValidationResult("Lan", 2, "s", "e", False, 0.0, "ev", "warning"),
            ArcValidationResult("Hùng", 3, "s", "e", False, 0.0, "ev", "critical"),
        ]
        summary = get_arc_drift_summary(results)
        assert summary["total"] == 3
        assert summary["ok"] == 1
        assert summary["warning"] == 1
        assert summary["critical"] == 1
        assert summary["drift_rate"] == pytest.approx(2 / 3)

    def test_by_character_grouping(self):
        from pipeline.layer1_story.arc_execution_validator import (
            ArcValidationResult,
            get_arc_drift_summary,
        )

        results = [
            ArcValidationResult("Lan", 1, "s", "e", True, 0.9, "ev", "ok"),
            ArcValidationResult("Lan", 2, "s", "e", True, 0.8, "ev", "ok"),
            ArcValidationResult("Hùng", 1, "s", "e", False, 0.0, "ev", "warning"),
        ]
        summary = get_arc_drift_summary(results)
        assert "Lan" in summary["by_character"]
        assert "Hùng" in summary["by_character"]
        assert len(summary["by_character"]["Lan"]) == 2
