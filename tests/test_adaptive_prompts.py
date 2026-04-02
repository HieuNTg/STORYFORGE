"""Tests for services/adaptive_prompts.py."""

from services.adaptive_prompts import (
    GENRE_EMPHASIS,
    SCORE_BOOSTERS,
    WEAK_SCORE_THRESHOLD,
    get_genre_emphasis,
    get_score_boosters,
    build_adaptive_write_prompt,
    build_adaptive_enhance_prompt,
)


# ---------------------------------------------------------------------------
# get_genre_emphasis
# ---------------------------------------------------------------------------

class TestGetGenreEmphasis:
    def test_exact_match_all_genres(self):
        for genre in GENRE_EMPHASIS:
            result = get_genre_emphasis(genre)
            assert result == GENRE_EMPHASIS[genre], f"Exact match failed for {genre}"

    def test_partial_match_substring(self):
        # "Tiên Hiệp" should match when genre contains "Tiên Hiệp"
        result = get_genre_emphasis("Truyện Tiên Hiệp hay")
        assert result == GENRE_EMPHASIS["Tiên Hiệp"]

    def test_partial_match_genre_in_key(self):
        # Short genre name contained in a full key
        result = get_genre_emphasis("Kiếm")
        # "Kiếm" is substring of "Kiếm Hiệp"
        assert result == GENRE_EMPHASIS["Kiếm Hiệp"]

    def test_case_insensitive_partial(self):
        result = get_genre_emphasis("tiên hiệp")
        assert result == GENRE_EMPHASIS["Tiên Hiệp"]

    def test_unknown_genre_returns_empty(self):
        assert get_genre_emphasis("Thể loại lạ không tồn tại xyz") == ""

    def test_empty_genre_returns_empty(self):
        assert get_genre_emphasis("") == ""

    def test_returns_string(self):
        for genre in GENRE_EMPHASIS:
            assert isinstance(get_genre_emphasis(genre), str)


# ---------------------------------------------------------------------------
# get_score_boosters
# ---------------------------------------------------------------------------

class TestGetScoreBoosters:
    def test_none_returns_empty(self):
        assert get_score_boosters(None) == ""

    def test_empty_dict_returns_empty(self):
        assert get_score_boosters({}) == ""

    def test_all_high_scores_no_boosters(self):
        scores = {
            "coherence": 4.0,
            "character_consistency": 5.0,
            "drama": 3.5,
            "writing_quality": 4.5,
        }
        assert get_score_boosters(scores) == ""

    def test_all_scores_at_threshold_not_boosted(self):
        # Exactly at threshold should NOT trigger (strict less-than)
        scores = {k: WEAK_SCORE_THRESHOLD for k in SCORE_BOOSTERS}
        assert get_score_boosters(scores) == ""

    def test_single_weak_dimension(self):
        scores = {"coherence": 2.5, "character_consistency": 4.0, "drama": 4.0, "writing_quality": 4.0}
        result = get_score_boosters(scores)
        assert SCORE_BOOSTERS["coherence"] in result
        assert SCORE_BOOSTERS["character_consistency"] not in result

    def test_multiple_weak_dimensions(self):
        scores = {"coherence": 1.0, "character_consistency": 1.0, "drama": 5.0, "writing_quality": 5.0}
        result = get_score_boosters(scores)
        assert SCORE_BOOSTERS["coherence"] in result
        assert SCORE_BOOSTERS["character_consistency"] in result
        assert SCORE_BOOSTERS["drama"] not in result

    def test_all_weak_dimensions(self):
        scores = {k: 1.0 for k in SCORE_BOOSTERS}
        result = get_score_boosters(scores)
        for booster in SCORE_BOOSTERS.values():
            assert booster in result

    def test_missing_dimension_defaults_to_high(self):
        # Missing dimension defaults to 5.0, so no booster
        scores = {"coherence": 2.0}
        result = get_score_boosters(scores)
        assert SCORE_BOOSTERS["coherence"] in result
        assert SCORE_BOOSTERS["drama"] not in result

    def test_invalid_score_skipped(self):
        scores = {"coherence": "invalid", "drama": 1.0}
        result = get_score_boosters(scores)
        assert SCORE_BOOSTERS["coherence"] not in result
        assert SCORE_BOOSTERS["drama"] in result

    def test_none_score_skipped(self):
        scores = {"coherence": None, "drama": 1.0}
        result = get_score_boosters(scores)
        assert SCORE_BOOSTERS["coherence"] not in result

    def test_border_below_threshold(self):
        scores = {"drama": WEAK_SCORE_THRESHOLD - 0.01}
        result = get_score_boosters(scores)
        assert SCORE_BOOSTERS["drama"] in result


