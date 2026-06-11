"""Unit tests for services/naming_conventions.py (previously untested).

Locks in the product rule: Vietnamese names by default, Chinese-style
names only for tiên hiệp / wuxia-family genres, Western for fantasy/sci-fi.
"""

from __future__ import annotations

import pytest

from services.naming_conventions import get_naming_instruction, get_naming_style


class TestGetNamingStyle:
    @pytest.mark.parametrize(
        "genre",
        [
            "Tiên Hiệp",
            "kiếm hiệp",
            "Wuxia",
            "xianxia",
            "tu tiên",
            "huyền huyễn",
            "cung đấu",
        ],
    )
    def test_chinese_style_genres(self, genre):
        assert get_naming_style(genre) == "chinese"

    @pytest.mark.parametrize(
        "genre",
        ["High Fantasy", "epic fantasy", "Sci-Fi", "khoa học viễn tưởng"],
    )
    def test_western_style_genres(self, genre):
        assert get_naming_style(genre) == "western"

    @pytest.mark.parametrize(
        "genre",
        ["Ngôn tình", "Trinh thám", "Kinh dị", "Đời thường", ""],
    )
    def test_vietnamese_is_the_default(self, genre):
        assert get_naming_style(genre) == "vietnamese"

    def test_substring_match_inside_longer_genre(self):
        assert get_naming_style("Truyện tiên hiệp hài hước") == "chinese"

    def test_case_and_whitespace_insensitive(self):
        assert get_naming_style("  TIÊN HIỆP  ") == "chinese"


class TestGetNamingInstruction:
    def test_chinese_instruction_mentions_chinese_style(self):
        text = get_naming_instruction("tiên hiệp")
        assert "Trung Quốc" in text
        assert "tông môn" in text or "phái" in text

    def test_western_instruction_mentions_western_style(self):
        text = get_naming_instruction("high fantasy")
        assert "phương Tây" in text
        assert "Western" in text

    def test_default_instruction_uses_vietnamese_names(self):
        text = get_naming_instruction("ngôn tình")
        assert "Việt Nam" in text
        assert "Nguyễn" in text
