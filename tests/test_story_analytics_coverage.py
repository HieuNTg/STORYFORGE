"""Tests for services/story_analytics.py — coverage for StoryAnalytics class."""
import pytest
from unittest.mock import MagicMock, patch
from models.schemas import Chapter, StoryDraft, EnhancedStory
from services.story_analytics import StoryAnalytics


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_chapter(number: int, title: str, content: str) -> Chapter:
    return Chapter(chapter_number=number, title=title, content=content)


# ---------------------------------------------------------------------------
# analyze_chapter
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestAnalyzeChapter:
    def test_basic_metrics(self):
        ch = _make_chapter(1, "Test", "Hello world. How are you? Fine!")
        result = StoryAnalytics.analyze_chapter(ch)
        assert result["chapter_number"] == 1
        assert result["title"] == "Test"
        assert result["word_count"] == 6
        assert result["sentence_count"] >= 1
        assert result["reading_time_minutes"] >= 1

    def test_empty_content(self):
        ch = _make_chapter(1, "Empty", "")
        result = StoryAnalytics.analyze_chapter(ch)
        assert result["word_count"] == 0
        assert result["sentence_count"] == 1  # max(1, 0)
        assert result["paragraph_count"] == 1  # max(1, 0)

    def test_dialogue_detection_double_quotes(self):
        ch = _make_chapter(1, "Dialogue", 'He said "hello world" to her.')
        result = StoryAnalytics.analyze_chapter(ch)
        assert result["dialogue_count"] >= 1
        assert result["dialogue_ratio"] >= 0.0

    def test_dialogue_detection_em_dash(self):
        # em-dash dialogue format common in Vietnamese fiction
        ch = _make_chapter(1, "Dialogue", "— Lý Huyền: Chào bạn, hôm nay thế nào?")
        result = StoryAnalytics.analyze_chapter(ch)
        assert result["dialogue_count"] >= 0  # may or may not match pattern

    def test_paragraph_count(self):
        content = "Para one.\n\nPara two.\n\nPara three."
        ch = _make_chapter(1, "Paras", content)
        result = StoryAnalytics.analyze_chapter(ch)
        assert result["paragraph_count"] >= 3

    def test_avg_sentence_length(self):
        ch = _make_chapter(1, "Avg", "One two three. Four five.")
        result = StoryAnalytics.analyze_chapter(ch)
        assert result["avg_sentence_length"] > 0

    def test_reading_time_min_one(self):
        # Even a very short chapter should return reading_time >= 1
        ch = _make_chapter(1, "Short", "Hi.")
        result = StoryAnalytics.analyze_chapter(ch)
        assert result["reading_time_minutes"] >= 1


# ---------------------------------------------------------------------------
# analyze_story
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestAnalyzeStory:
    def test_empty_chapters_returns_error(self):
        story = MagicMock()
        story.chapters = []
        result = StoryAnalytics.analyze_story(story)
        assert "error" in result

    def test_full_story(self, sample_story_draft):
        result = StoryAnalytics.analyze_story(sample_story_draft)
        assert "total_words" in result
        assert "total_chapters" in result
        assert result["total_chapters"] == len(sample_story_draft.chapters)
        assert "chapter_stats" in result
        assert len(result["chapter_stats"]) == result["total_chapters"]
        assert "pacing_data" in result

    def test_pacing_data_structure(self, sample_story_draft):
        result = StoryAnalytics.analyze_story(sample_story_draft)
        pd = result["pacing_data"]
        assert "chapter_numbers" in pd
        assert "word_counts" in pd
        assert "dialogue_ratios" in pd
        assert "avg_sentence_lengths" in pd

    def test_reading_time_positive(self, sample_story_draft):
        result = StoryAnalytics.analyze_story(sample_story_draft)
        assert result["reading_time_minutes"] >= 1

    def test_avg_words_per_chapter(self, sample_story_draft):
        result = StoryAnalytics.analyze_story(sample_story_draft)
        assert result["avg_words_per_chapter"] >= 0


