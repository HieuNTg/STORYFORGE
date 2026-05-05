"""Behavior tests for three L1 scene/theme modules.

Covers:
- pipeline.layer1_story.scene_decomposer
- pipeline.layer1_story.scene_beat_generator
- pipeline.layer1_story.theme_premise_generator
"""

import pytest
from unittest.mock import MagicMock

from models.schemas import Character, WorldSetting, ChapterOutline
from pipeline.layer1_story.scene_decomposer import (
    decompose_chapter_scenes,
    format_scenes_for_prompt,
    should_decompose,
    CLIMAX_PACING_TYPES,
)
from pipeline.layer1_story.scene_beat_generator import (
    SceneBeat,
    generate_scene_beats,
    format_beats_for_prompt,
)
from pipeline.layer1_story.theme_premise_generator import (
    generate_premise,
    format_premise_for_prompt,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_llm(return_value: dict) -> MagicMock:
    llm = MagicMock()
    llm.generate_json.return_value = return_value
    return llm


def _make_outline(
    chapter_number: int = 1,
    title: str = "Cuộc gặp gỡ định mệnh",
    summary: str = "Hai nhân vật đối đầu lần đầu.",
    key_events: list | None = None,
    pacing_type: str = "rising",
    emotional_arc: str = "căng thẳng → bất ngờ",
) -> ChapterOutline:
    return ChapterOutline(
        chapter_number=chapter_number,
        title=title,
        summary=summary,
        key_events=key_events or ["Đối đầu", "Lời đe dọa"],
        characters_involved=["Minh", "Hoa"],
        emotional_arc=emotional_arc,
        pacing_type=pacing_type,
    )


def _make_characters() -> list[Character]:
    return [
        Character(name="Nguyễn Minh", role="chính", personality="Cứng rắn, quyết đoán"),
        Character(name="Trần Hoa", role="phụ", personality="Thông minh, bí ẩn"),
    ]


def _make_world() -> WorldSetting:
    return WorldSetting(
        name="Vương quốc Đông Sơn",
        description="Vương quốc phong kiến thời trung đại.",
        locations=["Cung điện", "Chợ thành phố"],
        era="Thế kỷ 15",
    )


_VALID_SCENES = {
    "scenes": [
        {
            "scene_number": 1,
            "location": "Chợ thành phố",
            "pov_character": "Nguyễn Minh",
            "characters_present": ["Nguyễn Minh", "Trần Hoa"],
            "goal": "Minh tìm kiếm manh mối",
            "conflict": "Hoa chặn đường anh",
            "outcome": "phức tạp hóa",
            "sensory_focus": ["thị giác", "thính giác"],
            "emotional_beat": "căng thẳng",
        },
        {
            "scene_number": 2,
            "location": "Ngõ tối",
            "pov_character": "Nguyễn Minh",
            "characters_present": ["Nguyễn Minh"],
            "goal": "Chạy trốn",
            "conflict": "Bị truy đuổi",
            "outcome": "thất bại",
            "sensory_focus": ["xúc giác"],
            "emotional_beat": "sợ hãi",
        },
    ]
}

_VALID_PREMISE = {
    "premise_statement": "Câu chuyện về chiến tranh, nhưng thực chất nói về sự hy sinh",
    "thematic_core": "Tình người vượt lên trên mọi xung đột.",
    "thematic_keywords": ["hy sinh", "chiến tranh", "tình người"],
    "moral_dilemma": "Nhân vật phải chọn giữa danh dự và gia đình",
}


# ===========================================================================
# scene_decomposer
# ===========================================================================


class TestShouldDecompose:
    def test_always_true_for_normal(self):
        assert should_decompose(1, "rising") is True

    def test_climax_pacing_returns_true(self):
        for pacing in CLIMAX_PACING_TYPES:
            assert should_decompose(5, pacing) is True

    def test_empty_pacing_returns_true(self):
        assert should_decompose(3, "") is True


class TestDecomposeChapterScenes:
    def test_happy_path_returns_scenes(self):
        llm = _make_llm(_VALID_SCENES)
        scenes = decompose_chapter_scenes(
            llm,
            _make_outline(),
            _make_characters(),
            _make_world(),
            "tiên hiệp",
        )
        assert len(scenes) == 2
        assert scenes[0]["scene_number"] == 1
        assert scenes[0]["location"] == "Chợ thành phố"
        assert "Nguyễn Minh" in scenes[0]["characters_present"]

    def test_clamps_to_five_scenes(self):
        six_scenes = {"scenes": [{"scene_number": i} for i in range(1, 7)]}
        llm = _make_llm(six_scenes)
        scenes = decompose_chapter_scenes(
            llm, _make_outline(), _make_characters(), _make_world(), "tiên hiệp"
        )
        assert len(scenes) == 5

    def test_llm_failure_returns_empty_list(self):
        llm = MagicMock()
        llm.generate_json.side_effect = RuntimeError("network error")
        scenes = decompose_chapter_scenes(
            llm, _make_outline(), _make_characters(), _make_world(), "lãng mạn"
        )
        assert scenes == []

    def test_llm_returns_empty_dict_gives_empty_list(self):
        llm = _make_llm({})
        scenes = decompose_chapter_scenes(
            llm, _make_outline(), _make_characters(), _make_world(), "lãng mạn"
        )
        assert scenes == []

    def test_scenes_key_not_list_returns_empty(self):
        llm = _make_llm({"scenes": "not a list"})
        scenes = decompose_chapter_scenes(
            llm, _make_outline(), _make_characters(), _make_world(), "kinh dị"
        )
        assert scenes == []

    def test_model_param_passed_to_llm(self):
        llm = _make_llm(_VALID_SCENES)
        decompose_chapter_scenes(
            llm, _make_outline(), _make_characters(), _make_world(), "võ hiệp", model="gpt-4o"
        )
        _, kwargs = llm.generate_json.call_args
        assert kwargs.get("model") == "gpt-4o"

    def test_outline_with_no_key_events(self):
        outline = _make_outline(key_events=[])
        llm = _make_llm(_VALID_SCENES)
        scenes = decompose_chapter_scenes(llm, outline, _make_characters(), _make_world(), "lãng mạn")
        assert len(scenes) == 2

    def test_world_without_locations_or_era(self):
        world = WorldSetting(name="Thế giới giả tưởng", description="Mô tả cơ bản.")
        llm = _make_llm(_VALID_SCENES)
        scenes = decompose_chapter_scenes(
            llm, _make_outline(), _make_characters(), world, "huyền huyễn"
        )
        assert isinstance(scenes, list)

    def test_vietnamese_content_preserved(self):
        llm = _make_llm(_VALID_SCENES)
        decompose_chapter_scenes(
            llm, _make_outline(), _make_characters(), _make_world(), "tiên hiệp"
        )
        call_kwargs = llm.generate_json.call_args[1]
        assert "tiếng Việt" in call_kwargs["system_prompt"]
        assert "Chợ thành phố" in str(call_kwargs.get("user_prompt", ""))


class TestFormatScenesForPrompt:
    def test_empty_scenes_returns_empty_string(self):
        assert format_scenes_for_prompt([]) == ""

    def test_happy_path_contains_key_fields(self):
        output = format_scenes_for_prompt(_VALID_SCENES["scenes"])
        assert "CẤU TRÚC CẢNH" in output
        assert "Chợ thành phố" in output
        assert "Nguyễn Minh" in output
        assert "Minh tìm kiếm manh mối" in output
        assert "phức tạp hóa" in output

    def test_scene_without_optional_fields(self):
        minimal = [{"scene_number": 1, "location": "Hang động", "pov_character": "Minh", "goal": "Thoát ra"}]
        output = format_scenes_for_prompt(minimal)
        assert "Hang động" in output
        assert "Thoát ra" in output

    def test_sensory_focus_and_emotional_beat_included(self):
        output = format_scenes_for_prompt(_VALID_SCENES["scenes"])
        assert "thị giác" in output
        assert "căng thẳng" in output


# ===========================================================================
# scene_beat_generator
# ===========================================================================

_VALID_BEATS_RESPONSE = {
    "scenes": [
        {
            "scene_num": 1,
            "characters": ["Nguyễn Minh", "Trần Hoa"],
            "setting": "Chợ sáng sớm",
            "action": "Hai người chạm mặt nhau",
            "tension_level": 0.6,
            "pov": "Nguyễn Minh",
            "emotional_goal": "Bất ngờ và cảnh giác",
        },
        {
            "scene_num": 2,
            "characters": ["Nguyễn Minh"],
            "setting": "Ngõ hẻm",
            "action": "Minh theo dõi bóng người",
            "tension_level": 0.8,
            "pov": "Nguyễn Minh",
            "emotional_goal": "Hồi hộp",
        },
    ]
}


class TestGenerateSceneBeats:
    def test_happy_path_returns_scene_beats(self):
        llm = _make_llm(_VALID_BEATS_RESPONSE)
        beats = generate_scene_beats(
            llm, _make_outline(), _make_characters(), _make_world(), "tiên hiệp"
        )
        assert len(beats) == 2
        assert all(isinstance(b, SceneBeat) for b in beats)
        assert beats[0].scene_num == 1
        assert beats[0].tension_level == pytest.approx(0.6)
        assert beats[1].tension_level == pytest.approx(0.8)

    def test_llm_failure_returns_empty_list(self):
        llm = MagicMock()
        llm.generate_json.side_effect = Exception("timeout")
        beats = generate_scene_beats(
            llm, _make_outline(), _make_characters(), _make_world(), "lãng mạn"
        )
        assert beats == []

    def test_empty_scenes_in_response_returns_empty(self):
        llm = _make_llm({"scenes": []})
        beats = generate_scene_beats(
            llm, _make_outline(), _make_characters(), _make_world(), "kinh dị"
        )
        assert beats == []

    def test_missing_scenes_key_returns_empty(self):
        llm = _make_llm({})
        beats = generate_scene_beats(
            llm, _make_outline(), _make_characters(), _make_world(), "kinh dị"
        )
        assert beats == []

    def test_legacy_field_mapping_characters_present(self):
        legacy_response = {
            "scenes": [
                {
                    "scene_num": 1,
                    "characters_present": ["Minh", "Hoa"],
                    "setting": "Rừng",
                    "action": "Chạy trốn",
                    "tension_level": 0.7,
                    "pov": "Minh",
                    "emotional_goal": "Sợ hãi",
                }
            ]
        }
        llm = _make_llm(legacy_response)
        beats = generate_scene_beats(
            llm, _make_outline(), _make_characters(), _make_world(), "phiêu lưu"
        )
        assert len(beats) == 1
        assert beats[0].characters == ["Minh", "Hoa"]

    def test_legacy_field_mapping_emotional_beat(self):
        legacy_response = {
            "scenes": [
                {
                    "scene_num": 1,
                    "characters": ["Minh"],
                    "setting": "Rừng",
                    "action": "Ngồi suy nghĩ",
                    "tension_level": 0.3,
                    "pov": "Minh",
                    "emotional_beat": "Buồn bã",
                }
            ]
        }
        llm = _make_llm(legacy_response)
        beats = generate_scene_beats(
            llm, _make_outline(), _make_characters(), _make_world(), "lãng mạn"
        )
        assert len(beats) == 1
        assert beats[0].emotional_goal == "Buồn bã"

    def test_invalid_scene_in_list_is_skipped(self):
        mixed = {
            "scenes": [
                {"scene_num": 1, "characters": ["Minh"], "setting": "A", "action": "B", "tension_level": 0.5, "pov": "Minh", "emotional_goal": "OK"},
                {"scene_num": "not_an_int_but_valid_coercion", "tension_level": 9999},  # tension out of range — skipped
            ]
        }
        llm = _make_llm(mixed)
        beats = generate_scene_beats(
            llm, _make_outline(), _make_characters(), _make_world(), "kinh dị"
        )
        # First beat valid, second skipped due to out-of-range tension
        assert len(beats) == 1
        assert beats[0].scene_num == 1

    def test_pacing_type_override(self):
        llm = _make_llm(_VALID_BEATS_RESPONSE)
        generate_scene_beats(
            llm, _make_outline(pacing_type="climax"),
            _make_characters(), _make_world(), "tiên hiệp",
            pacing_type="",
        )
        call_kwargs = llm.generate_json.call_args[1]
        # Empty string override: "Loại chương:" block should NOT appear
        assert "Loại chương:" not in call_kwargs["user_prompt"]

    def test_pacing_type_included_in_prompt_when_set(self):
        llm = _make_llm(_VALID_BEATS_RESPONSE)
        generate_scene_beats(
            llm, _make_outline(pacing_type="climax"),
            _make_characters(), _make_world(), "tiên hiệp",
        )
        call_kwargs = llm.generate_json.call_args[1]
        assert "climax" in call_kwargs["user_prompt"]

    def test_characters_truncated_to_five(self):
        many_chars = [
            Character(name=f"NV{i}", role="phụ", personality="Bình thường")
            for i in range(8)
        ]
        llm = _make_llm(_VALID_BEATS_RESPONSE)
        generate_scene_beats(
            llm, _make_outline(), many_chars, _make_world(), "kinh dị"
        )
        call_kwargs = llm.generate_json.call_args[1]
        # Only first 5 names in prompt
        for i in range(5):
            assert f"NV{i}" in call_kwargs["user_prompt"]
        assert "NV5" not in call_kwargs["user_prompt"]


class TestSceneBeatModel:
    def test_defaults(self):
        beat = SceneBeat(scene_num=1)
        assert beat.characters == []
        assert beat.setting == ""
        assert beat.tension_level == pytest.approx(0.5)

    def test_tension_clamped_invalid_raises(self):
        with pytest.raises(Exception):
            SceneBeat(scene_num=1, tension_level=1.5)


class TestFormatBeatsForPrompt:
    def test_empty_returns_empty_string(self):
        assert format_beats_for_prompt([]) == ""

    def test_happy_path_contains_key_info(self):
        beats = [
            SceneBeat(
                scene_num=1,
                characters=["Minh", "Hoa"],
                setting="Chợ",
                action="Chạm mặt",
                tension_level=0.7,
                pov="Minh",
                emotional_goal="Căng thẳng",
            )
        ]
        output = format_beats_for_prompt(beats)
        assert "CẤU TRÚC CẢNH" in output
        assert "Chợ" in output
        assert "70%" in output
        assert "Minh" in output
        assert "Căng thẳng" in output
        assert "Viết đúng theo cấu trúc" in output

    def test_no_pov_omits_pov_tag(self):
        beats = [SceneBeat(scene_num=1, setting="Rừng", action="Đi bộ", tension_level=0.3)]
        output = format_beats_for_prompt(beats)
        assert "POV" not in output


# ===========================================================================
# theme_premise_generator
# ===========================================================================


class TestGeneratePremise:
    def test_happy_path_returns_all_keys(self):
        llm = _make_llm(_VALID_PREMISE)
        result = generate_premise(llm, "Ngọn lửa chiến tranh", "lịch sử", "Câu chuyện về chiến tranh Việt Nam")
        assert result["premise_statement"] == _VALID_PREMISE["premise_statement"]
        assert result["thematic_core"] == _VALID_PREMISE["thematic_core"]
        assert isinstance(result["thematic_keywords"], list)
        assert len(result["thematic_keywords"]) == 3
        assert result["moral_dilemma"] == _VALID_PREMISE["moral_dilemma"]

    def test_llm_failure_returns_empty_dict(self):
        llm = MagicMock()
        llm.generate_json.side_effect = RuntimeError("API down")
        result = generate_premise(llm, "Tiêu đề", "tiên hiệp", "Ý tưởng")
        assert result == {}

    def test_missing_required_key_returns_empty_dict(self):
        incomplete = {k: v for k, v in _VALID_PREMISE.items() if k != "moral_dilemma"}
        llm = _make_llm(incomplete)
        result = generate_premise(llm, "Test", "lãng mạn", "Ý tưởng")
        assert result == {}

    def test_non_dict_response_returns_empty_dict(self):
        llm = _make_llm([])  # type: ignore[arg-type] — simulates broken LLM returning list
        llm.generate_json.return_value = []
        result = generate_premise(llm, "Test", "kinh dị", "Ý tưởng")
        assert result == {}

    def test_keywords_string_coerced_to_list(self):
        with_str_keywords = {**_VALID_PREMISE, "thematic_keywords": "hy sinh, tình yêu"}
        llm = _make_llm(with_str_keywords)
        result = generate_premise(llm, "Test", "lãng mạn", "Idea")
        assert isinstance(result["thematic_keywords"], list)

    def test_user_input_wrapped_in_tags(self):
        llm = _make_llm(_VALID_PREMISE)
        generate_premise(llm, "Tiêu đề nguy hiểm", "tiên hiệp", "Ý tưởng thú vị")
        call_kwargs = llm.generate_json.call_args[1]
        user_prompt = call_kwargs["user_prompt"]
        assert "<user_input>" in user_prompt
        assert "</user_input>" in user_prompt
        assert "Tiêu đề nguy hiểm" in user_prompt
        assert "Ý tưởng thú vị" in user_prompt

    def test_vietnamese_system_prompt(self):
        llm = _make_llm(_VALID_PREMISE)
        generate_premise(llm, "T", "g", "i")
        call_kwargs = llm.generate_json.call_args[1]
        assert "tiếng Việt" in call_kwargs["system_prompt"]

    def test_only_allowed_keys_returned(self):
        extra = {**_VALID_PREMISE, "extra_field": "should_not_appear"}
        llm = _make_llm(extra)
        result = generate_premise(llm, "T", "g", "i")
        assert "extra_field" not in result
        assert set(result.keys()) == {"premise_statement", "thematic_core", "thematic_keywords", "moral_dilemma"}


class TestFormatPremiseForPrompt:
    def test_empty_dict_returns_empty_string(self):
        assert format_premise_for_prompt({}) == ""

    def test_happy_path_contains_all_sections(self):
        output = format_premise_for_prompt(_VALID_PREMISE)
        assert "CHỦ ĐỀ CỐT LÕI" in output
        assert "chiến tranh" in output
        assert "hy sinh" in output
        assert "Tình người" in output
        assert "danh dự" in output

    def test_missing_all_content_returns_empty(self):
        empty_premise = {"premise_statement": "", "thematic_core": "", "thematic_keywords": [], "moral_dilemma": ""}
        assert format_premise_for_prompt(empty_premise) == ""

    def test_keywords_list_joined_with_comma(self):
        output = format_premise_for_prompt(_VALID_PREMISE)
        assert "hy sinh, chiến tranh, tình người" in output

    def test_keywords_as_string_still_renders(self):
        premise = {**_VALID_PREMISE, "thematic_keywords": "hy sinh"}
        output = format_premise_for_prompt(premise)
        assert "hy sinh" in output
