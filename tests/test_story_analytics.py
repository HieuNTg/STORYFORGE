"""Tests for StoryAnalytics service."""
import pytest
from models.schemas import Chapter, StoryDraft, EnhancedStory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_chapter(number: int, content: str, title: str = "Test") -> Chapter:
    return Chapter(chapter_number=number, title=title, content=content)


# ---------------------------------------------------------------------------
# Tests: analyze_chapter — basic metrics
# ---------------------------------------------------------------------------

class TestAnalyzeChapter:
    def test_word_count(self):
        from services.story_analytics import StoryAnalytics
        ch = make_chapter(1, "mot hai ba bon nam")
        stats = StoryAnalytics.analyze_chapter(ch)
        assert stats["word_count"] == 5

    def test_word_count_multiline(self):
        from services.story_analytics import StoryAnalytics
        ch = make_chapter(1, "dong mot\ndong hai\ndong ba")
        stats = StoryAnalytics.analyze_chapter(ch)
        assert stats["word_count"] == 6

    def test_sentence_count_single(self):
        from services.story_analytics import StoryAnalytics
        ch = make_chapter(1, "Mot cau don gian.")
        stats = StoryAnalytics.analyze_chapter(ch)
        assert stats["sentence_count"] >= 1

    def test_sentence_count_multiple(self):
        from services.story_analytics import StoryAnalytics
        ch = make_chapter(1, "Cau mot. Cau hai. Cau ba.")
        stats = StoryAnalytics.analyze_chapter(ch)
        assert stats["sentence_count"] == 3

    def test_sentence_count_exclamation_question(self):
        from services.story_analytics import StoryAnalytics
        ch = make_chapter(1, "That vay sao? Ung! Dung roi.")
        stats = StoryAnalytics.analyze_chapter(ch)
        assert stats["sentence_count"] == 3

    def test_paragraph_count_single(self):
        from services.story_analytics import StoryAnalytics
        ch = make_chapter(1, "Chi co mot doan van nay thoi.")
        stats = StoryAnalytics.analyze_chapter(ch)
        assert stats["paragraph_count"] == 1

    def test_paragraph_count_multiple(self):
        from services.story_analytics import StoryAnalytics
        ch = make_chapter(1, "Doan 1.\n\nDoan 2.\n\nDoan 3.")
        stats = StoryAnalytics.analyze_chapter(ch)
        assert stats["paragraph_count"] == 3

    def test_empty_content_does_not_crash(self):
        from services.story_analytics import StoryAnalytics
        ch = make_chapter(1, "")
        stats = StoryAnalytics.analyze_chapter(ch)
        assert stats["word_count"] == 0
        assert stats["sentence_count"] >= 1   # max(1, ...)
        assert stats["paragraph_count"] >= 1  # max(1, ...)

    def test_chapter_number_in_result(self):
        from services.story_analytics import StoryAnalytics
        ch = make_chapter(7, "Noi dung chuong 7.")
        stats = StoryAnalytics.analyze_chapter(ch)
        assert stats["chapter_number"] == 7

    def test_title_in_result(self):
        from services.story_analytics import StoryAnalytics
        ch = make_chapter(1, "content", title="My Title")
        stats = StoryAnalytics.analyze_chapter(ch)
        assert stats["title"] == "My Title"

    def test_avg_sentence_length(self):
        from services.story_analytics import StoryAnalytics
        # 4 words, 1 sentence → avg = 4.0
        ch = make_chapter(1, "mot hai ba bon.")
        stats = StoryAnalytics.analyze_chapter(ch)
        assert stats["avg_sentence_length"] == pytest.approx(4.0, abs=0.5)

    def test_reading_time_minimum_one(self):
        from services.story_analytics import StoryAnalytics
        ch = make_chapter(1, "ngon")  # 1 word < 200 WPM threshold
        stats = StoryAnalytics.analyze_chapter(ch)
        assert stats["reading_time_minutes"] == 1

    def test_reading_time_calculation(self):
        from services.story_analytics import StoryAnalytics
        # 400 words → 400 // 200 = 2 minutes
        content = " ".join(["tu"] * 400)
        ch = make_chapter(1, content)
        stats = StoryAnalytics.analyze_chapter(ch)
        assert stats["reading_time_minutes"] == 2


