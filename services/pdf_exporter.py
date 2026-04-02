"""Export story as PDF with Vietnamese typography support."""
import logging
import os
from typing import Union
from models.schemas import StoryDraft, EnhancedStory, Character, ReadingStats

logger = logging.getLogger(__name__)

FONT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "fonts")


class PDFExporter:
    """Export story as PDF with Vietnamese font support using fpdf2."""

    @staticmethod
    def compute_reading_stats(story: Union[StoryDraft, EnhancedStory]) -> ReadingStats:
        """Tính số từ, thời gian đọc, v.v."""
        chapters = story.chapters
        total_words = sum(len(ch.content.split()) for ch in chapters)
        total_ch = len(chapters)
        avg_wpc = total_words // max(1, total_ch)
        reading_min = max(1, total_words // 200)  # ~200 từ/phút
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
        font: str = "NotoSansVN",
    ) -> str:
        """Export story to PDF. Returns path to generated file."""
        try:
            from fpdf import FPDF
        except ImportError:
            logger.error("fpdf2 not installed. Run: pip install fpdf2")
            return ""

        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)

        # Đăng ký font tiếng Việt
        font_registered = PDFExporter._register_font(pdf, font)
        if font_registered:
            pdf.set_font(font, size=12)
        else:
            pdf.set_font("Helvetica", size=12)
            logger.warning("Vietnamese font not found, using Helvetica (diacritics may not render)")

        # Trang tiêu đề
        pdf.add_page()
        pdf.set_font_size(24)
        pdf.cell(0, 40, story.title, new_x="LMARGIN", new_y="NEXT", align="C")
        pdf.set_font_size(14)
        pdf.cell(0, 10, f"The loai: {story.genre}", new_x="LMARGIN", new_y="NEXT", align="C")

        # Trang nhân vật
        if characters:
            pdf.add_page()
            pdf.set_font_size(16)
            pdf.cell(0, 10, "Nhan vat", new_x="LMARGIN", new_y="NEXT")
            pdf.set_font_size(11)
            for c in characters:
                pdf.multi_cell(0, 6, f"- {c.name} ({c.role}): {c.personality}")
                pdf.ln(2)

        # Các chương
        pdf.set_font_size(12)
        for ch in story.chapters:
            pdf.add_page()
            pdf.set_font_size(16)
            pdf.cell(0, 10, f"Chuong {ch.chapter_number}: {ch.title}", new_x="LMARGIN", new_y="NEXT")
            pdf.set_font_size(12)
            pdf.ln(5)
            # Chia nội dung thành đoạn văn
            for para in ch.content.split("\n"):
                para = para.strip()
                if para:
                    pdf.multi_cell(0, 6, para)
                    pdf.ln(3)

        # Trang thống kê
        stats = PDFExporter.compute_reading_stats(story)
        pdf.add_page()
        pdf.set_font_size(14)
        pdf.cell(0, 10, "Thong ke", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font_size(11)
        pdf.cell(0, 8, f"Tong so tu: {stats.total_words:,}", new_x="LMARGIN", new_y="NEXT")
        pdf.cell(0, 8, f"So chuong: {stats.total_chapters}", new_x="LMARGIN", new_y="NEXT")
        pdf.cell(0, 8, f"Thoi gian doc: ~{stats.estimated_reading_minutes} phut", new_x="LMARGIN", new_y="NEXT")

        out_dir = os.path.dirname(output_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        pdf.output(output_path)
        logger.info(f"PDF exported: {output_path}")
        return output_path

    @staticmethod
    def _register_font(pdf, font_name: str) -> bool:
        """Đăng ký font hỗ trợ tiếng Việt. Auto-download nếu thiếu file."""
        font_path = os.path.join(FONT_DIR, "NotoSans-Regular.ttf")
        if not os.path.exists(font_path):
            # Auto-download font nếu thiếu
            font_path = PDFExporter._download_font(font_path)
            if not font_path:
                return False
        try:
            pdf.add_font(font_name, "", font_path)
            return True
        except Exception as e:
            logger.warning(f"Font registration failed: {e}")
            return False

    @staticmethod
    def _download_font(dest_path: str) -> str:
        """Download NotoSans font từ Google Fonts. Trả path hoặc empty string."""
        import urllib.request
        url = (
            "https://raw.githubusercontent.com/google/fonts/main/"
            "ofl/notosans/NotoSans%5Bwdth%2Cwght%5D.ttf"
        )
        try:
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            logger.info("Downloading NotoSans font for Vietnamese PDF support...")
            urllib.request.urlretrieve(url, dest_path)
            logger.info(f"Font downloaded: {dest_path}")
            return dest_path
        except Exception as e:
            logger.warning(f"Font download failed: {e}")
            return ""
