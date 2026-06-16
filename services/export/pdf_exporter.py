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
MARGIN_L = 20
MARGIN_R = 20
MARGIN_T = 22
MARGIN_B = 22

# Body typography — serif body for book feel
BODY_SIZE = 11
BODY_LEADING = 6.0  # mm line-height at 11pt (~1.5 leading)
PARA_INDENT = 5.5  # first-line indent (mm)
DROPCAP_SIZE = 26  # drop cap point size on chapter openers

# Font file names on disk (under services/assets/fonts/)
# Body uses NotoSerif (book-grade Vietnamese serif). Display elements use NotoSans.
_FONT_FILES = {
    "serif_regular": "NotoSerif-Regular.ttf",
    "serif_bold": "NotoSerif-Bold.ttf",
    "serif_italic": "NotoSerif-Italic.ttf",
    "sans_regular": "NotoSans-Regular.ttf",
    "sans_bold": "NotoSans-Bold.ttf",
    "sans_italic": "NotoSans-Italic.ttf",
}

# Remote source: Google Fonts repository (static files — stable parsing for fpdf2)
_FONT_URLS = {
    "serif_regular": "https://raw.githubusercontent.com/googlefonts/noto-fonts/main/hinted/ttf/NotoSerif/NotoSerif-Regular.ttf",
    "serif_bold": "https://raw.githubusercontent.com/googlefonts/noto-fonts/main/hinted/ttf/NotoSerif/NotoSerif-Bold.ttf",
    "serif_italic": "https://raw.githubusercontent.com/googlefonts/noto-fonts/main/hinted/ttf/NotoSerif/NotoSerif-Italic.ttf",
    "sans_regular": "https://raw.githubusercontent.com/googlefonts/noto-fonts/main/hinted/ttf/NotoSans/NotoSans-Regular.ttf",
    "sans_bold": "https://raw.githubusercontent.com/googlefonts/noto-fonts/main/hinted/ttf/NotoSans/NotoSans-Bold.ttf",
    "sans_italic": "https://raw.githubusercontent.com/googlefonts/noto-fonts/main/hinted/ttf/NotoSans/NotoSans-Italic.ttf",
}