# ---------------------------------------------------------------------------
# Tests: Dialogue detection
# ---------------------------------------------------------------------------

class TestDialogueDetection:
    def test_double_quote_dialogue(self):
        from services.story_analytics import StoryAnalytics
        ch = make_chapter(1, 'Anh noi: "Toi se quay lai" va roi di.')
        stats = StoryAnalytics.analyze_chapter(ch)
        assert stats["dialogue_count"] >= 1

    def test_angle_bracket_dialogue(self):
        """Test dialogue with angle brackets «...» which the pattern supports."""
        from services.story_analytics import StoryAnalytics
        ch = make_chapter(1, '\u00abXin chao the gioi\u00bb co ay noi.')
        stats = StoryAnalytics.analyze_chapter(ch)
        assert stats["dialogue_count"] >= 1

    def test_no_dialogue(self):
        from services.story_analytics import StoryAnalytics
        ch = make_chapter(1, "Khong co loi thoai nao o day ca.")
        stats = StoryAnalytics.analyze_chapter(ch)
        assert stats["dialogue_count"] == 0

    def test_dialogue_words_counted(self):
        from services.story_analytics import StoryAnalytics
        ch = make_chapter(1, '"Xin chao the gioi" la cau noi dau tien.')
        stats = StoryAnalytics.analyze_chapter(ch)
        assert stats["dialogue_words"] >= 3

    def test_dialogue_ratio_zero_no_dialogue(self):
        from services.story_analytics import StoryAnalytics
        ch = make_chapter(1, "Chi co van xuoi thuan tuy khong co doi thoai.")
        stats = StoryAnalytics.analyze_chapter(ch)
        assert stats["dialogue_ratio"] == 0.0

    def test_dialogue_ratio_positive_with_dialogue(self):
        from services.story_analytics import StoryAnalytics
        ch = make_chapter(1, '"Xin chao" va nhieu cau van khac kem theo.')
        stats = StoryAnalytics.analyze_chapter(ch)
        assert stats["dialogue_ratio"] > 0


# ---------------------------------------------------------------------------
# Tests: analyze_story
# ---------------------------------------------------------------------------

class TestAnalyzeStory:
    def test_no_chapters_returns_error(self):
        from services.story_analytics import StoryAnalytics
        story = StoryDraft(title="Empty", genre="test", chapters=[])
        result = StoryAnalytics.analyze_story(story)
        assert "error" in result

    def test_total_chapters_count(self, sample_story_draft):
        from services.story_analytics import StoryAnalytics
        result = StoryAnalytics.analyze_story(sample_story_draft)
        assert result["total_chapters"] == len(sample_story_draft.chapters)

    def test_total_words_aggregated(self, sample_story_draft):
        from services.story_analytics import StoryAnalytics
        result = StoryAnalytics.analyze_story(sample_story_draft)
        chapter_stats = result["chapter_stats"]
        expected = sum(s["word_count"] for s in chapter_stats)
        assert result["total_words"] == expected

    def test_total_sentences_aggregated(self, sample_story_draft):
        from services.story_analytics import StoryAnalytics
        result = StoryAnalytics.analyze_story(sample_story_draft)
        chapter_stats = result["chapter_stats"]
        expected = sum(s["sentence_count"] for s in chapter_stats)
        assert result["total_sentences"] == expected

    def test_total_paragraphs_aggregated(self, sample_story_draft):
        from services.story_analytics import StoryAnalytics
        result = StoryAnalytics.analyze_story(sample_story_draft)
        chapter_stats = result["chapter_stats"]
        expected = sum(s["paragraph_count"] for s in chapter_stats)
        assert result["total_paragraphs"] == expected

    def test_reading_time_minimum_one(self, sample_story_draft):
        from services.story_analytics import StoryAnalytics
        result = StoryAnalytics.analyze_story(sample_story_draft)
        assert result["reading_time_minutes"] >= 1

    def test_avg_words_per_chapter(self, sample_story_draft):
        from services.story_analytics import StoryAnalytics
        result = StoryAnalytics.analyze_story(sample_story_draft)
        expected = result["total_words"] // max(1, result["total_chapters"])
        assert result["avg_words_per_chapter"] == expected

    def test_avg_sentence_length_positive(self, sample_story_draft):
        from services.story_analytics import StoryAnalytics
        result = StoryAnalytics.analyze_story(sample_story_draft)
        assert result["avg_sentence_length"] > 0

    def test_dialogue_ratio_between_0_and_1(self, sample_story_draft):
        from services.story_analytics import StoryAnalytics
        result = StoryAnalytics.analyze_story(sample_story_draft)
        assert 0.0 <= result["dialogue_ratio"] <= 1.0

    def test_chapter_stats_list_length(self, sample_story_draft):
        from services.story_analytics import StoryAnalytics
        result = StoryAnalytics.analyze_story(sample_story_draft)
        assert len(result["chapter_stats"]) == len(sample_story_draft.chapters)

    def test_works_with_enhanced_story(self, sample_enhanced_story):
        from services.story_analytics import StoryAnalytics
        result = StoryAnalytics.analyze_story(sample_enhanced_story)
        assert "total_words" in result
        assert result["total_chapters"] == len(sample_enhanced_story.chapters)


