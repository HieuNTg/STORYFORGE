"""Unit tests for lane_classifier — keyword-based dramatic/craft lane splitter."""

import pytest

from pipeline.layer2_enhance.lane_classifier import (
    classify_lane,
    is_craft_drift,
)


class TestClassifyLane:
    @pytest.mark.parametrize("text", [
        "Tăng xung đột giữa hai nhân vật chính",
        "Cần thêm plot twist ở chương cuối",
        "Bí mật của antagonist nên được tiết lộ sớm hơn",
        "Foreshadow cái chết của nhân vật phụ",
        "Raise the stakes for the protagonist",
        "Strengthen the character arc and motivation",
        "Đẩy cao trào và căng thẳng ở cảnh cuối",
    ])
    def test_dramatic_signals(self, text):
        assert classify_lane(text) == "dramatic"

    @pytest.mark.parametrize("text", [
        "Văn phong quá lê thê, cần ngắn gọn hơn",
        "Cải thiện grammar và sentence structure",
        "Show, don't tell ở đoạn miêu tả này",
        "POV shift giữa chừng làm rối người đọc",
        "Tone consistency của narrator chưa đều",
        "Awkward phrasing in chapter 3",
        "Dùng metaphor thay vì miêu tả trực tiếp",
    ])
    def test_craft_signals(self, text):
        assert classify_lane(text) == "craft"

    @pytest.mark.parametrize("text", [
        "",
        "Chapter is okay overall",
        "Tổng thể ổn",
        "Cần xem lại",
    ])
    def test_ambiguous_signals(self, text):
        assert classify_lane(text) == "ambiguous"

    def test_mixed_signals_are_ambiguous(self):
        # Has both craft (văn phong) and dramatic (xung đột) markers
        assert classify_lane("Văn phong rõ hơn để khắc họa xung đột") == "ambiguous"

    def test_empty_and_whitespace(self):
        assert classify_lane("") == "ambiguous"
        assert classify_lane("   ") == "ambiguous"


class TestIsCraftDrift:
    def test_clear_craft_drift_returns_true(self):
        assert is_craft_drift("Cần sửa văn phong và grammar") is True

    def test_dramatic_does_not_drift(self):
        assert is_craft_drift("Tăng xung đột và stakes") is False

    def test_ambiguous_does_not_drift(self):
        assert is_craft_drift("Văn phong rõ hơn để khắc họa xung đột") is False

    def test_empty_does_not_drift(self):
        assert is_craft_drift("") is False
