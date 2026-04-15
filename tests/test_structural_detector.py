"""Unit tests for StructuralIssueDetector (Phase 5: L2→L1 rewrite trigger)."""

import pytest
from unittest.mock import MagicMock
from pipeline.layer2_enhance.structural_detector import (
    StructuralIssueDetector,
    StructuralIssue,
    StructuralIssueType,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_chapter(number: int = 1, content: str = "Nội dung chương một bình thường."):
    ch = MagicMock()
    ch.chapter_number = number
    ch.content = content
    return ch


def _make_outline(key_events=None, characters_involved=None, pacing_type="rising"):
    outline = MagicMock()
    outline.key_events = key_events or []
    outline.characters_involved = characters_involved or []
    outline.pacing_type = pacing_type
    return outline


# ---------------------------------------------------------------------------
# StructuralIssueDetector.detect — no-issue paths
# ---------------------------------------------------------------------------

class TestDetectNoIssues:
    def test_no_outline_returns_empty(self):
        detector = StructuralIssueDetector()
        ch = _make_chapter(content="something")
        result = detector.detect(ch, outline=None, arc_waypoints=None)
        assert result == []

    def test_empty_key_events_no_issue(self):
        detector = StructuralIssueDetector()
        ch = _make_chapter(content="some content here for the chapter")
        outline = _make_outline(key_events=[], characters_involved=[])
        result = detector.detect(ch, outline=outline)
        assert result == []

    def test_single_missing_key_event_below_threshold(self):
        """Only 1 missing event — below the 2-missing threshold for structural issue."""
        detector = StructuralIssueDetector()
        ch = _make_chapter(content="some unrelated content without event words")
        # Only 1 event keyword that isn't found → should NOT trigger (needs 2+)
        outline = _make_outline(key_events=["battle scene happens"])
        result = detector.detect(ch, outline=outline)
        # Should be empty since only 1 missing, not 2+
        assert all(i.issue_type != StructuralIssueType.MISSING_KEY_EVENT for i in result)

    def test_all_key_events_present(self):
        detector = StructuralIssueDetector()
        ch = _make_chapter(content="trận chiến xảy ra và nhân vật chạy thoát cảnh đó")
        outline = _make_outline(key_events=["trận chiến xảy ra", "nhân vật chạy thoát"])
        result = detector.detect(ch, outline=outline)
        assert all(i.issue_type != StructuralIssueType.MISSING_KEY_EVENT for i in result)

    def test_characters_all_present(self):
        detector = StructuralIssueDetector()
        ch = _make_chapter(content="minh và lan gặp nhau tại công viên")
        outline = _make_outline(characters_involved=["minh", "lan"])
        result = detector.detect(ch, outline=outline)
        assert all(i.issue_type != StructuralIssueType.WRONG_CHARACTERS for i in result)


# ---------------------------------------------------------------------------
# _check_key_events
# ---------------------------------------------------------------------------

class TestCheckKeyEvents:
    def test_two_missing_events_trigger_issue(self):
        detector = StructuralIssueDetector()
        ch = _make_chapter(content="không có gì liên quan")
        outline = _make_outline(key_events=[
            "trận chiến lớn diễn ra",
            "nhân vật phản bội đồng đội",
            "thành trì sụp đổ hoàn toàn",
        ])
        issues = detector._check_key_events(ch.content, outline, ch.chapter_number)
        assert len(issues) == 1
        assert issues[0].issue_type == StructuralIssueType.MISSING_KEY_EVENT
        assert issues[0].severity == 0.8

    def test_fix_hint_contains_missing_events(self):
        detector = StructuralIssueDetector()
        ch = _make_chapter(content="không có gì liên quan")
        outline = _make_outline(key_events=[
            "trận chiến lớn diễn ra",
            "nhân vật phản bội đồng đội",
        ])
        issues = detector._check_key_events(ch.content, outline, ch.chapter_number)
        assert len(issues) == 1
        assert "trận" in issues[0].fix_hint or "nhân vật" in issues[0].fix_hint

    def test_chapter_number_set_correctly(self):
        detector = StructuralIssueDetector()
        ch = _make_chapter(number=5, content="không có gì")
        outline = _make_outline(key_events=["alpha event here", "beta event here"])
        issues = detector._check_key_events(ch.content, outline, 5)
        assert all(i.chapter_number == 5 for i in issues)


# ---------------------------------------------------------------------------
# _check_characters
# ---------------------------------------------------------------------------

class TestCheckCharacters:
    def test_two_missing_characters_trigger_issue(self):
        detector = StructuralIssueDetector()
        ch = _make_chapter(content="không đề cập ai cả")
        outline = _make_outline(characters_involved=["minh", "lan", "hùng"])
        issues = detector._check_characters(ch.content, outline, ch.chapter_number)
        assert len(issues) == 1
        assert issues[0].issue_type == StructuralIssueType.WRONG_CHARACTERS
        assert issues[0].severity == 0.75

    def test_one_missing_no_issue(self):
        detector = StructuralIssueDetector()
        ch = _make_chapter(content="minh đang ngồi uống cà phê một mình")
        outline = _make_outline(characters_involved=["minh", "lan"])
        issues = detector._check_characters(ch.content, outline, ch.chapter_number)
        assert len(issues) == 0

    def test_fix_hint_lists_missing_characters(self):
        detector = StructuralIssueDetector()
        ch = _make_chapter(content="không có ai")
        outline = _make_outline(characters_involved=["minh", "lan"])
        issues = detector._check_characters(ch.content, outline, ch.chapter_number)
        assert len(issues) == 1
        assert "minh" in issues[0].fix_hint or "lan" in issues[0].fix_hint


# ---------------------------------------------------------------------------
# _check_arc_waypoints
# ---------------------------------------------------------------------------

class TestCheckArcWaypoints:
    def test_waypoint_in_range_missing_triggers_issue(self):
        detector = StructuralIssueDetector()
        ch = _make_chapter(number=5, content="bình thường không có gì đặc biệt")
        waypoints = [{"chapter_range": "3-7", "milestone": "phản bội lớn"}]
        issues = detector._check_arc_waypoints(ch.content, waypoints, 5)
        assert len(issues) == 1
        assert issues[0].issue_type == StructuralIssueType.MISSED_ARC_WAYPOINT
        assert issues[0].severity == 0.7

    def test_waypoint_out_of_range_skipped(self):
        detector = StructuralIssueDetector()
        ch = _make_chapter(number=10, content="bình thường")
        waypoints = [{"chapter_range": "3-7", "milestone": "phản bội lớn"}]
        issues = detector._check_arc_waypoints(ch.content, waypoints, 10)
        assert len(issues) == 0

    def test_waypoint_milestone_present_no_issue(self):
        detector = StructuralIssueDetector()
        ch = _make_chapter(number=5, content="đây là cảnh phản bội quan trọng trong truyện")
        waypoints = [{"chapter_range": "3-7", "milestone": "phản bội"}]
        issues = detector._check_arc_waypoints(ch.content, waypoints, 5)
        assert len(issues) == 0

    def test_waypoint_with_model_dump(self):
        detector = StructuralIssueDetector()
        ch = _make_chapter(number=5, content="nội dung không liên quan gì")
        wp = MagicMock()
        wp.model_dump.return_value = {"chapter_range": "4-6", "milestone": "phản bội lớn"}
        issues = detector._check_arc_waypoints(ch.content, [wp], 5)
        assert len(issues) == 1

    def test_max_one_waypoint_issue_per_chapter(self):
        """Only first matching waypoint triggers issue, then break."""
        detector = StructuralIssueDetector()
        ch = _make_chapter(number=5, content="không có gì")
        waypoints = [
            {"chapter_range": "3-7", "milestone": "phản bội lớn"},
            {"chapter_range": "4-6", "milestone": "đấu tranh ác liệt"},
        ]
        issues = detector._check_arc_waypoints(ch.content, waypoints, 5)
        assert len(issues) == 1


# ---------------------------------------------------------------------------
# _check_pacing
# ---------------------------------------------------------------------------

class TestCheckPacing:
    def test_climax_without_action_triggers_issue(self):
        detector = StructuralIssueDetector()
        ch = _make_chapter(content="một ngày bình thường trôi qua rất nhẹ nhàng")
        outline = _make_outline(pacing_type="climax")
        issues = detector._check_pacing(ch.content, outline, ch.chapter_number)
        assert len(issues) == 1
        assert issues[0].issue_type == StructuralIssueType.PACING_VIOLATION
        assert issues[0].severity == 0.7

    def test_climax_viet_without_action_triggers_issue(self):
        detector = StructuralIssueDetector()
        ch = _make_chapter(content="một ngày bình thường trôi qua")
        outline = _make_outline(pacing_type="cao trào")
        issues = detector._check_pacing(ch.content, outline, ch.chapter_number)
        assert len(issues) == 1

    def test_climax_with_action_no_issue(self):
        detector = StructuralIssueDetector()
        ch = _make_chapter(content="họ đánh nhau dữ dội trên đỉnh núi")
        outline = _make_outline(pacing_type="climax")
        issues = detector._check_pacing(ch.content, outline, ch.chapter_number)
        assert len(issues) == 0

    def test_non_climax_pacing_no_issue(self):
        detector = StructuralIssueDetector()
        ch = _make_chapter(content="không có hành động gì")
        outline = _make_outline(pacing_type="setup")
        issues = detector._check_pacing(ch.content, outline, ch.chapter_number)
        assert len(issues) == 0

    def test_empty_pacing_no_issue(self):
        detector = StructuralIssueDetector()
        ch = _make_chapter(content="không có gì")
        outline = _make_outline(pacing_type="")
        issues = detector._check_pacing(ch.content, outline, ch.chapter_number)
        assert len(issues) == 0


# ---------------------------------------------------------------------------
# Severity threshold filtering
# ---------------------------------------------------------------------------

class TestSeverityThreshold:
    def test_custom_threshold_filters_lower_severity(self):
        """With threshold=0.9, severity=0.8 issue is excluded."""
        detector = StructuralIssueDetector(severity_threshold=0.9)
        ch = _make_chapter(content="không có gì liên quan")
        outline = _make_outline(key_events=[
            "trận chiến lớn diễn ra",
            "nhân vật phản bội đồng đội",
        ])
        result = detector.detect(ch, outline=outline)
        # MISSING_KEY_EVENT has severity 0.8, below 0.9 threshold
        assert all(i.issue_type != StructuralIssueType.MISSING_KEY_EVENT for i in result)

    def test_default_threshold_includes_0_8_severity(self):
        detector = StructuralIssueDetector()  # default 0.7
        ch = _make_chapter(content="không có gì liên quan")
        outline = _make_outline(key_events=[
            "trận chiến lớn diễn ra",
            "nhân vật phản bội đồng đội",
        ])
        result = detector.detect(ch, outline=outline)
        assert any(i.issue_type == StructuralIssueType.MISSING_KEY_EVENT for i in result)


# ---------------------------------------------------------------------------
# detect() integration
# ---------------------------------------------------------------------------

class TestDetectIntegration:
    def test_detect_returns_multiple_issue_types(self):
        detector = StructuralIssueDetector()
        # Chapter with multiple structural problems
        ch = _make_chapter(number=3, content="không có gì đặc biệt")
        outline = _make_outline(
            key_events=["trận chiến lớn diễn ra", "nhân vật phản bội đồng đội"],
            characters_involved=["minh", "lan", "hùng"],
            pacing_type="climax",
        )
        result = detector.detect(ch, outline=outline)
        issue_types = {i.issue_type for i in result}
        assert StructuralIssueType.MISSING_KEY_EVENT in issue_types
        assert StructuralIssueType.WRONG_CHARACTERS in issue_types
        assert StructuralIssueType.PACING_VIOLATION in issue_types

    def test_detect_with_arc_waypoints(self):
        detector = StructuralIssueDetector()
        ch = _make_chapter(number=5, content="ngày thường không có gì")
        outline = _make_outline()
        waypoints = [{"chapter_range": "4-6", "milestone": "phản bội lớn xảy ra"}]
        result = detector.detect(ch, outline=outline, arc_waypoints=waypoints)
        assert any(i.issue_type == StructuralIssueType.MISSED_ARC_WAYPOINT for i in result)

    def test_detect_none_content_safe(self):
        """Chapter with None content doesn't raise."""
        detector = StructuralIssueDetector()
        ch = MagicMock()
        ch.chapter_number = 1
        ch.content = None
        outline = _make_outline(key_events=["battle", "fight"])
        result = detector.detect(ch, outline=outline)
        # Should not raise, returns empty or issue list
        assert isinstance(result, list)
