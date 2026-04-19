"""Export story as PDF with book-quality typography and Vietnamese support."""
import logging
import os
from datetime import datetime
from typing import Union
from models.schemas import StoryDraft, EnhancedStory, Character, ReadingStats

logger = logging.getLogger(__name__)

FONT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "fonts")

# Trade paperback feel: A5 (148 x 210 mm). Keeps lines readable (~65 chars).
PAGE_FORMAT = "A5"
MARGIN_L = 18
MARGIN_R = 18
MARGIN_T = 20
MARGIN_B = 18

# Body typography
BODY_SIZE = 11
BODY_LEADING = 5.6           # mm line-height at 11pt
PARA_INDENT = 5.5            # first-line indent (mm)

# Font file names on disk (under services/assets/fonts/)
_FONT_FILES = {
    "regular": "NotoSans-Regular.ttf",
    "bold":    "NotoSans-Bold.ttf",
    "italic":  "NotoSans-Italic.ttf",
}

# Remote source: Google Fonts repository (static files — stable parsing for fpdf2)
_FONT_URLS = {
    "regular": "https://raw.githubusercontent.com/googlefonts/noto-fonts/main/hinted/ttf/NotoSans/NotoSans-Regular.ttf",
    "bold":    "https://raw.githubusercontent.com/googlefonts/noto-fonts/main/hinted/ttf/NotoSans/NotoSans-Bold.ttf",
    "italic":  "https://raw.githubusercontent.com/googlefonts/noto-fonts/main/hinted/ttf/NotoSans/NotoSans-Italic.ttf",
}


class _BookPDF:
    """fpdf2 subclass wrapper — overrides header/footer for book-style running elements.

    Defined inside export() via local class because importing FPDF at module
    load time is optional (fpdf2 may be absent in some deployments).
    """


def _build_pdf_class():
    """Return a FPDF subclass with book-style header/footer. Lazy import fpdf2."""
    from fpdf import FPDF

    class BookPDF(FPDF):
        # Toggled to suppress header/footer on cover/TOC
        show_chrome = False
        book_title = ""

        def header(self):
            # No header — keeps the book clean. Page number is in footer only.
            return

        def footer(self):
            if not self.show_chrome:
                return
            # Page number, centered, small size, muted colour.
            self.set_y(-12)
            try:
                self.set_font("NotoSans", "", 9)
            except Exception:
                self.set_font("Helvetica", "", 9)
            self.set_text_color(130, 130, 130)
            self.cell(0, 6, str(self.page_no()), align="C")
            self.set_text_color(0, 0, 0)

    return BookPDF