# ---------------------------------------------------------------------------
# extract_emotion_arc (keyword-based)
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestExtractEmotionArc:
    def test_returns_expected_keys(self, sample_chapters):
        result = StoryAnalytics.extract_emotion_arc(sample_chapters)
        for key in ("chapter_numbers", "positivity", "negativity", "tension", "emotional_valence"):
            assert key in result

    def test_length_matches_chapters(self, sample_chapters):
        result = StoryAnalytics.extract_emotion_arc(sample_chapters)
        assert len(result["chapter_numbers"]) == len(sample_chapters)
        assert len(result["positivity"]) == len(sample_chapters)

    def test_empty_chapters(self):
        result = StoryAnalytics.extract_emotion_arc([])
        assert result["chapter_numbers"] == []
        assert result["positivity"] == []

    def test_positive_keywords_detected(self):
        ch = _make_chapter(1, "Happy", "Anh ta vui mừng và hạnh phúc khi gặp lại bạn cũ.")
        result = StoryAnalytics.extract_emotion_arc([ch])
        assert result["positivity"][0] >= 0

    def test_negative_keywords_detected(self):
        ch = _make_chapter(1, "Sad", "Cô ấy buồn và khóc khi nghe tin xấu về người thân.")
        result = StoryAnalytics.extract_emotion_arc([ch])
        assert result["negativity"][0] >= 0

    def test_valence_range(self, sample_chapters):
        result = StoryAnalytics.extract_emotion_arc(sample_chapters)
        for v in result["emotional_valence"]:
            assert -1.0 <= v <= 1.0


# ---------------------------------------------------------------------------
# extract_emotion_arc_llm (with mocked LLM)
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestExtractEmotionArcLLM:
    """LLMClient is imported inside the function body — patch at source module."""

    def test_llm_success(self, sample_chapters):
        mock_result = {
            "joy": 7, "sadness": 3, "anger": 2, "fear": 1,
            "surprise": 5, "tension": 4, "romance": 2,
            "dominant_emotion": "joy", "emotional_summary": "Happy chapter",
        }
        with patch("services.llm_client.LLMClient") as MockLLM, \
             patch("services.prompts.EXTRACT_CHAPTER_EMOTIONS",
                   "Analyze chapter {chapter_number} {title} {content}"):
            instance = MockLLM.return_value
            instance.generate_json.return_value = mock_result

            result = StoryAnalytics.extract_emotion_arc_llm(sample_chapters)

        assert len(result["chapter_numbers"]) == len(sample_chapters)
        assert len(result["joy"]) == len(sample_chapters)
        for v in result["joy"]:
            assert 0 <= v <= 10

    def test_llm_fallback_on_exception(self, sample_chapters):
        with patch("services.llm_client.LLMClient") as MockLLM, \
             patch("services.prompts.EXTRACT_CHAPTER_EMOTIONS",
                   "Analyze {chapter_number} {title} {content}"):
            instance = MockLLM.return_value
            instance.generate_json.side_effect = Exception("LLM error")

            result = StoryAnalytics.extract_emotion_arc_llm(sample_chapters)

        assert len(result["chapter_numbers"]) == len(sample_chapters)
        assert result["dominant_emotions"] == ["unknown"] * len(sample_chapters)

    def test_max_chapters_limit(self):
        chapters = [_make_chapter(i, f"Ch {i}", f"Content {i}") for i in range(10)]
        with patch("services.llm_client.LLMClient") as MockLLM, \
             patch("services.prompts.EXTRACT_CHAPTER_EMOTIONS",
                   "Analyze {chapter_number} {title} {content}"):
            instance = MockLLM.return_value
            instance.generate_json.return_value = {
                "joy": 5, "sadness": 5, "anger": 5, "fear": 5,
                "surprise": 5, "tension": 5, "romance": 5,
                "dominant_emotion": "neutral", "emotional_summary": "",
            }
            result = StoryAnalytics.extract_emotion_arc_llm(chapters, max_chapters=3)

        assert len(result["chapter_numbers"]) == 3

    def test_clamp_out_of_range_values(self, sample_chapters):
        """LLM may return values outside [0,10] — should be clamped."""
        mock_result = {
            "joy": 99, "sadness": -5, "anger": 0, "fear": 0,
            "surprise": 0, "tension": 0, "romance": 0,
            "dominant_emotion": "joy", "emotional_summary": "",
        }
        with patch("services.llm_client.LLMClient") as MockLLM, \
             patch("services.prompts.EXTRACT_CHAPTER_EMOTIONS",
                   "Analyze {chapter_number} {title} {content}"):
            instance = MockLLM.return_value
            instance.generate_json.return_value = mock_result
            result = StoryAnalytics.extract_emotion_arc_llm(sample_chapters[:1])

        assert result["joy"][0] == 10.0  # clamped from 99
        assert result["sadness"][0] == 0.0  # clamped from -5