# ---------------------------------------------------------------------------
# build_adaptive_write_prompt
# ---------------------------------------------------------------------------

class TestBuildAdaptiveWritePrompt:
    BASE_WITH_YEU_CAU = (
        "Bạn là tiểu thuyết gia.\n\n"
        "YÊU CẦU:\n- Viết 2000 từ\n\nBắt đầu viết chương:"
    )
    BASE_WITHOUT_YEU_CAU = (
        "Bạn là tiểu thuyết gia.\n\nBắt đầu viết chương:"
    )
    BASE_BARE = "Bạn là tiểu thuyết gia."

    def test_no_genre_no_scores_returns_original(self):
        result = build_adaptive_write_prompt(self.BASE_WITH_YEU_CAU, "")
        assert result == self.BASE_WITH_YEU_CAU

    def test_unknown_genre_no_scores_returns_original(self):
        result = build_adaptive_write_prompt(self.BASE_WITH_YEU_CAU, "Thể loại lạ xyz")
        assert result == self.BASE_WITH_YEU_CAU

    def test_genre_inserted_before_yeu_cau(self):
        result = build_adaptive_write_prompt(self.BASE_WITH_YEU_CAU, "Tiên Hiệp")
        assert "HƯỚNG DẪN THỂ LOẠI TIÊN HIỆP:" in result
        assert GENRE_EMPHASIS["Tiên Hiệp"] in result
        # Must appear before YÊU CẦU
        idx_genre = result.index("HƯỚNG DẪN THỂ LOẠI TIÊN HIỆP:")
        idx_yc = result.index("YÊU CẦU:")
        assert idx_genre < idx_yc

    def test_score_booster_inserted_before_yeu_cau(self):
        scores = {"drama": 1.0}
        result = build_adaptive_write_prompt(self.BASE_WITH_YEU_CAU, "", scores)
        assert SCORE_BOOSTERS["drama"] in result
        idx_booster = result.index(SCORE_BOOSTERS["drama"])
        idx_yc = result.index("YÊU CẦU:")
        assert idx_booster < idx_yc

    def test_both_genre_and_scores(self):
        scores = {"coherence": 1.0, "drama": 1.0}
        result = build_adaptive_write_prompt(self.BASE_WITH_YEU_CAU, "Ngôn Tình", scores)
        assert "HƯỚNG DẪN THỂ LOẠI NGÔN TÌNH:" in result
        assert SCORE_BOOSTERS["coherence"] in result
        assert SCORE_BOOSTERS["drama"] in result
        assert "YÊU CẦU:" in result

    def test_original_content_preserved(self):
        result = build_adaptive_write_prompt(self.BASE_WITH_YEU_CAU, "Trinh Thám")
        assert "Bạn là tiểu thuyết gia." in result
        assert "YÊU CẦU:" in result
        assert "Viết 2000 từ" in result
        assert "Bắt đầu viết chương:" in result

    def test_fallback_to_bat_dau_viet(self):
        result = build_adaptive_write_prompt(self.BASE_WITHOUT_YEU_CAU, "Hệ Thống")
        assert "HƯỚNG DẪN THỂ LOẠI HỆ THỐNG:" in result
        # Still contains the original marker
        assert "Bắt đầu viết chương:" in result

    def test_last_resort_append(self):
        result = build_adaptive_write_prompt(self.BASE_BARE, "Khoa Huyễn")
        assert "HƯỚNG DẪN THỂ LOẠI KHOA HUYỄN:" in result
        assert "Bạn là tiểu thuyết gia." in result

    def test_all_known_genres_produce_nonempty_result(self):
        for genre in GENRE_EMPHASIS:
            result = build_adaptive_write_prompt(self.BASE_WITH_YEU_CAU, genre)
            assert len(result) > len(self.BASE_WITH_YEU_CAU), f"No enhancement for {genre}"

    def test_yeu_cau_replaced_only_once(self):
        # Ensure we don't double-insert if "YÊU CẦU:" appears once
        result = build_adaptive_write_prompt(self.BASE_WITH_YEU_CAU, "Cung Đấu")
        assert result.count("YÊU CẦU:") == 1


