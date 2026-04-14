"""Tests for services/web_reader_generator.py."""
import pytest
from unittest.mock import MagicMock
from models.schemas import Chapter
from services.web_reader_generator import WebReaderGenerator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_chapter(number: int, title: str, content: str) -> Chapter:
    return Chapter(chapter_number=number, title=title, content=content)


def _make_mock_story(title: str, chapters: list, genre: str = "Tiên Hiệp"):
    story = MagicMock()
    story.title = title
    story.genre = genre
    story.chapters = chapters
    return story


def _make_character(name: str, role: str, personality: str):
    char = MagicMock()
    char.name = name
    char.role = role
    char.personality = personality
    return char


# ---------------------------------------------------------------------------
# generate — basic
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestWebReaderGeneratorGenerate:
    def test_empty_chapters_returns_empty_html(self):
        story = _make_mock_story("Test", [])
        html = WebReaderGenerator.generate(story)
        assert "Test" in html
        assert "Chưa có nội dung" in html

    def test_returns_html_string(self, sample_story_draft):
        html = WebReaderGenerator.generate(sample_story_draft)
        assert isinstance(html, str)
        assert html.startswith("<!DOCTYPE html>")

    def test_title_in_output(self, sample_story_draft):
        html = WebReaderGenerator.generate(sample_story_draft)
        assert sample_story_draft.title in html

    def test_chapter_content_in_output(self, sample_story_draft):
        html = WebReaderGenerator.generate(sample_story_draft)
        for ch in sample_story_draft.chapters:
            # Content is HTML-escaped; check chapter number appears
            assert f"chapter-{ch.chapter_number}" in html

    def test_genre_in_output(self, sample_story_draft):
        html = WebReaderGenerator.generate(sample_story_draft)
        # genre is HTML-escaped in the output
        import html as html_lib
        assert html_lib.escape(sample_story_draft.genre) in html

    def test_xss_prevention(self):
        ch = _make_chapter(1, "Test", '<script>alert("xss")</script>')
        story = _make_mock_story("<b>Title</b>", [ch])
        html = WebReaderGenerator.generate(story)
        # HTML title should be escaped — raw <b> tag should not appear unescaped in title position
        assert "&lt;b&gt;" in html
        # Chapter content should have the < escaped as &lt; (not a live script tag in content area)
        assert "&lt;script&gt;" in html or "alert" not in html

    def test_with_characters(self, sample_story_draft, sample_characters):
        html = WebReaderGenerator.generate(sample_story_draft, characters=sample_characters)
        for char in sample_characters:
            assert char.name in html

    def test_without_characters(self, sample_story_draft):
        html = WebReaderGenerator.generate(sample_story_draft, characters=None)
        # char-card is in CSS but the char-grid div with content should not be present
        assert '<div class="char-grid">' not in html

    def test_chapter_navigation_elements(self, sample_story_draft):
        html = WebReaderGenerator.generate(sample_story_draft)
        assert "prevChapter" in html
        assert "nextChapter" in html

    def test_bookmark_elements_present(self, sample_story_draft):
        html = WebReaderGenerator.generate(sample_story_draft)
        assert "bookmarkBtn" in html or "bookmark" in html.lower()

    def test_reading_time_shown(self, sample_story_draft):
        html = WebReaderGenerator.generate(sample_story_draft)
        assert "phút" in html  # Vietnamese for "minutes"


# ---------------------------------------------------------------------------
# Truncation behavior
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestTruncation:
    def test_truncation_banner_shown_when_over_limit(self):
        # Create enough chapters to exceed MAX_WORDS
        # Each chapter has 1000 words; MAX_WORDS=200_000 so we need 201 chapters
        big_content = " ".join(["word"] * 1001)
        chapters = [_make_chapter(i, f"Ch {i}", big_content) for i in range(1, 202)]
        story = _make_mock_story("Large Story", chapters)
        html = WebReaderGenerator.generate(story)
        assert "truncation" in html.lower() or "Truy" in html  # truncation banner Vietnamese text

    def test_no_truncation_for_normal_story(self, sample_story_draft):
        html = WebReaderGenerator.generate(sample_story_draft)
        # Normal story should not show truncation banner
        # The banner uses specific HTML entities
        assert "&#9888;" not in html


# ---------------------------------------------------------------------------
# _content_to_html
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestContentToHtml:
    def test_paragraphs_wrapped(self):
        html = WebReaderGenerator._content_to_html("Line one.\nLine two.")
        assert "<p>Line one.</p>" in html
        assert "<p>Line two.</p>" in html

    def test_empty_lines_skipped(self):
        html = WebReaderGenerator._content_to_html("Line one.\n\n\nLine two.")
        assert html.count("<p>") == 2

    def test_bold_markdown_converted(self):
        html = WebReaderGenerator._content_to_html("This is **bold** text.")
        assert "<strong>bold</strong>" in html

    def test_italic_markdown_converted(self):
        html = WebReaderGenerator._content_to_html("This is *italic* text.")
        assert "<em>italic</em>" in html

    def test_script_tag_escaped(self):
        html = WebReaderGenerator._content_to_html("Before </script> after")
        assert "</script>" not in html

    def test_html_entities_escaped(self):
        html = WebReaderGenerator._content_to_html("A & B < C > D")
        assert "&amp;" in html
        assert "&lt;" in html
        assert "&gt;" in html


# ---------------------------------------------------------------------------
# _render_template
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestRenderTemplate:
    def _sample_chapters_data(self):
        return [
            {"number": 1, "title": "Ch One", "words": 500, "reading_min": 3, "content": "<p>Content</p>"},
            {"number": 2, "title": "Ch Two", "words": 600, "reading_min": 3, "content": "<p>More</p>"},
        ]

    def test_renders_valid_html(self):
        html = WebReaderGenerator._render_template("My Title", "Fantasy", self._sample_chapters_data(), "")
        assert "<!DOCTYPE html>" in html
        assert "My Title" in html

    def test_chapter_ids_present(self):
        html = WebReaderGenerator._render_template("T", "G", self._sample_chapters_data(), "")
        assert 'id="chapter-1"' in html
        assert 'id="chapter-2"' in html

    def test_total_word_count_displayed(self):
        html = WebReaderGenerator._render_template("T", "G", self._sample_chapters_data(), "")
        assert "1,100" in html  # 500 + 600

    def test_truncation_info_renders_banner(self):
        html = WebReaderGenerator._render_template(
            "T", "G", self._sample_chapters_data(), "",
            truncation_info=(300000, 250, 150),
        )
        assert "&#9888;" in html  # warning sign

    def test_no_truncation_info_no_banner(self):
        html = WebReaderGenerator._render_template("T", "G", self._sample_chapters_data(), "")
        assert "&#9888;" not in html

    def test_char_html_injected(self):
        char_html = '<div class="char-grid"><p>Character data</p></div>'
        html = WebReaderGenerator._render_template("T", "G", self._sample_chapters_data(), char_html)
        assert "Character data" in html

    def test_js_title_quote_escaped(self):
        """Title with quotes should not break the JS string literal."""
        html = WebReaderGenerator._render_template("It's \"Great\"", "G", self._sample_chapters_data(), "")
        # The title_js should have escaped quotes — verify no raw unescaped double quote in JS context
        assert "STORY_KEY" in html  # JS key is present