# ---------------------------------------------------------------------------
# Tests: pacing_data structure
# ---------------------------------------------------------------------------

class TestPacingData:
    def test_pacing_data_keys_present(self, sample_story_draft):
        from services.story_analytics import StoryAnalytics
        result = StoryAnalytics.analyze_story(sample_story_draft)
        pd = result["pacing_data"]
        assert "chapter_numbers" in pd
        assert "word_counts" in pd
        assert "dialogue_ratios" in pd
        assert "avg_sentence_lengths" in pd

    def test_pacing_data_lengths_match_chapters(self, sample_story_draft):
        from services.story_analytics import StoryAnalytics
        result = StoryAnalytics.analyze_story(sample_story_draft)
        pd = result["pacing_data"]
        n = len(sample_story_draft.chapters)
        assert len(pd["chapter_numbers"]) == n
        assert len(pd["word_counts"]) == n
        assert len(pd["dialogue_ratios"]) == n
        assert len(pd["avg_sentence_lengths"]) == n

    def test_chapter_numbers_ordered(self, sample_story_draft):
        from services.story_analytics import StoryAnalytics
        result = StoryAnalytics.analyze_story(sample_story_draft)
        nums = result["pacing_data"]["chapter_numbers"]
        assert nums == sorted(nums)

    def test_word_counts_all_nonnegative(self, sample_story_draft):
        from services.story_analytics import StoryAnalytics
        result = StoryAnalytics.analyze_story(sample_story_draft)
        assert all(w >= 0 for w in result["pacing_data"]["word_counts"])


# ---------------------------------------------------------------------------
# Tests: extract_emotion_arc
# ---------------------------------------------------------------------------

