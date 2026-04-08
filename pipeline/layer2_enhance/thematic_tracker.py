"""Thematic Resonance Tracker — trích xuất chủ đề và theo dõi sự nhất quán chủ đề."""

import logging
from pydantic import BaseModel, Field
from models.schemas import StoryDraft, Chapter
from services.llm_client import LLMClient

logger = logging.getLogger(__name__)

EXTRACT_THEME = """Phân tích chủ đề trung tâm của truyện sau:

TIÊU ĐỀ: {title}
THỂ LOẠI: {genre}
TÓM TẮT: {synopsis}
TIỀN ĐỀ CHỦ ĐỀ: {premise}

NHÂN VẬT:
{characters}

Trả về JSON:
{{
  "central_theme": "chủ đề trung tâm (1 câu ngắn gọn)",
  "recurring_motifs": ["hình ảnh/biểu tượng lặp lại trong truyện"],
  "symbolic_items": ["vật thể mang ý nghĩa biểu tượng"],
  "thematic_questions": ["câu hỏi chủ đề truyện đặt ra cho người đọc"]
}}"""

SCORE_CHAPTER_THEME = """Đánh giá mức độ chương này củng cố chủ đề trung tâm.

CHỦ ĐỀ: {central_theme}
MOTIF CẦN CÓ: {motifs}
BIỂU TƯỢNG: {symbols}

NỘI DUNG CHƯƠNG:
{content}

Trả về JSON:
{{
  "theme_alignment": 0.7,
  "motifs_present": ["motif đã xuất hiện trong chương"],
  "motifs_missing": ["motif nên thêm vào để củng cố chủ đề"],
  "drift_warning": "cảnh báo nếu chương lệch chủ đề (để rỗng nếu ổn)"
}}"""


class ThemeProfile(BaseModel):
    central_theme: str = ""
    recurring_motifs: list[str] = Field(default_factory=list)
    symbolic_items: list[str] = Field(default_factory=list)
    thematic_questions: list[str] = Field(default_factory=list)


class ChapterThematicScore(BaseModel):
    chapter_number: int
    theme_alignment: float = 0.5
    motifs_present: list[str] = Field(default_factory=list)
    motifs_missing: list[str] = Field(default_factory=list)
    drift_warning: str = ""


class ThematicTracker:
    """Trích xuất chủ đề từ bản thảo và theo dõi độ nhất quán chủ đề theo chương."""

    def __init__(self):
        self.llm = LLMClient()

    def extract_theme(self, draft: StoryDraft) -> ThemeProfile:
        """Dùng LLM trích xuất chủ đề trung tâm từ synopsis, premise và nhân vật."""
        chars_text = "\n".join(
            f"- {c.name} ({c.role}): {c.motivation}"
            for c in (draft.characters or [])[:5]
        ) or "Không có thông tin nhân vật"

        synopsis = getattr(draft, "synopsis", "") or ""
        premise_raw = getattr(draft, "premise", {}) or {}
        if isinstance(premise_raw, dict):
            import json as _json
            premise = _json.dumps(premise_raw, ensure_ascii=False)
        else:
            premise = str(premise_raw)

        try:
            result = self.llm.generate_json(
                system_prompt="Phân tích chủ đề văn học. Trả về JSON.",
                user_prompt=EXTRACT_THEME.format(
                    title=draft.title or "",
                    genre=draft.genre or "",
                    synopsis=synopsis[:1000],
                    premise=premise[:500],
                    characters=chars_text,
                ),
                temperature=0.3,
                max_tokens=512,
                model_tier="cheap",
            )
            return ThemeProfile(
                central_theme=result.get("central_theme", ""),
                recurring_motifs=result.get("recurring_motifs", []),
                symbolic_items=result.get("symbolic_items", []),
                thematic_questions=result.get("thematic_questions", []),
            )
        except Exception as e:
            logger.warning(f"Theme extraction failed (non-fatal): {e}")
            return ThemeProfile()

    def score_chapter_theme(
        self,
        chapter: Chapter,
        theme: ThemeProfile,
    ) -> ChapterThematicScore:
        """Chấm điểm mức độ chương củng cố chủ đề trung tâm."""
        if not theme.central_theme:
            return ChapterThematicScore(chapter_number=chapter.chapter_number)

        motifs_text = ", ".join(theme.recurring_motifs[:6]) or "Không có"
        symbols_text = ", ".join(theme.symbolic_items[:6]) or "Không có"

        try:
            result = self.llm.generate_json(
                system_prompt="Đánh giá độ nhất quán chủ đề. Trả về JSON.",
                user_prompt=SCORE_CHAPTER_THEME.format(
                    central_theme=theme.central_theme,
                    motifs=motifs_text,
                    symbols=symbols_text,
                    content=chapter.content[:3000],
                ),
                temperature=0.2,
                max_tokens=400,
                model_tier="cheap",
            )
            return ChapterThematicScore(
                chapter_number=chapter.chapter_number,
                theme_alignment=float(result.get("theme_alignment", 0.5)),
                motifs_present=result.get("motifs_present", []),
                motifs_missing=result.get("motifs_missing", []),
                drift_warning=result.get("drift_warning", ""),
            )
        except Exception as e:
            logger.debug(f"Chapter theme scoring failed: {e}")
            return ChapterThematicScore(chapter_number=chapter.chapter_number)

    def generate_thematic_guidance(
        self,
        theme: ThemeProfile,
        chapter_score: ChapterThematicScore,
    ) -> str:
        """Tạo hướng dẫn nâng cấp: motif cần thêm và cảnh báo lệch chủ đề."""
        if not theme.central_theme:
            return ""

        parts: list[str] = [f"Chủ đề trung tâm: {theme.central_theme}"]

        missing = chapter_score.motifs_missing[:4]
        if missing:
            parts.append(f"Motif cần dệt vào: {', '.join(missing)}")

        if chapter_score.drift_warning:
            parts.append(f"Cảnh báo lệch chủ đề: {chapter_score.drift_warning}")

        if theme.thematic_questions:
            parts.append(
                f"Câu hỏi chủ đề cần gợi lên: {theme.thematic_questions[0]}"
            )

        return "\n".join(parts)

    def format_for_prompt(self, guidance: str) -> str:
        """Định dạng hướng dẫn chủ đề để chèn vào ENHANCE_CHAPTER prompt."""
        if not guidance:
            return ""
        return (
            "\n\n=== HƯỚNG DẪN CHỦ ĐỀ ===\n"
            f"{guidance}\n"
            "=== KẾT THÚC HƯỚNG DẪN CHỦ ĐỀ ==="
        )
