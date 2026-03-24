"""Tests for EPUBExporter service."""
import importlib
import os
import sys
import pytest
from unittest.mock import MagicMock, patch
from models.schemas import StoryDraft, EnhancedStory, Character, Chapter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_epub_mocks():
    """Return (ebooklib_mock, epub_mod, book) with a fully wired mock hierarchy."""
    epub_mod = MagicMock()
    book = MagicMock()
    epub_mod.EpubBook.return_value = book

    # CSS item
    css_item = MagicMock()
    css_item.file_name = "style/default.css"
    epub_mod.EpubItem.return_value = css_item

    # EpubHtml pages – fresh mock per call, with settable .content
    def make_html(**kwargs):
        page = MagicMock()
        page.file_name = kwargs.get("file_name", "page.xhtml")
        page.title = kwargs.get("title", "")
        # allow content assignment without error
        page.content = b""
        return page

    epub_mod.EpubHtml.side_effect = make_html

    # Link, Nav, Ncx
    epub_mod.Link.side_effect = lambda fn, t, uid: MagicMock(file_name=fn, title=t)
    epub_mod.EpubNcx.return_value = MagicMock()
    epub_mod.EpubNav.return_value = MagicMock()

    epub_mod.write_epub = MagicMock()

    # The module-level mock: 'from ebooklib import epub' resolves to epub_mod
    ebooklib_mock = MagicMock()
    ebooklib_mock.epub = epub_mod

    return ebooklib_mock, epub_mod, book


def _get_exporter(ebooklib_mock):
    """Reload EPUBExporter with mocked ebooklib, return the class."""
    with patch.dict(sys.modules, {"ebooklib": ebooklib_mock}):
        import services.epub_exporter
        importlib.reload(services.epub_exporter)
        return services.epub_exporter.EPUBExporter


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def single_chapter_story():
    return StoryDraft(
        title="Single Chapter",
        genre="romance",
        synopsis="A short love story.",
        chapters=[
            Chapter(
                chapter_number=1,
                title="Chuong Duy Nhat",
                content="Day la noi dung duy nhat cua chuong nay.",
                summary="Chuong cuoi",
            )
        ],
    )


@pytest.fixture
def multi_chapter_story():
    chapters = [
        Chapter(
            chapter_number=i,
            title=f"Chuong {i}",
            content=f"Noi dung chuong {i}.",
            summary=f"Tom tat {i}",
        )
        for i in range(1, 6)
    ]
    return StoryDraft(
        title="Multi Chapter Story",
        genre="fantasy",
        synopsis="Epic fantasy.",
        chapters=chapters,
    )


# ---------------------------------------------------------------------------
# Tests: _get_css (no mocking needed)
# ---------------------------------------------------------------------------

class TestGetCss:
    def test_returns_string(self):
        from services.epub_exporter import EPUBExporter
        css = EPUBExporter._get_css()
        assert isinstance(css, str)

    def test_contains_font_family(self):
        from services.epub_exporter import EPUBExporter
        assert "font-family" in EPUBExporter._get_css()

    def test_contains_line_height(self):
        from services.epub_exporter import EPUBExporter
        assert "line-height" in EPUBExporter._get_css()

    def test_contains_title_page_class(self):
        from services.epub_exporter import EPUBExporter
        assert ".title-page" in EPUBExporter._get_css()

    def test_contains_character_class(self):
        from services.epub_exporter import EPUBExporter
        assert ".character" in EPUBExporter._get_css()

    def test_nonempty(self):
        from services.epub_exporter import EPUBExporter
        assert len(EPUBExporter._get_css()) > 50


# ---------------------------------------------------------------------------
# Tests: ImportError fallback
# ---------------------------------------------------------------------------

class TestImportFallback:
    def test_returns_empty_string_when_ebooklib_missing(self, sample_story_draft, tmp_path):
        out = str(tmp_path / "story.epub")
        # patch ebooklib import to raise ImportError
        with patch.dict(sys.modules, {"ebooklib": None}):
            import services.epub_exporter
            importlib.reload(services.epub_exporter)
            EPUBExporter = services.epub_exporter.EPUBExporter
            result = EPUBExporter.export(sample_story_draft, out)
        assert result == ""

    def test_no_file_created_when_import_fails(self, sample_story_draft, tmp_path):
        out = str(tmp_path / "story.epub")
        with patch.dict(sys.modules, {"ebooklib": None}):
            import services.epub_exporter
            importlib.reload(services.epub_exporter)
            EPUBExporter = services.epub_exporter.EPUBExporter
            EPUBExporter.export(sample_story_draft, out)
        assert not os.path.exists(out)


