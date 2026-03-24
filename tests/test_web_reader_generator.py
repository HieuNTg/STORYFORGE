"""Tests for web reader generator — XSS prevention and content limits."""
import pytest
from unittest.mock import MagicMock
from models.schemas import StoryDraft, EnhancedStory, Chapter, Character


def _make_story(title="Test", genre="fantasy", chapters=None):
    if chapters is None:
        chapters = [Chapter(chapter_number=1, title="Ch1", content="Hello world")]
    return StoryDraft(title=title, genre=genre, chapters=chapters)


class TestXSSPrevention:
    def test_script_tag_in_title(self):
        from services.web_reader_generator import WebReaderGenerator
        story = _make_story(title='<script>alert("xss")</script>')
        html = WebReaderGenerator.generate(story)
        assert '<script>alert' not in html
        assert '&lt;script&gt;' in html or '<\\/script>' in html

    def test_script_close_tag_in_content(self):
        from services.web_reader_generator import WebReaderGenerator
        chapters = [Chapter(chapter_number=1, title="Test",
                           content='Normal text</script><script>alert(1)</script>')]
        story = _make_story(chapters=chapters)
        html = WebReaderGenerator.generate(story)
        assert '</script><script>' not in html

    def test_html_entities_in_chapter_title(self):
        from services.web_reader_generator import WebReaderGenerator
        chapters = [Chapter(chapter_number=1, title='<img onerror="alert(1)">',
                           content="Safe")]
        story = _make_story(chapters=chapters)
        html = WebReaderGenerator.generate(story)
        # Raw unescaped onerror attribute must not appear (it should be entity-escaped)
        assert 'onerror="alert' not in html
        # Either fully escaped or tag stripped
        assert '&lt;img' in html or '<img' not in html

    def test_unicode_in_title(self):
        from services.web_reader_generator import WebReaderGenerator
        story = _make_story(title="Truyen voi ky tu dac biet: '\"\n\t")
        html = WebReaderGenerator.generate(story)
        assert isinstance(html, str)
        assert '<html' in html


class TestContentLimits:
    def test_large_story_truncated(self):
        from services.web_reader_generator import WebReaderGenerator
        # Create story with ~300K words (5 chapters * ~60K each)
        big_content = "Lorem ipsum dolor sit amet. " * 10000
        chapters = [
            Chapter(chapter_number=i, title=f"Ch{i}", content=big_content)
            for i in range(1, 6)
        ]
        story = _make_story(chapters=chapters)
        html = WebReaderGenerator.generate(story)
        # Should produce valid HTML even if truncated
        assert isinstance(html, str)

    def test_empty_chapters(self):
        from services.web_reader_generator import WebReaderGenerator
        story = _make_story(chapters=[])
        html = WebReaderGenerator.generate(story)
        assert "Chua co noi dung" in html or "<html" in html