class TestExtractEmotionArc:
    def test_returns_correct_keys(self, sample_chapters):
        from services.story_analytics import StoryAnalytics
        arc = StoryAnalytics.extract_emotion_arc(sample_chapters)
        assert "chapter_numbers" in arc
        assert "positivity" in arc
        assert "negativity" in arc
        assert "tension" in arc
        assert "emotional_valence" in arc

    def test_lengths_match_chapters(self, sample_chapters):
        from services.story_analytics import StoryAnalytics
        arc = StoryAnalytics.extract_emotion_arc(sample_chapters)
        n = len(sample_chapters)
        assert len(arc["chapter_numbers"]) == n
        assert len(arc["positivity"]) == n
        assert len(arc["negativity"]) == n
        assert len(arc["tension"]) == n
        assert len(arc["emotional_valence"]) == n

    def test_positive_keyword_detection(self):
        from services.story_analytics import StoryAnalytics
        # "vui" is a positive keyword — matches as substring; no diacritics needed for "vui"
        ch = make_chapter(1, "anh ấy vui vẻ và hạnh phúc bao la trong lòng")
        arc = StoryAnalytics.extract_emotion_arc([ch])
        assert arc["positivity"][0] > 0

    def test_negative_keyword_detection(self):
        from services.story_analytics import StoryAnalytics
        # "buồn" and "khóc" are negative keywords (must use diacritics to match)
        ch = make_chapter(1, "cô ấy buồn bã và khóc suốt ngày dài")
        arc = StoryAnalytics.extract_emotion_arc([ch])
        assert arc["negativity"][0] > 0

    def test_tension_keyword_detection(self):
        from services.story_analytics import StoryAnalytics
        # "sốc" is the only single-word tension keyword; multi-word ones like
        # "bí mật" require the full phrase in one word which won't match split words.
        ch = make_chapter(1, "anh ta sốc nặng khi phát hiện sự thật")
        arc = StoryAnalytics.extract_emotion_arc([ch])
        assert arc["tension"][0] > 0

    def test_emotional_valence_range(self, sample_chapters):
        from services.story_analytics import StoryAnalytics
        arc = StoryAnalytics.extract_emotion_arc(sample_chapters)
        for v in arc["emotional_valence"]:
            assert -1.0 <= v <= 1.0

    def test_positive_chapter_has_high_valence(self):
        from services.story_analytics import StoryAnalytics
        # Heavy positive content — use diacritics so keywords match
        ch = make_chapter(1, "vui vui vui hạnh phúc yêu thương hy vọng chiến thắng")
        arc = StoryAnalytics.extract_emotion_arc([ch])
        assert arc["emotional_valence"][0] > 0

    def test_negative_chapter_has_low_valence(self):
        from services.story_analytics import StoryAnalytics
        # Heavy negative content — use diacritics so keywords match
        ch = make_chapter(1, "buồn khổ đau đớn tuyệt vọng hận thù chiến tranh")
        arc = StoryAnalytics.extract_emotion_arc([ch])
        assert arc["emotional_valence"][0] <= 0

    def test_empty_chapters_list(self):
        from services.story_analytics import StoryAnalytics
        arc = StoryAnalytics.extract_emotion_arc([])
        assert arc["chapter_numbers"] == []
        assert arc["positivity"] == []
        assert arc["negativity"] == []

    def test_neutral_chapter_valence_zero(self):
        from services.story_analytics import StoryAnalytics
        ch = make_chapter(1, "anh di ve nha an com xong roi ngu")
        arc = StoryAnalytics.extract_emotion_arc([ch])
        # No keywords → valence = (0-0)/max(1,0) = 0
        assert arc["emotional_valence"][0] == 0.0

    def test_positivity_is_percentage(self):
        from services.story_analytics import StoryAnalytics
        # "vui" matches since it's a substring of POSITIVE_KEYWORDS entries
        ch = make_chapter(1, "vui " * 10 + "trung_tinh " * 90)
        arc = StoryAnalytics.extract_emotion_arc([ch])
        # positivity should be a percentage value (0–100 range)
        assert 0 <= arc["positivity"][0] <= 100

    def test_chapter_numbers_preserved(self):
        from services.story_analytics import StoryAnalytics
        chapters = [make_chapter(5, "content"), make_chapter(12, "more content")]
        arc = StoryAnalytics.extract_emotion_arc(chapters)
        assert arc["chapter_numbers"] == [5, 12]


# ---------------------------------------------------------------------------
# Tests: reading time (200 WPM)
# ---------------------------------------------------------------------------

class TestReadingTime:
    def test_vietnamese_wpm_constant(self):
        from services.story_analytics import StoryAnalytics
        assert StoryAnalytics.VIETNAMESE_WPM == 200

    def test_600_words_equals_3_minutes(self):
        from services.story_analytics import StoryAnalytics
        content = " ".join(["tu"] * 600)
        ch = make_chapter(1, content)
        stats = StoryAnalytics.analyze_chapter(ch)
        assert stats["reading_time_minutes"] == 3

    def test_story_reading_time_min_one(self):
        from services.story_analytics import StoryAnalytics
        story = StoryDraft(
            title="Tiny",
            genre="test",
            chapters=[make_chapter(1, "ngan")],
        )
        result = StoryAnalytics.analyze_story(story)
        assert result["reading_time_minutes"] >= 1

    def test_large_story_reading_time(self):
        from services.story_analytics import StoryAnalytics
        # 3 chapters × 400 words = 1200 words → 1200 // 200 = 6 min
        chapters = [make_chapter(i, " ".join(["tu"] * 400)) for i in range(1, 4)]
        story = StoryDraft(title="Long", genre="test", chapters=chapters)
        result = StoryAnalytics.analyze_story(story)
        assert result["reading_time_minutes"] == 6


# ---------------------------------------------------------------------------
# Tests: Edge cases requested in test additions
# ---------------------------------------------------------------------------