# ---------------------------------------------------------------------------
# Tests: export() — write_epub called
# ---------------------------------------------------------------------------

class TestExportWriteEpub:
    def test_returns_output_path(self, sample_story_draft, tmp_path):
        ebooklib_mock, epub_mod, _ = _make_epub_mocks()
        EPUBExporter = _get_exporter(ebooklib_mock)
        out = str(tmp_path / "story.epub")
        with patch.dict(sys.modules, {"ebooklib": ebooklib_mock}):
            result = EPUBExporter.export(sample_story_draft, out)
        assert result == out

    def test_write_epub_called_once(self, sample_story_draft, tmp_path):
        ebooklib_mock, epub_mod, _ = _make_epub_mocks()
        EPUBExporter = _get_exporter(ebooklib_mock)
        out = str(tmp_path / "story.epub")
        with patch.dict(sys.modules, {"ebooklib": ebooklib_mock}):
            EPUBExporter.export(sample_story_draft, out)
        epub_mod.write_epub.assert_called_once()

    def test_write_epub_receives_output_path(self, sample_story_draft, tmp_path):
        ebooklib_mock, epub_mod, _ = _make_epub_mocks()
        EPUBExporter = _get_exporter(ebooklib_mock)
        out = str(tmp_path / "story.epub")
        with patch.dict(sys.modules, {"ebooklib": ebooklib_mock}):
            EPUBExporter.export(sample_story_draft, out)
        args = epub_mod.write_epub.call_args[0]
        assert args[0] == out

    def test_write_epub_receives_book_object(self, sample_story_draft, tmp_path):
        ebooklib_mock, epub_mod, book = _make_epub_mocks()
        EPUBExporter = _get_exporter(ebooklib_mock)
        out = str(tmp_path / "story.epub")
        with patch.dict(sys.modules, {"ebooklib": ebooklib_mock}):
            EPUBExporter.export(sample_story_draft, out)
        args = epub_mod.write_epub.call_args[0]
        assert args[1] is book


# ---------------------------------------------------------------------------
# Tests: export() with characters
# ---------------------------------------------------------------------------

class TestExportWithCharacters:
    def test_returns_output_path(self, sample_story_draft, sample_characters, tmp_path):
        ebooklib_mock, epub_mod, _ = _make_epub_mocks()
        EPUBExporter = _get_exporter(ebooklib_mock)
        out = str(tmp_path / "story.epub")
        with patch.dict(sys.modules, {"ebooklib": ebooklib_mock}):
            result = EPUBExporter.export(sample_story_draft, out, characters=sample_characters)
        assert result == out

    def test_characters_xhtml_created(self, sample_story_draft, sample_characters, tmp_path):
        ebooklib_mock, epub_mod, _ = _make_epub_mocks()
        EPUBExporter = _get_exporter(ebooklib_mock)
        out = str(tmp_path / "story.epub")
        with patch.dict(sys.modules, {"ebooklib": ebooklib_mock}):
            EPUBExporter.export(sample_story_draft, out, characters=sample_characters)
        file_names = [c.kwargs.get("file_name", "") for c in epub_mod.EpubHtml.call_args_list]
        assert "characters.xhtml" in file_names

    def test_spine_assigned(self, sample_story_draft, sample_characters, tmp_path):
        ebooklib_mock, epub_mod, book = _make_epub_mocks()
        EPUBExporter = _get_exporter(ebooklib_mock)
        out = str(tmp_path / "story.epub")
        with patch.dict(sys.modules, {"ebooklib": ebooklib_mock}):
            EPUBExporter.export(sample_story_draft, out, characters=sample_characters)
        assert book.spine is not None


# ---------------------------------------------------------------------------
# Tests: export() without characters
# ---------------------------------------------------------------------------

