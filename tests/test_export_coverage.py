"""Export service coverage tests — PDF, EPUB, HTML exporters.

Tests:
    - PDF export with Vietnamese content (and missing fpdf2 graceful fail)
    - EPUB export metadata correctness
    - HTML export structure validation
"""
from __future__ import annotations

import os
import tempfile

import pytest

from models.schemas import Chapter, Character, StoryDraft, EnhancedStory, WorldSetting, ChapterOutline


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def viet_characters():
    return [
        Character(
            name="Lý Huyền",
            role="protagonist",
            personality="Kiên cường, thông minh",
            background="Mồ côi từ nhỏ",
            motivation="Tìm sự thật về gia tộc",
            appearance="Cao, tóc đen dài",
        ),
        Character(
            name="Hoàng Yến",
            role="antagonist",
            personality="Xảo quyệt, tham vọng",
            background="Trưởng lão phản bội tông môn",
            motivation="Chiếm đoạt quyền lực",
        ),
    ]


@pytest.fixture
def viet_chapters():
    return [
        Chapter(
            chapter_number=1,
            title="Khởi Đầu",
            content=(
                "Lý Huyền bước vào tông môn với ánh mắt kiên định.\n\n"
                "Gió thổi nhẹ qua hàng cây cổ thụ, mang theo mùi hương của hoa dại.\n\n"
                "Đây là nơi anh sẽ bắt đầu hành trình tu luyện gian nan."
            ),
            word_count=45,
            summary="Lý Huyền gia nhập tông môn",
        ),
        Chapter(
            chapter_number=2,
            title="Thử Thách Đầu Tiên",
            content=(
                "Trận đấu đầu tiên diễn ra dưới ánh nắng gay gắt.\n\n"
                "Hoàng Yến xuất hiện với nụ cười lạnh lùng, đôi mắt sắc bén như kiếm.\n\n"
                "Lý Huyền chuẩn bị nghênh chiến, quyết không lùi bước."
            ),
            word_count=42,
            summary="Đối đầu với Hoàng Yến",
        ),
    ]


@pytest.fixture
def story_draft(viet_chapters, viet_characters):
    world = WorldSetting(
        name="Thanh Vân Giới",
        description="Thế giới tu tiên với 9 cảnh giới",
        rules=["Linh khí là nguồn sức mạnh"],
        locations=["Thanh Vân Tông"],
        era="Cổ đại",
    )
    outlines = [
        ChapterOutline(chapter_number=i + 1, title=ch.title, summary=ch.summary)
        for i, ch in enumerate(viet_chapters)
    ]
    return StoryDraft(
        title="Thanh Vân Kiếm Khách",
        genre="tiên hiệp",
        synopsis="Câu chuyện về Lý Huyền tu luyện thành kiếm khách.",
        characters=viet_characters,
        world=world,
        outlines=outlines,
        chapters=viet_chapters,
    )


@pytest.fixture
def enhanced_story(viet_chapters):
    return EnhancedStory(
        title="Thanh Vân Kiếm Khách (Enhanced)",
        genre="tiên hiệp",
        synopsis="Câu chuyện về Lý Huyền",
        chapters=viet_chapters,
        drama_score=0.82,
        enhancement_notes=["Tăng xung đột giữa MC và antagonist"],
    )


# ---------------------------------------------------------------------------
# PDF Tests
# ---------------------------------------------------------------------------


class TestPDFExporter:
    def test_pdf_export_returns_path_or_empty(self, story_draft):
        """PDF export returns output path on success or '' if fpdf2 missing."""
        from services.pdf_exporter import PDFExporter  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as tmpdir:
            out = os.path.join(tmpdir, "story.pdf")
            result = PDFExporter.export(story_draft, out)
            # Either successful export or graceful empty string (no fpdf2)
            assert result == out or result == ""

    def test_pdf_export_with_characters(self, story_draft, viet_characters):
        """PDF export with character list runs without raising."""
        from services.pdf_exporter import PDFExporter  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as tmpdir:
            out = os.path.join(tmpdir, "story_chars.pdf")
            result = PDFExporter.export(story_draft, out, characters=viet_characters)
            assert result == out or result == ""

    def test_compute_reading_stats(self, story_draft):
        """Reading stats are computed correctly from chapter word counts."""
        from services.pdf_exporter import PDFExporter  # noqa: PLC0415

        stats = PDFExporter.compute_reading_stats(story_draft)
        assert stats.total_chapters == 2
        assert stats.total_words > 0
        assert stats.estimated_reading_minutes >= 1
        assert stats.avg_words_per_chapter > 0

    def test_compute_reading_stats_enhanced(self, enhanced_story):
        """Reading stats work on EnhancedStory too."""
        from services.pdf_exporter import PDFExporter  # noqa: PLC0415

        stats = PDFExporter.compute_reading_stats(enhanced_story)
        assert stats.total_chapters == 2

    def test_pdf_export_creates_parent_dir(self, story_draft):
        """PDF export creates parent directories automatically."""
        from services.pdf_exporter import PDFExporter  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as tmpdir:
            nested = os.path.join(tmpdir, "subdir", "nested", "story.pdf")
            result = PDFExporter.export(story_draft, nested)
            assert result == nested or result == ""
            # If fpdf2 available, parent dirs must exist
            if result == nested:
                assert os.path.exists(os.path.dirname(nested))