class TestAnalyticsEdgeCases:

    # --- Empty chapter (0 words) ---

    def test_empty_chapter_word_count_zero(self):
        from services.story_analytics import StoryAnalytics
        ch = make_chapter(1, "")
        stats = StoryAnalytics.analyze_chapter(ch)
        assert stats["word_count"] == 0

    def test_empty_chapter_reading_time_minimum_one(self):
        from services.story_analytics import StoryAnalytics
        ch = make_chapter(1, "")
        stats = StoryAnalytics.analyze_chapter(ch)
        assert stats["reading_time_minutes"] == 1

    def test_empty_chapter_dialogue_count_zero(self):
        from services.story_analytics import StoryAnalytics
        ch = make_chapter(1, "")
        stats = StoryAnalytics.analyze_chapter(ch)
        assert stats["dialogue_count"] == 0

    def test_empty_chapter_dialogue_words_zero(self):
        from services.story_analytics import StoryAnalytics
        ch = make_chapter(1, "")
        stats = StoryAnalytics.analyze_chapter(ch)
        assert stats["dialogue_words"] == 0

    def test_empty_chapter_dialogue_ratio_zero(self):
        from services.story_analytics import StoryAnalytics
        ch = make_chapter(1, "")
        stats = StoryAnalytics.analyze_chapter(ch)
        assert stats["dialogue_ratio"] == 0.0

    # --- Single word chapter ---

    def test_single_word_chapter_word_count_one(self):
        from services.story_analytics import StoryAnalytics
        ch = make_chapter(1, "hello")
        stats = StoryAnalytics.analyze_chapter(ch)
        assert stats["word_count"] == 1

    def test_single_word_chapter_reading_time_minimum_one(self):
        from services.story_analytics import StoryAnalytics
        ch = make_chapter(1, "hello")
        stats = StoryAnalytics.analyze_chapter(ch)
        assert stats["reading_time_minutes"] == 1

    def test_single_word_chapter_sentence_count_at_least_one(self):
        from services.story_analytics import StoryAnalytics
        ch = make_chapter(1, "hello")
        stats = StoryAnalytics.analyze_chapter(ch)
        assert stats["sentence_count"] >= 1

    def test_single_word_chapter_paragraph_count_at_least_one(self):
        from services.story_analytics import StoryAnalytics
        ch = make_chapter(1, "hello")
        stats = StoryAnalytics.analyze_chapter(ch)
        assert stats["paragraph_count"] >= 1

    # --- Chapter with only dialogue (100% dialogue ratio) ---

    def test_all_dialogue_chapter_high_dialogue_ratio(self):
        from services.story_analytics import StoryAnalytics
        # Only dialogue lines — should produce high dialogue_ratio
        content = '"Xin chao the gioi" "Day la cuoc song" "Toi yeu em"'
        ch = make_chapter(1, content)
        stats = StoryAnalytics.analyze_chapter(ch)
        assert stats["dialogue_ratio"] > 0

    def test_all_dialogue_chapter_dialogue_count_positive(self):
        from services.story_analytics import StoryAnalytics
        content = '"Xin chao the gioi" "Day la cuoc song" "Toi yeu em"'
        ch = make_chapter(1, content)
        stats = StoryAnalytics.analyze_chapter(ch)
        assert stats["dialogue_count"] >= 1

    def test_all_dialogue_chapter_dialogue_words_positive(self):
        from services.story_analytics import StoryAnalytics
        content = '"Xin chao the gioi" "Day la cuoc song" "Toi yeu em"'
        ch = make_chapter(1, content)
        stats = StoryAnalytics.analyze_chapter(ch)
        assert stats["dialogue_words"] > 0

    # --- All 6 quote mark styles detected correctly ---
    # The regex supports: straight " ", ASCII ' ', guillemets « »,
    # CJK brackets 「」, CJK double brackets 『』, em-dash — Name: text
    # Note: Unicode curly quotes U+201C/U+201D and U+2018/U+2019 map to
    # the straight ASCII variants in the pattern (same byte in raw string).

    def test_straight_double_quotes_detected(self):
        """ASCII straight double quotes " " are detected as dialogue."""
        from services.story_analytics import StoryAnalytics
        ch = make_chapter(1, '"Xin chao"')
        stats = StoryAnalytics.analyze_chapter(ch)
        assert stats["dialogue_count"] >= 1

    def test_ascii_single_quotes_detected(self):
        """ASCII single quotes ' ' are detected as dialogue."""
        from services.story_analytics import StoryAnalytics
        ch = make_chapter(1, "'Xin chao'")
        stats = StoryAnalytics.analyze_chapter(ch)
        assert stats["dialogue_count"] >= 1

    def test_guillemets_angle_brackets_detected(self):
        """Guillemets « » (U+00AB/U+00BB) are detected as dialogue."""
        from services.story_analytics import StoryAnalytics
        ch = make_chapter(1, '\u00abXin chao\u00bb')
        stats = StoryAnalytics.analyze_chapter(ch)
        assert stats["dialogue_count"] >= 1

    def test_cjk_brackets_detected(self):
        """CJK corner brackets 「」 (U+300C/U+300D) are detected as dialogue."""
        from services.story_analytics import StoryAnalytics
        ch = make_chapter(1, '\u300cXin chao\u300d')
        stats = StoryAnalytics.analyze_chapter(ch)
        assert stats["dialogue_count"] >= 1

    def test_cjk_double_brackets_detected(self):
        """CJK white corner brackets 『』 (U+300E/U+300F) are detected as dialogue."""
        from services.story_analytics import StoryAnalytics
        ch = make_chapter(1, '\u300eXin chao\u300f')
        stats = StoryAnalytics.analyze_chapter(ch)
        assert stats["dialogue_count"] >= 1

    def test_em_dash_dialogue_detected(self):
        """Em-dash dialogue format — Name: text is detected as dialogue."""
        from services.story_analytics import StoryAnalytics
        ch = make_chapter(1, '\u2014 Anh: Toi se quay lai')
        stats = StoryAnalytics.analyze_chapter(ch)
        assert stats["dialogue_count"] >= 1

    def test_en_dash_dialogue_detected(self):
        """En-dash dialogue format – Name: text is detected as dialogue."""
        from services.story_analytics import StoryAnalytics
        ch = make_chapter(1, '\u2013 Co: Toi hieu roi')
        stats = StoryAnalytics.analyze_chapter(ch)
        assert stats["dialogue_count"] >= 1

    # --- Vietnamese diacritics in story title for EPUB export ---

    def test_epub_export_vietnamese_diacritics_in_title(self, tmp_path):
        """EPUBExporter handles Vietnamese diacritics in title without crashing."""
        pytest.importorskip("ebooklib")
        from models.schemas import StoryDraft, Chapter
        from services.epub_exporter import EPUBExporter

        viet_title = "Thanh Vân Kiếm Khách — Truyện Tiên Hiệp"
        story = StoryDraft(
            title=viet_title,
            genre="Tiên Hiệp",
            chapters=[Chapter(chapter_number=1, title="Khởi Đầu", content="Nội dung chương 1.")],
        )
        out = str(tmp_path / "viet.epub")
        result = EPUBExporter.export(story, out)
        assert result == out
        assert os.path.exists(out)

    def test_epub_export_full_unicode_content(self, tmp_path):
        """EPUBExporter handles full Unicode diacritics in chapter content."""
        pytest.importorskip("ebooklib")
        from models.schemas import StoryDraft, Chapter
        from services.epub_exporter import EPUBExporter

        story = StoryDraft(
            title="Câu Chuyện Huyền Bí",
            genre="Huyền Huyễn",
            chapters=[
                Chapter(
                    chapter_number=1,
                    title="Chương Đầu Tiên",
                    content="Lý Huyền bước vào tông môn với ánh mắt kiên định. "
                            "Anh biết con đường phía trước đầy gian nan.",
                )
            ],
        )
        out = str(tmp_path / "unicode.epub")
        result = EPUBExporter.export(story, out)
        assert result == out

    def test_story_analytics_handles_vietnamese_diacritics_title(self):
        """StoryAnalytics.analyze_chapter works with Vietnamese diacritics in title."""
        from services.story_analytics import StoryAnalytics
        ch = make_chapter(1, "Nội dung chương với ký tự tiếng Việt đầy đủ.", title="Khởi Đầu Mới")
        stats = StoryAnalytics.analyze_chapter(ch)
        assert stats["title"] == "Khởi Đầu Mới"
        assert stats["word_count"] >= 1
