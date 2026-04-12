"""Tests for consistency_validators: timeline/location extraction, name validation, arc drift."""

from unittest.mock import MagicMock
from models.schemas import Character, CharacterState
from pipeline.layer1_story.consistency_validators import (
    extract_timeline_and_locations,
    validate_character_names,
    detect_arc_drift,
    _is_name_variant,
    _edit_distance,
)


class TestExtractTimelineAndLocations:
    def test_merges_with_previous(self):
        llm = MagicMock()
        llm.generate_json.return_value = {
            "timeline_positions": {"Minh": "buổi chiều ngày 3"},
            "character_locations": {"Minh": "rừng cấm"},
        }
        tl, loc = extract_timeline_and_locations(
            llm, "content", 2,
            {"Linh": "buổi sáng ngày 2"}, {"Linh": "làng cũ"},
        )
        assert tl == {"Linh": "buổi sáng ngày 2", "Minh": "buổi chiều ngày 3"}
        assert loc == {"Linh": "làng cũ", "Minh": "rừng cấm"}

    def test_returns_previous_on_failure(self):
        llm = MagicMock()
        llm.generate_json.side_effect = RuntimeError("API down")
        tl, loc = extract_timeline_and_locations(llm, "c", 1, {"A": "t"}, {"A": "l"})
        assert tl == {"A": "t"}
        assert loc == {"A": "l"}

    def test_empty_previous(self):
        llm = MagicMock()
        llm.generate_json.return_value = {
            "timeline_positions": {"X": "dawn"},
            "character_locations": {"X": "cave"},
        }
        tl, loc = extract_timeline_and_locations(llm, "c", 1, {}, {})
        assert tl == {"X": "dawn"}
        assert loc == {"X": "cave"}

    def test_empty_result_keeps_previous(self):
        llm = MagicMock()
        llm.generate_json.return_value = {}
        tl, loc = extract_timeline_and_locations(llm, "c", 1, {"A": "t1"}, {"A": "l1"})
        assert tl == {"A": "t1"}
        assert loc == {"A": "l1"}


class TestValidateCharacterNames:
    def _chars(self, *names):
        return [Character(name=n, role="hero", personality="p", motivation="m") for n in names]

    def test_no_warnings_for_exact_names(self):
        content = "Minh đi vào rừng. Linh chạy theo."
        assert validate_character_names(content, self._chars("Minh", "Linh")) == []

    def test_detects_variant_via_edit_distance(self):
        content = "Nguyễn Văn Mnnh đi về phía trước."
        warnings = validate_character_names(content, self._chars("Nguyễn Văn Minh"))
        assert len(warnings) >= 1
        assert "Mnnh" in warnings[0] or "Minh" in warnings[0]

    def test_ignores_unrelated_capitalized_words(self):
        content = "Trường Đại Học lớn lắm. Thành phố rộng."
        warnings = validate_character_names(content, self._chars("Minh"))
        assert warnings == []

    def test_given_name_variant_detected(self):
        content = "Minnh nói rằng hắn không thể."
        warnings = validate_character_names(content, self._chars("Nguyễn Văn Minh"))
        assert any("Minnh" in w for w in warnings)

    def test_short_name_strict_edit_distance(self):
        content = "Abc và Xyz đều có mặt."
        warnings = validate_character_names(content, self._chars("Abx"))
        assert warnings == []


class TestArcDrift:
    def _char(self, name, traj="coward to brave"):
        return Character(name=name, role="hero", personality="p",
                         motivation="m", arc_trajectory=traj)

    def _state(self, name, pos):
        return CharacterState(name=name, mood="ok", arc_position=pos, last_action="a")

    def test_no_drift_when_on_track(self):
        chars = [self._char("A")]
        states = [self._state("A", "rising")]
        warnings = detect_arc_drift(states, chars, 3, 10)
        assert warnings == []

    def test_drift_when_behind(self):
        chars = [self._char("A")]
        states = [self._state("A", "setup")]
        warnings = detect_arc_drift(states, chars, 8, 10)
        assert len(warnings) == 1
        assert "ARC DRIFT" in warnings[0]
        assert "chậm hơn" in warnings[0]

    def test_drift_when_ahead(self):
        chars = [self._char("A")]
        states = [self._state("A", "resolution")]
        warnings = detect_arc_drift(states, chars, 2, 10)
        assert len(warnings) == 1
        assert "nhanh hơn" in warnings[0]

    def test_no_drift_within_tolerance(self):
        chars = [self._char("A")]
        states = [self._state("A", "rising")]
        warnings = detect_arc_drift(states, chars, 5, 10)
        assert warnings == []

    def test_skips_characters_without_trajectory(self):
        chars = [Character(name="A", role="hero", personality="p", motivation="m")]
        states = [self._state("A", "setup")]
        warnings = detect_arc_drift(states, chars, 8, 10)
        assert warnings == []

    def test_zero_total_chapters(self):
        assert detect_arc_drift([], [], 1, 0) == []

    def test_vietnamese_aliases(self):
        chars = [self._char("A")]
        states = [self._state("A", "cao trào")]
        warnings = detect_arc_drift(states, chars, 2, 10)
        assert len(warnings) == 1
        assert "nhanh hơn" in warnings[0]


class TestHelpers:
    def test_edit_distance_identical(self):
        assert _edit_distance("minh", "minh") == 0

    def test_edit_distance_one_char(self):
        assert _edit_distance("minh", "minnh") == 1

    def test_edit_distance_two_chars(self):
        assert _edit_distance("nguyễn", "nguyên") == 1

    def test_is_name_variant_exact_lowercase_not_variant(self):
        assert _is_name_variant("Minh", "Minh") is False

    def test_is_name_variant_substring(self):
        assert _is_name_variant("A Minh", "Minh") is True

    def test_is_name_variant_edit_distance(self):
        assert _is_name_variant("Nguyễnn", "Nguyễn") is True

    def test_is_name_variant_unrelated(self):
        assert _is_name_variant("Hoàng", "Minh") is False

    def test_short_name_strict_distance(self):
        assert _is_name_variant("Abcd", "Abxy") is False
        assert _is_name_variant("Abcde", "Abcdy") is True