class PDFExporter:
    """Export story as PDF with Vietnamese font support and book typography."""

    # ── Public API ────────────────────────────────────────────────────────────

    @staticmethod
    def compute_reading_stats(story: Union[StoryDraft, EnhancedStory]) -> ReadingStats:
        chapters = story.chapters
        total_words = sum(len(ch.content.split()) for ch in chapters)
        total_ch = len(chapters)
        avg_wpc = total_words // max(1, total_ch)
        reading_min = max(1, total_words // 200)  # ~200 words/min
        return ReadingStats(
            total_words=total_words,
            total_chapters=total_ch,
            estimated_reading_minutes=reading_min,
            avg_words_per_chapter=avg_wpc,
        )

    @staticmethod
    def export(
        story: Union[StoryDraft, EnhancedStory],
        output_path: str,
        characters: list[Character] = None,
        font: str = "NotoSans",
    ) -> str:
        """Export story to PDF. Returns path to generated file (empty on failure)."""
        try:
            from fpdf import FPDF  # noqa: F401  (availability check)
        except ImportError:
            logger.error("fpdf2 not installed. Run: pip install fpdf2")
            return ""

        BookPDF = _build_pdf_class()
        pdf = BookPDF(format=PAGE_FORMAT, unit="mm")
        pdf.set_margins(MARGIN_L, MARGIN_T, MARGIN_R)
        pdf.set_auto_page_break(auto=True, margin=MARGIN_B)
        pdf.book_title = story.title or ""
        pdf.set_title(story.title or "StoryForge")
        pdf.set_author("StoryForge")

        font_ok = PDFExporter._register_fonts(pdf)
        family = "NotoSans" if font_ok else "Helvetica"
        if not font_ok:
            logger.warning("Vietnamese fonts not found — falling back to Helvetica (diacritics may be missing)")

        # ── 1. Title page ───────────────────────────────────────────────────
        PDFExporter._render_title_page(pdf, family, story)

        # ── 2. Table of Contents (auto-paginated placeholder) ───────────────
        pdf.add_page()
        pdf.show_chrome = False
        PDFExporter._header_h1(pdf, family, "Mục lục", align="C")
        pdf.ln(6)
        # Pre-size TOC: ~24 entries fit on an A5 page at 7mm line-height.
        _toc_entries = len(story.chapters) + (1 if characters else 0)
        _toc_pages = max(1, (_toc_entries + 23) // 24)
        pdf.insert_toc_placeholder(
            lambda p, outline: PDFExporter._render_toc(p, family, outline, _toc_pages),
            pages=_toc_pages,
        )

        # ── 3. Characters (optional) ────────────────────────────────────────
        if characters:
            pdf.add_page()
            pdf.show_chrome = True
            pdf.start_section("Nhân vật", level=0)
            PDFExporter._header_h1(pdf, family, "Nhân vật", align="L")
            pdf.ln(4)
            for c in characters:
                pdf.set_font(family, "B", 12)
                pdf.multi_cell(0, 6, f"{c.name}", new_x="LMARGIN", new_y="NEXT")
                pdf.set_font(family, "I", 10)
                pdf.set_text_color(90, 90, 90)
                role_line = getattr(c, "role", "") or ""
                if role_line:
                    pdf.multi_cell(0, 5, role_line, new_x="LMARGIN", new_y="NEXT")
                pdf.set_text_color(0, 0, 0)
                pdf.set_font(family, "", 10.5)
                personality = getattr(c, "personality", "") or ""
                if personality:
                    pdf.multi_cell(0, 5.2, personality, new_x="LMARGIN", new_y="NEXT")
                pdf.ln(3)

        # ── 4. Chapters ─────────────────────────────────────────────────────
        for ch in story.chapters:
            PDFExporter._render_chapter(pdf, family, ch)

        # ── 5. Colophon / Stats ─────────────────────────────────────────────
        stats = PDFExporter.compute_reading_stats(story)
        PDFExporter._render_colophon(pdf, family, story, stats)

        # ── Write file ──────────────────────────────────────────────────────
        out_dir = os.path.dirname(output_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        pdf.output(output_path)
        logger.info(f"PDF exported: {output_path}")
        return output_path

    # ── Rendering helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _render_title_page(pdf, family: str, story) -> None:
        """Cover page — centered title block with ornamental rule."""
        pdf.add_page()
        pdf.show_chrome = False
        page_h = pdf.h
        # Vertical anchor ~42% down
        pdf.set_y(page_h * 0.32)

        title = (story.title or "").strip() or "Untitled"
        pdf.set_font(family, "B", 28)
        pdf.multi_cell(0, 12, title, align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

        # Ornamental rule
        PDFExporter._ornament(pdf, family)
        pdf.ln(4)

        genre = (story.genre or "").strip()
        if genre:
            pdf.set_font(family, "I", 13)
            pdf.set_text_color(90, 90, 90)
            pdf.multi_cell(0, 7, genre, align="C", new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(0, 0, 0)

        synopsis = (getattr(story, "synopsis", "") or "").strip()
        if synopsis:
            pdf.ln(10)
            # Slight side inset for synopsis block
            pdf.set_x(MARGIN_L + 8)
            pdf.set_font(family, "", 10.5)
            pdf.multi_cell(pdf.w - 2 * (MARGIN_L + 8), 5.4, synopsis, align="C")

        # Footer colophon at the bottom
        pdf.set_y(-28)
        pdf.set_font(family, "", 9)
        pdf.set_text_color(150, 150, 150)
        pdf.cell(0, 5, "StoryForge", align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.cell(0, 5, datetime.now().strftime("%Y"), align="C")
        pdf.set_text_color(0, 0, 0)

    @staticmethod
    def _render_toc(pdf, family: str, outline, expected_pages: int) -> None:
        """Render table of contents from fpdf2 outline sections.

        fpdf2 requires the renderer to emit exactly `expected_pages` pages, so
        we pad with blank pages if the entry list is shorter than reserved.
        """
        pdf.set_font(family, "", 11)
        pdf.set_text_color(0, 0, 0)
        line_h = 7.0
        usable_w = pdf.w - MARGIN_L - MARGIN_R
        start_page = pdf.page_no()
        for section in outline:
            if section.level > 0:
                continue
            name = section.name or ""
            page = str(section.page_number)
            name_w = pdf.get_string_width(name)
            page_w = pdf.get_string_width(page)
            dots_w = max(4.0, usable_w - name_w - page_w - 2)
            dot_unit = pdf.get_string_width(" . ")
            n_dots = max(3, int(dots_w / dot_unit))
            leader = " " + ("." * n_dots) + " "
            pdf.cell(name_w + 1, line_h, name)
            pdf.cell(usable_w - name_w - page_w - 1, line_h, leader, align="C")
            pdf.cell(page_w, line_h, page, align="R", new_x="LMARGIN", new_y="NEXT")
        # Pad so the placeholder spans exactly expected_pages
        pages_used = pdf.page_no() - start_page + 1
        for _ in range(max(0, expected_pages - pages_used)):
            pdf.add_page()

    @staticmethod
    def _render_chapter(pdf, family: str, ch) -> None:
        """One chapter — new page with decorative head, then justified body."""
        pdf.add_page()
        pdf.show_chrome = True
        # Section entry for outline + TOC
        pdf.start_section(f"Chương {ch.chapter_number}: {ch.title or ''}".strip(" :"), level=0)

        # Top spacing to give the chapter head room
        pdf.ln(10)

        # "CHƯƠNG N" — small caps feel via uppercase + letter spacing
        pdf.set_font(family, "", 10)
        pdf.set_text_color(140, 140, 140)
        pdf.cell(0, 6, f"CHƯƠNG   {ch.chapter_number}", align="C",
                 new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)
        pdf.ln(2)

        # Chapter title
        title = (ch.title or "").strip()
        if title:
            pdf.set_font(family, "B", 18)
            pdf.multi_cell(0, 9, title, align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(3)

        PDFExporter._ornament(pdf, family)
        pdf.ln(8)

        # Body — justified paragraphs, first-line indent, 1.4 leading
        pdf.set_font(family, "", BODY_SIZE)
        content = ch.content or ""
        paragraphs = [p.strip() for p in content.split("\n") if p.strip()]
        for i, para in enumerate(paragraphs):
            # Scene separator convention: "***" or "* * *" lines
            if para in ("***", "* * *", "---", "—"):
                pdf.ln(3)
                PDFExporter._scene_break(pdf, family)
                pdf.ln(3)
                continue
            # First-line indent (skip on first paragraph after the chapter head)
            if i > 0:
                pdf.set_x(MARGIN_L + PARA_INDENT)
            pdf.multi_cell(0, BODY_LEADING, para, align="J",
                           new_x="LMARGIN", new_y="NEXT")
            pdf.ln(1.2)

    @staticmethod
    def _render_colophon(pdf, family: str, story, stats: ReadingStats) -> None:
        """Closing page with reading stats — quiet typography."""
        pdf.add_page()
        pdf.show_chrome = False
        pdf.ln(pdf.h * 0.30)

        PDFExporter._ornament(pdf, family)
        pdf.ln(8)

        pdf.set_font(family, "I", 12)
        pdf.set_text_color(80, 80, 80)
        pdf.multi_cell(0, 6, "Hết", align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)
        pdf.ln(12)

        pdf.set_font(family, "", 10)
        pdf.set_text_color(110, 110, 110)
        _now = datetime.now()
        lines = [
            f"{stats.total_chapters} chương  ·  {stats.total_words:,} từ  ·  ~{stats.estimated_reading_minutes} phút đọc",
            f"Xuất bản {_now.day:02d}/{_now.month:02d}/{_now.year}",
        ]
        for line in lines:
            pdf.multi_cell(0, 5.5, line, align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)

    # ── Ornaments ────────────────────────────────────────────────────────────

    @staticmethod
    def _ornament(pdf, family: str) -> None:
        """Thin horizontal rule centered on the page, ~40mm wide."""
        rule_w = 40.0
        x_center = pdf.w / 2
        y = pdf.get_y() + 2
        pdf.set_draw_color(170, 170, 170)
        pdf.set_line_width(0.3)
        pdf.line(x_center - rule_w / 2, y, x_center + rule_w / 2, y)
        pdf.set_draw_color(0, 0, 0)
        pdf.ln(5)

    @staticmethod
    def _scene_break(pdf, family: str) -> None:
        """Three dots, centered — marks intra-chapter scene transitions."""
        pdf.set_font(family, "", 11)
        pdf.set_text_color(130, 130, 130)
        pdf.cell(0, 6, "* * *", align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)

    @staticmethod
    def _header_h1(pdf, family: str, text: str, align: str = "L") -> None:
        pdf.set_font(family, "B", 18)
        pdf.multi_cell(0, 10, text, align=align, new_x="LMARGIN", new_y="NEXT")

    # ── Font handling ────────────────────────────────────────────────────────

    @staticmethod
    def _register_fonts(pdf) -> bool:
        """Register Regular/Bold/Italic NotoSans variants. Auto-download missing files.

        Returns True if at least Regular loaded successfully. Bold/Italic degrade
        to Regular if unavailable (fpdf2 still accepts the style letter but
        produces synthetic emboldening which is acceptable fallback).
        """
        regular_ok = PDFExporter._ensure_and_register(pdf, "regular", style="")
        if not regular_ok:
            return False
        PDFExporter._ensure_and_register(pdf, "bold",   style="B")
        PDFExporter._ensure_and_register(pdf, "italic", style="I")
        return True

    @staticmethod
    def _ensure_and_register(pdf, key: str, style: str) -> bool:
        filename = _FONT_FILES[key]
        font_path = os.path.join(FONT_DIR, filename)
        if not os.path.exists(font_path):
            if not PDFExporter._download_font(_FONT_URLS[key], font_path):
                return False
        try:
            pdf.add_font("NotoSans", style, font_path)
            return True
        except Exception as e:
            logger.warning(f"Font registration failed ({key}): {e}")
            return False

    @staticmethod
    def _download_font(url: str, dest_path: str) -> bool:
        """Download a font file. Returns True on success."""
        import urllib.request
        try:
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            logger.info(f"Downloading font: {os.path.basename(dest_path)}")
            urllib.request.urlretrieve(url, dest_path)
            return True
        except Exception as e:
            logger.warning(f"Font download failed ({url}): {e}")
            return False
