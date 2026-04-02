"""Tests for services/html_exporter.py — HTMLExporter and helper functions."""
import os

from models.schemas import (
    Chapter, Character, StoryDraft, EnhancedStory,
)
from services.html_exporter import (
    HTMLExporter,
    _md_to_html,
    _build_chapter_nav,
    _build_character_cards,
    _build_chapters_html,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_chapter(num=1, title="Test Chapter", content="Hello world."):
    return Chapter(chapter_number=num, title=title, content=content)


def _make_character(name="Alice", role="protagonist", personality="brave", motivation="save world"):
    return Character(name=name, role=role, personality=personality, motivation=motivation, background="unknown")


def _make_story_draft(title="My Story", genre="tien_hiep", chapters=None, characters=None):
    return StoryDraft(
        title=title,
        genre=genre,
        synopsis="A great story",
        chapters=chapters or [_make_chapter()],
        characters=characters or [_make_character()],
    )


def _make_enhanced_story(title="Enhanced Story", drama_score=0.75, chapters=None):
    return EnhancedStory(
        title=title,
        genre="tien_hiep",
        drama_score=drama_score,
        chapters=chapters or [_make_chapter()],
    )


# ---------------------------------------------------------------------------
# _md_to_html
# ---------------------------------------------------------------------------

class TestMdToHtml:
    def test_bold_conversion(self):
        result = _md_to_html("**bold text**")
        assert "<strong>bold text</strong>" in result

    def test_italic_conversion(self):
        result = _md_to_html("*italic text*")
        assert "<em>italic text</em>" in result

    def test_horizontal_rule(self):
        result = _md_to_html("---")
        assert "<hr>" in result

    def test_paragraphs_wrapped_in_p_tags(self):
        result = _md_to_html("Para one.\n\nPara two.")
        assert "<p>" in result
        assert result.count("<p>") >= 2

    def test_html_special_chars_escaped(self):
        result = _md_to_html("<script>alert('xss')</script>")
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    def test_newline_within_paragraph_becomes_br(self):
        result = _md_to_html("Line one\nLine two")
        assert "<br>" in result

    def test_empty_string_returns_empty(self):
        result = _md_to_html("")
        assert result == ""

    def test_plain_text_wrapped_in_p(self):
        result = _md_to_html("Hello world")
        assert "<p>Hello world</p>" in result

    def test_bold_and_italic_combined(self):
        result = _md_to_html("**bold** and *italic*")
        assert "<strong>bold</strong>" in result
        assert "<em>italic</em>" in result


# ---------------------------------------------------------------------------
# _build_chapter_nav
# ---------------------------------------------------------------------------

class TestBuildChapterNav:
    def test_generates_anchor_links(self):
        chapters = [_make_chapter(1, "Intro"), _make_chapter(2, "Conflict")]
        nav = _build_chapter_nav(chapters)
        assert 'href="#ch-1"' in nav
        assert 'href="#ch-2"' in nav

    def test_chapter_titles_in_nav(self):
        chapters = [_make_chapter(1, "Chapter One")]
        nav = _build_chapter_nav(chapters)
        assert "Chapter One" in nav

    def test_empty_chapters_returns_empty(self):
        nav = _build_chapter_nav([])
        assert nav == ""

    def test_special_chars_in_title_escaped(self):
        chapters = [_make_chapter(1, "<script>")]
        nav = _build_chapter_nav(chapters)
        assert "<script>" not in nav
        assert "&lt;script&gt;" in nav

    def test_nav_item_class_present(self):
        chapters = [_make_chapter(1, "Test")]
        nav = _build_chapter_nav(chapters)
        assert 'class="nav-item"' in nav


# ---------------------------------------------------------------------------
# _build_character_cards
# ---------------------------------------------------------------------------

class TestBuildCharacterCards:
    def test_empty_list_returns_empty_string(self):
        result = _build_character_cards([])
        assert result == ""

    def test_character_name_in_output(self):
        chars = [_make_character("Alice")]
        result = _build_character_cards(chars)
        assert "Alice" in result

    def test_character_role_in_output(self):
        chars = [_make_character("Bob", role="antagonist")]
        result = _build_character_cards(chars)
        assert "antagonist" in result

    def test_multiple_characters_all_rendered(self):
        chars = [_make_character("Alice"), _make_character("Bob")]
        result = _build_character_cards(chars)
        assert "Alice" in result
        assert "Bob" in result

    def test_char_card_class_present(self):
        chars = [_make_character()]
        result = _build_character_cards(chars)
        assert 'class="char-card"' in result

    def test_xss_in_name_escaped(self):
        chars = [_make_character(name="<script>bad</script>")]
        result = _build_character_cards(chars)
        assert "<script>" not in result

    def test_characters_section_wraps_cards(self):
        chars = [_make_character("Alice")]
        result = _build_character_cards(chars)
        assert 'id="characters"' in result


# ---------------------------------------------------------------------------
# _build_chapters_html
# ---------------------------------------------------------------------------

class TestBuildChaptersHtml:
    def test_chapter_id_anchor(self):
        chapters = [_make_chapter(1, "Intro")]
        result = _build_chapters_html(chapters)
        assert 'id="ch-1"' in result

    def test_chapter_title_in_output(self):
        chapters = [_make_chapter(1, "The Beginning")]
        result = _build_chapters_html(chapters)
        assert "The Beginning" in result

    def test_chapter_content_rendered(self):
        chapters = [_make_chapter(1, "Intro", content="Once upon a time.")]
        result = _build_chapters_html(chapters)
        assert "Once upon a time." in result

    def test_empty_content_shows_placeholder(self):
        ch = Chapter(chapter_number=1, title="Empty", content="")
        result = _build_chapters_html([ch])
        assert "Chua co noi dung" in result

    def test_multiple_chapters_all_rendered(self):
        chapters = [_make_chapter(1, "Ch1"), _make_chapter(2, "Ch2")]
        result = _build_chapters_html(chapters)
        assert 'id="ch-1"' in result
        assert 'id="ch-2"' in result

    def test_chapter_article_class(self):
        chapters = [_make_chapter(1)]
        result = _build_chapters_html(chapters)
        assert 'class="chapter"' in result


# ---------------------------------------------------------------------------
# HTMLExporter.export
# ---------------------------------------------------------------------------

class TestHTMLExporter:
    def test_export_story_draft_creates_file(self, tmp_path):
        story = _make_story_draft()
        output_path = str(tmp_path / "story.html")
        result_path = HTMLExporter.export(story, output_path)
        assert result_path == output_path
        assert os.path.exists(output_path)

    def test_export_enhanced_story_creates_file(self, tmp_path):
        story = _make_enhanced_story()
        output_path = str(tmp_path / "enhanced.html")
        HTMLExporter.export(story, output_path)
        assert os.path.exists(output_path)

    def test_exported_html_contains_title(self, tmp_path):
        story = _make_story_draft(title="My Epic Tale")
        output_path = str(tmp_path / "out.html")
        HTMLExporter.export(story, output_path)
        content = open(output_path, encoding="utf-8").read()
        assert "My Epic Tale" in content

    def test_exported_html_contains_genre(self, tmp_path):
        story = _make_story_draft(genre="tien_hiep")
        output_path = str(tmp_path / "out.html")
        HTMLExporter.export(story, output_path)
        content = open(output_path, encoding="utf-8").read()
        assert "tien_hiep" in content

    def test_exported_html_is_valid_html_structure(self, tmp_path):
        story = _make_story_draft()
        output_path = str(tmp_path / "out.html")
        HTMLExporter.export(story, output_path)
        content = open(output_path, encoding="utf-8").read()
        assert "<!DOCTYPE html>" in content
        assert "<html" in content
        assert "</html>" in content

    def test_enhanced_story_includes_drama_badge(self, tmp_path):
        story = _make_enhanced_story(drama_score=0.85)
        output_path = str(tmp_path / "out.html")
        HTMLExporter.export(story, output_path)
        content = open(output_path, encoding="utf-8").read()
        assert "0.9" in content or "Kich tinh" in content

    def test_enhanced_story_zero_drama_no_badge(self, tmp_path):
        story = _make_enhanced_story(drama_score=0.0)
        output_path = str(tmp_path / "out.html")
        HTMLExporter.export(story, output_path)
        content = open(output_path, encoding="utf-8").read()
        assert "Kich tinh" not in content

    def test_explicit_characters_override_story_characters(self, tmp_path):
        story = _make_story_draft(characters=[_make_character("InStory")])
        extra_char = _make_character("Explicit")
        output_path = str(tmp_path / "out.html")
        HTMLExporter.export(story, output_path, characters=[extra_char])
        content = open(output_path, encoding="utf-8").read()
        assert "Explicit" in content

    def test_synopsis_rendered_when_present(self, tmp_path):
        story = _make_story_draft()
        output_path = str(tmp_path / "out.html")
        HTMLExporter.export(story, output_path)
        content = open(output_path, encoding="utf-8").read()
        assert "A great story" in content

    def test_share_id_injects_meta_tags(self, tmp_path):
        story = _make_story_draft()
        output_path = str(tmp_path / "share.html")
        HTMLExporter.export(story, output_path, share_id="abc123")
        content = open(output_path, encoding="utf-8").read()
        assert "storyforge-share" in content
        assert "abc123" in content

    def test_no_share_id_no_share_meta(self, tmp_path):
        story = _make_story_draft()
        output_path = str(tmp_path / "out.html")
        HTMLExporter.export(story, output_path)
        content = open(output_path, encoding="utf-8").read()
        assert "storyforge-share" not in content

    def test_output_creates_parent_dirs(self, tmp_path):
        story = _make_story_draft()
        output_path = str(tmp_path / "deep" / "nested" / "story.html")
        HTMLExporter.export(story, output_path)
        assert os.path.exists(output_path)

    def test_xss_in_title_escaped(self, tmp_path):
        story = _make_story_draft(title="<script>alert(1)</script>")
        output_path = str(tmp_path / "out.html")
        HTMLExporter.export(story, output_path)
        content = open(output_path, encoding="utf-8").read()
        assert "<script>alert(1)</script>" not in content
        assert "&lt;script&gt;" in content

    def test_chapter_nav_present_in_output(self, tmp_path):
        chapters = [_make_chapter(1, "Ch1"), _make_chapter(2, "Ch2")]
        story = _make_story_draft(chapters=chapters)
        output_path = str(tmp_path / "out.html")
        HTMLExporter.export(story, output_path)
        content = open(output_path, encoding="utf-8").read()
        assert 'href="#ch-1"' in content
        assert 'href="#ch-2"' in content

    def test_character_cards_in_output(self, tmp_path):
        chars = [_make_character("Hero"), _make_character("Villain")]
        story = _make_story_draft(characters=chars)
        output_path = str(tmp_path / "out.html")
        HTMLExporter.export(story, output_path)
        content = open(output_path, encoding="utf-8").read()
        assert "Hero" in content
        assert "Villain" in content

    def test_returns_output_path(self, tmp_path):
        story = _make_story_draft()
        output_path = str(tmp_path / "out.html")
        returned = HTMLExporter.export(story, output_path)
        assert returned == output_path

    def test_dark_light_mode_toggle_js_present(self, tmp_path):
        story = _make_story_draft()
        output_path = str(tmp_path / "out.html")
        HTMLExporter.export(story, output_path)
        content = open(output_path, encoding="utf-8").read()
        assert "toggleTheme" in content

    def test_nav_sidebar_present(self, tmp_path):
        story = _make_story_draft()
        output_path = str(tmp_path / "out.html")
        HTMLExporter.export(story, output_path)
        content = open(output_path, encoding="utf-8").read()
        assert "nav-sidebar" in content

    def test_utf8_content_preserved(self, tmp_path):
        chapters = [_make_chapter(1, "Khởi Đầu", content="Thế giới tu tiên huyền bí.")]
        story = _make_story_draft(chapters=chapters)
        output_path = str(tmp_path / "utf8.html")
        HTMLExporter.export(story, output_path)
        content = open(output_path, encoding="utf-8").read()
        assert "Thế giới" in content
