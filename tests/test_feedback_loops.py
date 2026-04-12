"""Tests for Phase 5: Feedback Loops — pacing feedback, location validation, selective critique."""

from pipeline.layer1_story.pacing_controller import (
    compare_pacing,
    compute_pacing_adjustment,
    _normalize_emotional_arc,
)
from pipeline.layer1_story.consistency_validators import validate_location_transitions
from pipeline.layer1_story.chapter_self_critique import should_critique


class TestComparePacing:
    def test_match_returns_none(self):
        assert compare_pacing("rising", "rising") is None

    def test_mismatch_returns_description(self):
        result = compare_pacing("climax", "setup")
        assert result is not None
        assert "climax" in result
        assert "setup" in result

    def test_empty_intended_returns_none(self):
        assert compare_pacing("", "rising") is None

    def test_empty_actual_returns_none(self):
        assert compare_pacing("rising", "") is None

    def test_vietnamese_arc_normalized(self):
        result = compare_pacing("climax", "bình lặng")
        assert result is not None
        assert "setup" in result


class TestComputePacingAdjustment:
    def test_no_mismatch_returns_empty(self):
        assert compute_pacing_adjustment("rising", "rising") == ""

    def test_mismatch_returns_directive(self):
        result = compute_pacing_adjustment("climax", "setup")
        assert "LEO THANG" in result
        assert "NHỊP" in result

    def test_downward_adjustment(self):
        result = compute_pacing_adjustment("cooldown", "climax")
        assert "HẠ NHIỆT" in result

    def test_caps_at_one_level(self):
        result = compute_pacing_adjustment("climax", "setup")
        assert "cooldown" in result  # setup(0) + 1 = cooldown(1)


class TestNormalizeEmotionalArc:
    def test_direct_pacing_type(self):
        assert _normalize_emotional_arc("climax") == "climax"

    def test_vietnamese_keyword(self):
        assert _normalize_emotional_arc("cao trào mạnh mẽ") == "climax"

    def test_unknown_returns_empty(self):
        assert _normalize_emotional_arc("random text") == ""

    def test_setup_aliases(self):
        assert _normalize_emotional_arc("bình lặng nhẹ nhàng") == "setup"

    def test_cooldown_aliases(self):
        assert _normalize_emotional_arc("hạ nhiệt sau trận chiến") == "cooldown"


class TestLocationTransitions:
    def test_no_prev_returns_empty(self):
        assert validate_location_transitions({}, {"A": "castle"}, "text") == []

    def test_same_location_no_warning(self):
        result = validate_location_transitions(
            {"Alice": "castle"}, {"Alice": "castle"}, "chapter text"
        )
        assert result == []

    def test_change_without_travel_warns(self):
        result = validate_location_transitions(
            {"Alice": "lâu đài"}, {"Alice": "hòn đảo xa"},
            "Alice nhìn ra biển và thấy hòn đảo xa."
        )
        assert len(result) == 1
        assert "VỊ TRÍ" in result[0]
        assert "Alice" in result[0]

    def test_change_with_travel_no_warning(self):
        result = validate_location_transitions(
            {"Alice": "lâu đài"}, {"Alice": "hòn đảo"},
            "Alice lên đường di chuyển đến hòn đảo bằng thuyền."
        )
        assert result == []

    def test_time_skip_no_warning(self):
        result = validate_location_transitions(
            {"Bob": "thành phố A"}, {"Bob": "thành phố B"},
            "Một tuần sau, Bob đã ở thành phố B."
        )
        assert result == []

    def test_unknown_char_no_warning(self):
        result = validate_location_transitions(
            {"Alice": "castle"}, {"Bob": "town"},
            "Bob appeared in town."
        )
        assert result == []


class TestSelectiveCritique:
    def test_short_story_always(self):
        assert should_critique(10, 15) is True

    def test_first_3_chapters(self):
        assert should_critique(1, 100) is True
        assert should_critique(3, 100) is True

    def test_last_3_chapters(self):
        assert should_critique(98, 100) is True
        assert should_critique(100, 100) is True

    def test_climax_pacing(self):
        assert should_critique(50, 100, pacing_type="climax") is True

    def test_twist_pacing(self):
        assert should_critique(50, 100, pacing_type="twist") is True

    def test_regular_mid_chapter_skipped(self):
        assert should_critique(50, 100, pacing_type="rising") is False

    def test_arc_boundary_critiqued(self):
        class FakeArc:
            chapter_start = 30
            chapter_end = 60
        assert should_critique(30, 100, macro_arcs=[FakeArc()]) is True
        assert should_critique(60, 100, macro_arcs=[FakeArc()]) is True

    def test_arc_adjacent_critiqued(self):
        class FakeArc:
            chapter_start = 30
            chapter_end = 60
        assert should_critique(31, 100, macro_arcs=[FakeArc()]) is True
        assert should_critique(59, 100, macro_arcs=[FakeArc()]) is True

    def test_mid_arc_not_critiqued(self):
        class FakeArc:
            chapter_start = 30
            chapter_end = 60
        assert should_critique(45, 100, macro_arcs=[FakeArc()]) is False

    def test_coverage_estimate(self):
        """Verify ~15-25% critique rate for 100-chapter story with 3 arcs."""
        class Arc:
            def __init__(self, s, e):
                self.chapter_start = s
                self.chapter_end = e
        arcs = [Arc(1, 33), Arc(34, 66), Arc(67, 100)]
        pacings = ["setup", "rising", "rising", "climax", "cooldown"] * 20
        critiqued = sum(
            1 for i in range(1, 101)
            if should_critique(i, 100, macro_arcs=arcs, pacing_type=pacings[i - 1])
        )
        assert 10 <= critiqued <= 35, f"Expected 10-35 critiqued, got {critiqued}"