# ---------------------------------------------------------------------------
# build_adaptive_enhance_prompt
# ---------------------------------------------------------------------------

class TestBuildAdaptiveEnhancePrompt:
    BASE_WITH_YEU_CAU = (
        "Bạn là nhà văn.\n\nCHƯƠNG GỐC:\n...\n\nYÊU CẦU:\n- Tăng kịch tính\n\nBắt đầu viết lại:"
    )
    BASE_WITHOUT_YEU_CAU = "Bạn là nhà văn.\n\nCHƯƠNG GỐC:\n..."

    def test_no_genre_returns_original(self):
        result = build_adaptive_enhance_prompt(self.BASE_WITH_YEU_CAU, "")
        assert result == self.BASE_WITH_YEU_CAU

    def test_unknown_genre_returns_original(self):
        result = build_adaptive_enhance_prompt(self.BASE_WITH_YEU_CAU, "xyz lạ")
        assert result == self.BASE_WITH_YEU_CAU

    def test_genre_inserted_before_yeu_cau(self):
        result = build_adaptive_enhance_prompt(self.BASE_WITH_YEU_CAU, "Xuyên Không")
        assert "PHONG CÁCH THỂ LOẠI XUYÊN KHÔNG:" in result
        idx_genre = result.index("PHONG CÁCH THỂ LOẠI XUYÊN KHÔNG:")
        idx_yc = result.index("YÊU CẦU:")
        assert idx_genre < idx_yc

    def test_original_content_preserved(self):
        result = build_adaptive_enhance_prompt(self.BASE_WITH_YEU_CAU, "Trọng Sinh")
        assert "Bạn là nhà văn." in result
        assert "CHƯƠNG GỐC:" in result
        assert "YÊU CẦU:" in result
        assert "Tăng kịch tính" in result

    def test_fallback_append_when_no_yeu_cau(self):
        result = build_adaptive_enhance_prompt(self.BASE_WITHOUT_YEU_CAU, "Lịch Sử")
        assert "PHONG CÁCH THỂ LOẠI LỊCH SỬ:" in result
        assert "Bạn là nhà văn." in result

    def test_all_known_genres_produce_enhancement(self):
        for genre in GENRE_EMPHASIS:
            result = build_adaptive_enhance_prompt(self.BASE_WITH_YEU_CAU, genre)
            assert len(result) > len(self.BASE_WITH_YEU_CAU), f"No enhancement for {genre}"

    def test_yeu_cau_replaced_only_once(self):
        result = build_adaptive_enhance_prompt(self.BASE_WITH_YEU_CAU, "Đô Thị")
        assert result.count("YÊU CẦU:") == 1

    def test_genre_emphasis_text_present(self):
        result = build_adaptive_enhance_prompt(self.BASE_WITH_YEU_CAU, "Huyền Huyễn")
        assert GENRE_EMPHASIS["Huyền Huyễn"] in result