class TestExportWithoutCharacters:
    def test_returns_output_path(self, sample_story_draft, tmp_path):
        ebooklib_mock, epub_mod, _ = _make_epub_mocks()
        EPUBExporter = _get_exporter(ebooklib_mock)
        out = str(tmp_path / "story.epub")
        with patch.dict(sys.modules, {"ebooklib": ebooklib_mock}):
            result = EPUBExporter.export(sample_story_draft, out, characters=None)
        assert result == out

    def test_no_characters_xhtml(self, sample_story_draft, tmp_path):
        ebooklib_mock, epub_mod, _ = _make_epub_mocks()
        EPUBExporter = _get_exporter(ebooklib_mock)
        out = str(tmp_path / "story.epub")
        with patch.dict(sys.modules, {"ebooklib": ebooklib_mock}):
            EPUBExporter.export(sample_story_draft, out, characters=None)
        file_names = [c.kwargs.get("file_name", "") for c in epub_mod.EpubHtml.call_args_list]
        assert "characters.xhtml" not in file_names

    def test_write_epub_still_called(self, sample_story_draft, tmp_path):
        ebooklib_mock, epub_mod, _ = _make_epub_mocks()
        EPUBExporter = _get_exporter(ebooklib_mock)
        out = str(tmp_path / "story.epub")
        with patch.dict(sys.modules, {"ebooklib": ebooklib_mock}):
            EPUBExporter.export(sample_story_draft, out)
        epub_mod.write_epub.assert_called_once()


# ---------------------------------------------------------------------------
# Tests: metadata
# ---------------------------------------------------------------------------

class TestMetadata:
    def test_title_set(self, sample_story_draft, tmp_path):
        ebooklib_mock, epub_mod, book = _make_epub_mocks()
        EPUBExporter = _get_exporter(ebooklib_mock)
        out = str(tmp_path / "story.epub")
        with patch.dict(sys.modules, {"ebooklib": ebooklib_mock}):
            EPUBExporter.export(sample_story_draft, out)
        book.set_title.assert_called_once_with(sample_story_draft.title)

    def test_language_default_vi(self, sample_story_draft, tmp_path):
        ebooklib_mock, epub_mod, book = _make_epub_mocks()
        EPUBExporter = _get_exporter(ebooklib_mock)
        out = str(tmp_path / "story.epub")
        with patch.dict(sys.modules, {"ebooklib": ebooklib_mock}):
            EPUBExporter.export(sample_story_draft, out)
        book.set_language.assert_called_once_with("vi")

    def test_language_override(self, sample_story_draft, tmp_path):
        ebooklib_mock, epub_mod, book = _make_epub_mocks()
        EPUBExporter = _get_exporter(ebooklib_mock)
        out = str(tmp_path / "story.epub")
        with patch.dict(sys.modules, {"ebooklib": ebooklib_mock}):
            EPUBExporter.export(sample_story_draft, out, language="en")
        book.set_language.assert_called_once_with("en")

    def test_author_set(self, sample_story_draft, tmp_path):
        ebooklib_mock, epub_mod, book = _make_epub_mocks()
        EPUBExporter = _get_exporter(ebooklib_mock)
        out = str(tmp_path / "story.epub")
        with patch.dict(sys.modules, {"ebooklib": ebooklib_mock}):
            EPUBExporter.export(sample_story_draft, out, author="Test Author")
        book.add_author.assert_called_once_with("Test Author")

    def test_genre_metadata_added(self, sample_story_draft, tmp_path):
        ebooklib_mock, epub_mod, book = _make_epub_mocks()
        EPUBExporter = _get_exporter(ebooklib_mock)
        out = str(tmp_path / "story.epub")
        with patch.dict(sys.modules, {"ebooklib": ebooklib_mock}):
            EPUBExporter.export(sample_story_draft, out)
        book.add_metadata.assert_called_with("DC", "subject", sample_story_draft.genre)

    def test_identifier_contains_storyforge(self, sample_story_draft, tmp_path):
        ebooklib_mock, epub_mod, book = _make_epub_mocks()
        EPUBExporter = _get_exporter(ebooklib_mock)
        out = str(tmp_path / "story.epub")
        with patch.dict(sys.modules, {"ebooklib": ebooklib_mock}):
            EPUBExporter.export(sample_story_draft, out)
        book.set_identifier.assert_called_once()
        id_arg = book.set_identifier.call_args[0][0]
        assert "storyforge" in id_arg


# ---------------------------------------------------------------------------
# Tests: multiple chapters → multiple xhtml files
# ---------------------------------------------------------------------------

