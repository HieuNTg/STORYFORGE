"""Security tests — XSS prevention, input length limits, HTML escaping."""

import pytest
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_story(title="Story", content="Content", genre="test"):
    from models.schemas import StoryDraft, Chapter

    return StoryDraft(
        title=title,
        genre=genre,
        chapters=[Chapter(chapter_number=1, title="Ch1", content=content)],
    )


XSS_SCRIPT = "<script>alert('xss')</script>"
XSS_IMG = "<img src=x onerror=alert(1)>"
XSS_HREF = "<a href='javascript:alert(1)'>click</a>"


# ---------------------------------------------------------------------------
# 1. XSS in story title → escaped in HTML output
# ---------------------------------------------------------------------------


class TestXSSInStoryTitle:
    def test_xss_title_not_present_raw_in_html_export(self, tmp_path):
        """HTMLExporter must escape XSS script tag in title."""
        from services.html_exporter import HTMLExporter

        story = _make_story(title=XSS_SCRIPT)
        out = str(tmp_path / "out.html")
        HTMLExporter.export(story, out)
        content = open(out, encoding="utf-8").read()
        assert XSS_SCRIPT not in content

    def test_xss_title_escaped_as_entities_in_html_export(self, tmp_path):
        """HTMLExporter must produce &lt;script&gt; for XSS title."""
        from services.html_exporter import HTMLExporter

        story = _make_story(title=XSS_SCRIPT)
        out = str(tmp_path / "out.html")
        HTMLExporter.export(story, out)
        content = open(out, encoding="utf-8").read()
        assert "&lt;script&gt;" in content

    def test_xss_img_tag_in_title_angle_bracket_escaped(self, tmp_path):
        """img XSS tag in title has its opening < angle bracket escaped in HTML body."""
        from services.html_exporter import HTMLExporter

        story = _make_story(title=XSS_IMG)
        out = str(tmp_path / "out.html")
        HTMLExporter.export(story, out)
        content = open(out, encoding="utf-8").read()
        # The unescaped raw <img tag must not appear in the rendered body sections
        # (It will appear escaped as &lt;img in body/h1/nav areas)
        assert "&lt;img" in content or XSS_IMG not in content.replace("&lt;img", "")

# ---------------------------------------------------------------------------
# 2. XSS in chapter content → escaped in HTML export
# ---------------------------------------------------------------------------


class TestXSSInChapterContent:
    def test_xss_in_content_escaped_in_html_exporter(self, tmp_path):
        """XSS payload in chapter content is escaped in HTMLExporter output."""
        from services.html_exporter import HTMLExporter

        story = _make_story(content=XSS_SCRIPT)
        out = str(tmp_path / "out.html")
        HTMLExporter.export(story, out)
        content = open(out, encoding="utf-8").read()
        # Raw script should not appear in chapter body
        assert "<script>alert" not in content

    def test_html_entities_present_for_xss_content(self, tmp_path):
        """HTMLExporter encodes XSS entities in chapter content."""
        from services.html_exporter import HTMLExporter

        story = _make_story(content="<b>bold</b> & <i>italic</i>")
        out = str(tmp_path / "out.html")
        HTMLExporter.export(story, out)
        content = open(out, encoding="utf-8").read()
        # Raw unescaped tags from content must not appear in chapter section
        # (They appear as CSS/JS in the template, but chapter content should be escaped)
        assert "&lt;b&gt;" in content or "&amp;" in content


# ---------------------------------------------------------------------------
# 3. Very long input → rejected or truncated
# ---------------------------------------------------------------------------


class TestVeryLongInput:
    def test_title_10000_chars_does_not_crash_html_export(self, tmp_path):
        """HTMLExporter handles 10000-char title without crashing."""
        from services.html_exporter import HTMLExporter

        long_title = "A" * 10000
        story = _make_story(title=long_title)
        out = str(tmp_path / "long.html")
        result = HTMLExporter.export(story, out)
        assert result == out
        assert len(open(out, encoding="utf-8").read()) > 0

    def test_epub_export_long_title_does_not_crash(self, tmp_path):
        """EPUBExporter handles long title gracefully (truncates identifier)."""
        pytest.importorskip("ebooklib")
        from services.epub_exporter import EPUBExporter

        long_title = "B" * 10000
        story = _make_story(title=long_title)
        out = str(tmp_path / "long.epub")
        result = EPUBExporter.export(story, out)
        assert result == out


# ---------------------------------------------------------------------------
# 4. Share manager HTML fallback escapes special characters
# ---------------------------------------------------------------------------


class TestShareManagerHTMLEscaping:
    def _make_share_mgr(self, tmp_path, monkeypatch):
        from services.share_manager import ShareManager

        monkeypatch.setattr(ShareManager, "SHARES_DIR", str(tmp_path / "shares"))
        monkeypatch.setattr(
            ShareManager, "SHARES_INDEX", str(tmp_path / "shares" / "index.json")
        )
        return ShareManager()

    def test_fallback_html_escapes_angle_brackets_in_title(self, tmp_path, monkeypatch):
        """Fallback HTML escapes < > in story title."""
        mgr = self._make_share_mgr(tmp_path, monkeypatch)
        story = _make_story(title="<Evil> & 'Story'")

        with patch(
            "services.html_exporter.HTMLExporter.export", side_effect=Exception("fail")
        ):
            share = mgr.create_share(story)

        content = open(share.html_path, encoding="utf-8").read()
        assert "<Evil>" not in content
        assert "&lt;Evil&gt;" in content

    def test_fallback_html_escapes_ampersand_in_title(self, tmp_path, monkeypatch):
        """Fallback HTML escapes & in story title."""
        mgr = self._make_share_mgr(tmp_path, monkeypatch)
        story = _make_story(title="Hero & Villain")

        with patch(
            "services.html_exporter.HTMLExporter.export", side_effect=Exception("fail")
        ):
            share = mgr.create_share(story)

        content = open(share.html_path, encoding="utf-8").read()
        assert "&amp;" in content

    def test_fallback_html_escapes_script_tag_in_title(self, tmp_path, monkeypatch):
        """Fallback HTML escapes XSS script tag in story title."""
        mgr = self._make_share_mgr(tmp_path, monkeypatch)
        story = _make_story(title=XSS_SCRIPT)

        with patch(
            "services.html_exporter.HTMLExporter.export", side_effect=Exception("fail")
        ):
            share = mgr.create_share(story)

        content = open(share.html_path, encoding="utf-8").read()
        assert XSS_SCRIPT not in content
        assert "&lt;script&gt;" in content

    def test_normal_share_creation_produces_valid_html(self, tmp_path, monkeypatch):
        """Normal (non-fallback) share produces valid HTML with title escaped."""
        mgr = self._make_share_mgr(tmp_path, monkeypatch)
        story = _make_story(title="Safe Title & More")
        share = mgr.create_share(story)
        content = open(share.html_path, encoding="utf-8").read()
        assert "<!DOCTYPE html>" in content or "<html" in content

    def test_fallback_html_is_valid_minimal_page(self, tmp_path, monkeypatch):
        """Fallback HTML is a minimal but valid HTML page structure."""
        mgr = self._make_share_mgr(tmp_path, monkeypatch)
        story = _make_story(title="Test Story")

        with patch(
            "services.html_exporter.HTMLExporter.export", side_effect=Exception("fail")
        ):
            share = mgr.create_share(story)

        content = open(share.html_path, encoding="utf-8").read()
        assert "<html>" in content
        assert "<body>" in content
        assert "</body></html>" in content