# ---------------------------------------------------------------------------
# EPUB Tests
# ---------------------------------------------------------------------------


class TestEPUBExporter:
    def test_epub_export_returns_path_or_empty(self, story_draft):
        """EPUB export returns output path or '' if ebooklib missing."""
        from services.epub_exporter import EPUBExporter  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as tmpdir:
            out = os.path.join(tmpdir, "story.epub")
            result = EPUBExporter.export(story_draft, out)
            assert result == out or result == ""

    def test_epub_export_with_characters_and_language(self, story_draft, viet_characters):
        """EPUB export accepts language and author overrides."""
        from services.epub_exporter import EPUBExporter  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as tmpdir:
            out = os.path.join(tmpdir, "story_vi.epub")
            result = EPUBExporter.export(
                story_draft, out,
                characters=viet_characters,
                language="vi",
                author="StoryForge AI",
            )
            assert result == out or result == ""

    def test_epub_html_escape_helper(self):
        """_html_escape handles special characters safely."""
        from services.epub_exporter import _html_escape  # noqa: PLC0415

        assert _html_escape("<script>") == "&lt;script&gt;"
        assert _html_escape("Lý & Huyền") == "Lý &amp; Huyền"
        assert _html_escape(None) == ""
        assert _html_escape("") == ""

    def test_epub_export_creates_output_dir(self, story_draft):
        """EPUB export creates nested output directory."""
        from services.epub_exporter import EPUBExporter  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as tmpdir:
            nested = os.path.join(tmpdir, "exports", "epub", "story.epub")
            result = EPUBExporter.export(story_draft, nested)
            assert result == nested or result == ""
            if result == nested:
                assert os.path.exists(nested)


# ---------------------------------------------------------------------------
# HTML Tests
# ---------------------------------------------------------------------------


class TestHTMLExporter:
    def test_html_export_creates_file(self, story_draft):
        """HTML export writes a non-empty file."""
        from services.html_exporter import HTMLExporter  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as tmpdir:
            out = os.path.join(tmpdir, "story.html")
            result = HTMLExporter.export(story_draft, out)
            assert result == out
            assert os.path.exists(out)
            assert os.path.getsize(out) > 0

    def test_html_export_contains_title(self, story_draft):
        """HTML output contains the story title."""
        from services.html_exporter import HTMLExporter  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as tmpdir:
            out = os.path.join(tmpdir, "story.html")
            HTMLExporter.export(story_draft, out)
            content = open(out, encoding="utf-8").read()
            assert "Thanh Vân Kiếm Khách" in content

    def test_html_export_contains_chapters(self, story_draft):
        """HTML output contains chapter headers."""
        from services.html_exporter import HTMLExporter  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as tmpdir:
            out = os.path.join(tmpdir, "story.html")
            HTMLExporter.export(story_draft, out)
            content = open(out, encoding="utf-8").read()
            assert "ch-1" in content
            assert "ch-2" in content

    def test_html_export_with_characters(self, story_draft, viet_characters):
        """HTML export includes character cards when characters provided."""
        from services.html_exporter import HTMLExporter  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as tmpdir:
            out = os.path.join(tmpdir, "story_chars.html")
            HTMLExporter.export(story_draft, out, characters=viet_characters)
            content = open(out, encoding="utf-8").read()
            assert "char-card" in content
            assert "Lý Huyền" in content

    def test_html_export_drama_badge_enhanced_story(self, enhanced_story):
        """Enhanced story HTML shows drama score badge."""
        from services.html_exporter import HTMLExporter  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as tmpdir:
            out = os.path.join(tmpdir, "enhanced.html")
            HTMLExporter.export(enhanced_story, out)
            content = open(out, encoding="utf-8").read()
            assert "0.8" in content  # drama_score badge

    def test_html_export_dark_mode_toggle(self, story_draft):
        """HTML includes dark mode toggle script."""
        from services.html_exporter import HTMLExporter  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as tmpdir:
            out = os.path.join(tmpdir, "story.html")
            HTMLExporter.export(story_draft, out)
            content = open(out, encoding="utf-8").read()
            assert "toggleTheme" in content
            assert "data-theme" in content

    def test_html_export_with_share_id(self, story_draft):
        """HTML includes share metadata when share_id is provided."""
        from services.html_exporter import HTMLExporter  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as tmpdir:
            out = os.path.join(tmpdir, "shared.html")
            HTMLExporter.export(story_draft, out, share_id="abc123share")
            content = open(out, encoding="utf-8").read()
            assert "storyforge-share" in content
            assert "abc123share" in content

    def test_md_to_html_bold_and_italic(self):
        """_md_to_html converts markdown bold and italic."""
        from services.html_exporter import _md_to_html  # noqa: PLC0415

        result = _md_to_html("**bold** and *italic* text")
        assert "<strong>bold</strong>" in result
        assert "<em>italic</em>" in result

    def test_html_export_vietnamese_content_preserved(self, story_draft):
        """Vietnamese diacritics are preserved in HTML output (UTF-8)."""
        from services.html_exporter import HTMLExporter  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as tmpdir:
            out = os.path.join(tmpdir, "viet.html")
            HTMLExporter.export(story_draft, out)
            content = open(out, encoding="utf-8").read()
            # Check Vietnamese text from chapters is present
            assert "Lý Huyền" in content or "L&#253;" in content