class TestMultipleChapters:
    def test_each_chapter_gets_xhtml(self, multi_chapter_story, tmp_path):
        ebooklib_mock, epub_mod, _ = _make_epub_mocks()
        EPUBExporter = _get_exporter(ebooklib_mock)
        out = str(tmp_path / "story.epub")
        with patch.dict(sys.modules, {"ebooklib": ebooklib_mock}):
            EPUBExporter.export(multi_chapter_story, out)
        file_names = [c.kwargs.get("file_name", "") for c in epub_mod.EpubHtml.call_args_list]
        chapter_files = [f for f in file_names if f.startswith("chapter_")]
        assert len(chapter_files) == 5

    def test_chapter_filenames_zero_padded(self, multi_chapter_story, tmp_path):
        ebooklib_mock, epub_mod, _ = _make_epub_mocks()
        EPUBExporter = _get_exporter(ebooklib_mock)
        out = str(tmp_path / "story.epub")
        with patch.dict(sys.modules, {"ebooklib": ebooklib_mock}):
            EPUBExporter.export(multi_chapter_story, out)
        file_names = [c.kwargs.get("file_name", "") for c in epub_mod.EpubHtml.call_args_list]
        chapter_files = sorted(f for f in file_names if f.startswith("chapter_"))
        assert chapter_files[0] == "chapter_001.xhtml"
        assert chapter_files[4] == "chapter_005.xhtml"

    def test_single_chapter_story(self, single_chapter_story, tmp_path):
        ebooklib_mock, epub_mod, _ = _make_epub_mocks()
        EPUBExporter = _get_exporter(ebooklib_mock)
        out = str(tmp_path / "story.epub")
        with patch.dict(sys.modules, {"ebooklib": ebooklib_mock}):
            result = EPUBExporter.export(single_chapter_story, out)
        assert result == out
        file_names = [c.kwargs.get("file_name", "") for c in epub_mod.EpubHtml.call_args_list]
        chapter_files = [f for f in file_names if f.startswith("chapter_")]
        assert len(chapter_files) == 1

    def test_title_page_always_created(self, single_chapter_story, tmp_path):
        ebooklib_mock, epub_mod, _ = _make_epub_mocks()
        EPUBExporter = _get_exporter(ebooklib_mock)
        out = str(tmp_path / "story.epub")
        with patch.dict(sys.modules, {"ebooklib": ebooklib_mock}):
            EPUBExporter.export(single_chapter_story, out)
        file_names = [c.kwargs.get("file_name", "") for c in epub_mod.EpubHtml.call_args_list]
        assert "title.xhtml" in file_names


# ---------------------------------------------------------------------------
# Tests: output directory creation
# ---------------------------------------------------------------------------

class TestOutputPath:
    def test_creates_nested_output_dir(self, sample_story_draft, tmp_path):
        ebooklib_mock, epub_mod, _ = _make_epub_mocks()
        EPUBExporter = _get_exporter(ebooklib_mock)
        nested = str(tmp_path / "a" / "b" / "c" / "out.epub")
        with patch.dict(sys.modules, {"ebooklib": ebooklib_mock}):
            result = EPUBExporter.export(sample_story_draft, nested)
        assert result == nested
        assert os.path.isdir(str(tmp_path / "a" / "b" / "c"))

    def test_enhanced_story_export(self, sample_enhanced_story, tmp_path):
        ebooklib_mock, epub_mod, _ = _make_epub_mocks()
        EPUBExporter = _get_exporter(ebooklib_mock)
        out = str(tmp_path / "enhanced.epub")
        with patch.dict(sys.modules, {"ebooklib": ebooklib_mock}):
            result = EPUBExporter.export(sample_enhanced_story, out)
        assert result == out

    def test_story_no_synopsis(self, tmp_path):
        ebooklib_mock, epub_mod, _ = _make_epub_mocks()
        EPUBExporter = _get_exporter(ebooklib_mock)
        story = StoryDraft(
            title="No Synopsis",
            genre="action",
            chapters=[Chapter(chapter_number=1, title="Ch1", content="Content.")],
        )
        out = str(tmp_path / "nosyn.epub")
        with patch.dict(sys.modules, {"ebooklib": ebooklib_mock}):
            result = EPUBExporter.export(story, out)
        assert result == out