SERIF = "NotoSerif"
SANS = "NotoSans"


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
            self.set_y(-14)
            try:
                self.set_font(SANS, "", 9)
            except Exception:
                self.set_font("Helvetica", "", 9)
            self.set_text_color(130, 130, 130)
            self.cell(0, 6, f"— {self.page_no()} —", align="C")
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

        body_ok = PDFExporter._register_fonts(pdf)
        # Body uses serif if available, sans if only sans loaded, Helvetica as final fallback.
        if body_ok == "serif":
            body_family = SERIF
            display_family = SANS
        elif body_ok == "sans":
            body_family = SANS
            display_family = SANS
            logger.warning("NotoSerif unavailable — body falls back to NotoSans")
        else:
            body_family = "Helvetica"
            display_family = "Helvetica"
            logger.warning(
                "Vietnamese fonts not found — falling back to Helvetica (diacritics may be missing)"
            )

        # ── 1. Title page ───────────────────────────────────────────────────
        PDFExporter._render_title_page(pdf, body_family, display_family, story)

        # ── 2. Table of Contents (auto-paginated placeholder) ───────────────
        pdf.add_page()
        pdf.show_chrome = False
        PDFExporter._header_h1(pdf, display_family, "Mục lục", align="C")
        pdf.ln(6)
        # Pre-size TOC: ~24 entries fit on an A5 page at 7mm line-height.
        _toc_entries = len(story.chapters) + (1 if characters else 0)
        _toc_pages = max(1, (_toc_entries + 23) // 24)
        pdf.insert_toc_placeholder(
            lambda p, outline: PDFExporter._render_toc(
                p, body_family, outline, _toc_pages
            ),
            pages=_toc_pages,
        )

        # ── 3. Characters (optional) ────────────────────────────────────────
        if characters:
            pdf.add_page()
            pdf.show_chrome = True
            pdf.start_section("Nhân vật", level=0)
            PDFExporter._header_h1(pdf, display_family, "Nhân vật", align="L")
            pdf.ln(4)
            for c in characters:
                pdf.set_font(display_family, "B", 12)
                pdf.multi_cell(0, 6, f"{c.name}", new_x="LMARGIN", new_y="NEXT")
                pdf.set_font(body_family, "I", 10)
                pdf.set_text_color(90, 90, 90)
                role_line = getattr(c, "role", "") or ""
                if role_line:
                    pdf.multi_cell(0, 5, role_line, new_x="LMARGIN", new_y="NEXT")
                pdf.set_text_color(0, 0, 0)
                pdf.set_font(body_family, "", 10.5)
                personality = getattr(c, "personality", "") or ""
                if personality:
                    pdf.multi_cell(0, 5.2, personality, new_x="LMARGIN", new_y="NEXT")
                pdf.ln(3)

        # ── 4. Chapters ─────────────────────────────────────────────────────
        for ch in story.chapters:
            PDFExporter._render_chapter(pdf, body_family, display_family, ch)

        # ── 5. Colophon / Stats ─────────────────────────────────────────────
        stats = PDFExporter.compute_reading_stats(story)
        PDFExporter._render_colophon(pdf, body_family, display_family, story, stats)

        # ── Write file ──────────────────────────────────────────────────────
        out_dir = os.path.dirname(output_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        pdf.output(output_path)
        logger.info(f"PDF exported: {output_path}")
        return output_path

    # ── Rendering helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _render_title_page(pdf, body_family: str, display_family: str, story) -> None:
        """Cover page — centered title block with ornamental rule and blank verso."""
        pdf.add_page()
        pdf.show_chrome = False
        page_h = pdf.h

        # Top mark — small all-caps publisher tag
        pdf.set_y(MARGIN_T + 4)
        pdf.set_font(display_family, "", 8)
        pdf.set_text_color(150, 150, 150)
        pdf.cell(
            0,
            5,
            "STORYFORGE  ·  AI STORY STUDIO",
            align="C",
            new_x="LMARGIN",
            new_y="NEXT",
        )
        pdf.set_text_color(0, 0, 0)

        # Vertical anchor ~36% down for title block
        pdf.set_y(page_h * 0.36)

        title = (story.title or "").strip() or "Untitled"
        pdf.set_font(display_family, "B", 30)
        pdf.multi_cell(0, 13, title, align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(3)

        # Ornamental rule
        PDFExporter._ornament(pdf, display_family)
        pdf.ln(5)

        genre = (story.genre or "").strip()
        if genre:
            pdf.set_font(body_family, "I", 12)
            pdf.set_text_color(90, 90, 90)
            pdf.multi_cell(0, 7, genre, align="C", new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(0, 0, 0)

        synopsis = (getattr(story, "synopsis", "") or "").strip()
        if synopsis:
            pdf.ln(12)
            pdf.set_x(MARGIN_L + 10)
            pdf.set_font(body_family, "I", 10.5)
            pdf.set_text_color(70, 70, 70)
            pdf.multi_cell(pdf.w - 2 * (MARGIN_L + 10), 5.6, synopsis, align="C")
            pdf.set_text_color(0, 0, 0)

        # Footer colophon at the bottom — single line to avoid pushing to verso
        pdf.set_y(-MARGIN_B - 8)
        pdf.set_font(display_family, "", 9)
        pdf.set_text_color(150, 150, 150)
        pdf.cell(
            0,
            5,
            f"StoryForge  ·  {datetime.now().strftime('%d/%m/%Y')}",
            align="C",
        )
        pdf.set_text_color(0, 0, 0)

        # Blank verso — keeps right-hand opening for the first chapter on print.
        pdf.add_page()
        pdf.show_chrome = False

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
    def _render_chapter(pdf, body_family: str, display_family: str, ch) -> None:
        """One chapter — new page with decorative head, then justified body with drop cap."""
        pdf.add_page()
        pdf.show_chrome = True
        # Section entry for outline + TOC
        pdf.start_section(
            f"Chương {ch.chapter_number}: {ch.title or ''}".strip(" :"), level=0
        )

        # Top spacing to give the chapter head room
        pdf.ln(14)

        # "CHƯƠNG N" — small caps via uppercase, display sans, muted colour
        pdf.set_font(display_family, "", 9)
        pdf.set_text_color(150, 150, 150)
        pdf.cell(
            0,
            6,
            f"C H Ư Ơ N G   {ch.chapter_number}",
            align="C",
            new_x="LMARGIN",
            new_y="NEXT",
        )
        pdf.set_text_color(0, 0, 0)
        pdf.ln(3)

        # Chapter title — display sans bold
        title = (ch.title or "").strip()
        if title:
            pdf.set_font(display_family, "B", 18)
            pdf.multi_cell(0, 9, title, align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(4)

        PDFExporter._ornament(pdf, display_family)
        pdf.ln(10)

        # Body — serif justified, generous leading, drop cap on first paragraph
        content = ch.content or ""
        paragraphs = [p.strip() for p in content.split("\n") if p.strip()]

        for i, para in enumerate(paragraphs):
            # Scene separator
            if para in ("***", "* * *", "---", "—"):
                pdf.ln(4)
                PDFExporter._scene_break(pdf, display_family)
                pdf.ln(4)
                continue

            if i == 0:
                PDFExporter._render_dropcap_paragraph(pdf, body_family, para)
            else:
                pdf.set_font(body_family, "", BODY_SIZE)
                pdf.set_x(MARGIN_L + PARA_INDENT)
                pdf.multi_cell(
                    0, BODY_LEADING, para, align="J", new_x="LMARGIN", new_y="NEXT"
                )
            pdf.ln(0.8)

    @staticmethod
    def _render_dropcap_paragraph(pdf, body_family: str, para: str) -> None:
        """Render a paragraph with a 3-line drop cap on the first character.

        Falls back to a normal justified paragraph if the paragraph starts with
        a quote/dash (dialogue) — drop caps look wrong on quotation marks.
        """
        if not para:
            return
        first = para[0]
        if first in ('"', "'", "“", "”", "‘", "’", "—", "-", "–"):
            pdf.set_font(body_family, "", BODY_SIZE)
            pdf.multi_cell(
                0, BODY_LEADING, para, align="J", new_x="LMARGIN", new_y="NEXT"
            )
            return

        rest = para[1:]
        # Drop cap measurements
        pdf.set_font(body_family, "B", DROPCAP_SIZE)
        cap_w = pdf.get_string_width(first) + 1.5
        cap_h = DROPCAP_SIZE * 0.35  # rough ascender height in mm at this size

        x0 = pdf.get_x()
        y0 = pdf.get_y()

        # Draw drop cap
        pdf.set_xy(x0, y0)
        pdf.cell(cap_w, cap_h, first)

        # Wrap remaining text in a narrower column beside the cap (~3 lines tall)
        col_x = x0 + cap_w
        col_w = pdf.w - MARGIN_R - col_x
        pdf.set_xy(col_x, y0)
        pdf.set_font(body_family, "", BODY_SIZE)

        # Split `rest` into ~3 lines of wrapped text beside the cap, then resume full-width.
        wrap_lines = PDFExporter._wrap_text(pdf, rest, col_w)
        beside = wrap_lines[:3]
        below = wrap_lines[3:]
        for idx, line in enumerate(beside):
            pdf.set_xy(col_x, y0 + idx * BODY_LEADING)
            pdf.cell(col_w, BODY_LEADING, line)
        # Move cursor below the drop cap block
        pdf.set_xy(MARGIN_L, y0 + max(len(beside), 1) * BODY_LEADING)
        if below:
            pdf.multi_cell(
                0,
                BODY_LEADING,
                " ".join(below),
                align="J",
                new_x="LMARGIN",
                new_y="NEXT",
            )

    @staticmethod
    def _wrap_text(pdf, text: str, max_w: float) -> list[str]:
        """Greedy word-wrap returning lines that fit within max_w at current font."""
        words = text.split()
        lines: list[str] = []
        cur = ""
        for w in words:
            candidate = f"{cur} {w}".strip()
            if pdf.get_string_width(candidate) <= max_w:
                cur = candidate
            else:
                if cur:
                    lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        return lines

    @staticmethod
    def _render_colophon(
        pdf, body_family: str, display_family: str, story, stats: ReadingStats
    ) -> None:
        """Closing page with reading stats — quiet typography."""
        pdf.add_page()
        pdf.show_chrome = False
        pdf.ln(pdf.h * 0.30)

        PDFExporter._ornament(pdf, display_family)
        pdf.ln(8)

        pdf.set_font(body_family, "I", 13)
        pdf.set_text_color(80, 80, 80)
        pdf.multi_cell(0, 6, "Hết", align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)
        pdf.ln(14)

        pdf.set_font(display_family, "", 9)
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
        """Decorative rule with center diamond, ~50mm wide."""
        rule_w = 50.0
        x_center = pdf.w / 2
        y = pdf.get_y() + 3
        pdf.set_draw_color(170, 170, 170)
        pdf.set_line_width(0.3)
        # left segment
        pdf.line(x_center - rule_w / 2, y, x_center - 3, y)
        # right segment
        pdf.line(x_center + 3, y, x_center + rule_w / 2, y)
        # center diamond
        pdf.set_fill_color(170, 170, 170)
        pdf.set_xy(x_center - 1.2, y - 1.2)
        pdf.cell(2.4, 2.4, "", fill=True)
        pdf.set_fill_color(255, 255, 255)
        pdf.set_draw_color(0, 0, 0)
        pdf.ln(6)

    @staticmethod
    def _scene_break(pdf, display_family: str) -> None:
        """Three dots, centered — marks intra-chapter scene transitions."""
        pdf.set_font(display_family, "", 12)
        pdf.set_text_color(140, 140, 140)
        pdf.cell(0, 6, "·   ·   ·", align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)

    @staticmethod
    def _header_h1(pdf, family: str, text: str, align: str = "L") -> None:
        pdf.set_font(family, "B", 18)
        pdf.multi_cell(0, 10, text, align=align, new_x="LMARGIN", new_y="NEXT")

    # ── Font handling ────────────────────────────────────────────────────────

    @staticmethod
    def _register_fonts(pdf) -> str:
        """Register both NotoSerif (body) and NotoSans (display) families.

        Returns "serif" if NotoSerif Regular loaded, "sans" if only NotoSans
        loaded, "" if neither family could be registered.
        """
        sans_ok = PDFExporter._ensure_and_register(pdf, SANS, "sans_regular", style="")
        if sans_ok:
            PDFExporter._ensure_and_register(pdf, SANS, "sans_bold", style="B")
            PDFExporter._ensure_and_register(pdf, SANS, "sans_italic", style="I")

        serif_ok = PDFExporter._ensure_and_register(
            pdf, SERIF, "serif_regular", style=""
        )
        if serif_ok:
            PDFExporter._ensure_and_register(pdf, SERIF, "serif_bold", style="B")
            PDFExporter._ensure_and_register(pdf, SERIF, "serif_italic", style="I")

        if serif_ok:
            return "serif"
        if sans_ok:
            return "sans"
        return ""

    @staticmethod
    def _ensure_and_register(pdf, family_name: str, key: str, style: str) -> bool:
        filename = _FONT_FILES[key]
        font_path = os.path.join(FONT_DIR, filename)
        if not os.path.exists(font_path):
            if not PDFExporter._download_font(_FONT_URLS[key], font_path):
                return False
        try:
            pdf.add_font(family_name, style, font_path)
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
