"""Show-don't-tell enforcer — pre-write guidance and post-write audit."""

import logging
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from services.llm_client import LLMClient

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sensory palette per genre
# ---------------------------------------------------------------------------

SENSORY_PALETTE: dict[str, dict] = {
    "Tiên Hiệp": {
        "primary": ["thị giác (luồng khí, hào quang năng lượng)", "xúc giác (cảm giác tu luyện, khí xuyên kinh mạch)"],
        "secondary": ["thính giác (tiếng gió linh khí, vũ khí rít qua không trung)"],
        "avoid": "tránh mô tả cảm xúc trực tiếp — dùng biến đổi cơ thể và phản ứng ngoại cảnh thay thế",
    },
    "Ngôn Tình": {
        "primary": ["xúc giác (chạm tay, hơi ấm, nhịp tim)", "thính giác (giọng nói thì thầm, tiếng thở)"],
        "secondary": ["thị giác (ánh mắt, cử chỉ nhỏ)", "khứu giác (mùi nước hoa, mùi quen thuộc)"],
        "avoid": "tránh 'anh yêu em' hoặc 'tim cô đập loạn' — dùng chi tiết vật lý cụ thể",
    },
    "Trinh Thám": {
        "primary": ["thị giác (chi tiết bất thường, dấu vết, ánh sáng bóng tối)", "thính giác (im lặng, bước chân, tiếng cọ)"],
        "secondary": ["khứu giác (mùi thuốc, máu, bụi)", "xúc giác (vật chứng)"],
        "avoid": "tránh giải thích thẳng — để chi tiết tự nói, nhân vật quan sát chứ không kết luận vội",
    },
    "Kiếm Hiệp": {
        "primary": ["thị giác (đường kiếm, chuyển động, địa thế)", "thính giác (tiếng kiếm khua, gió chém)"],
        "secondary": ["xúc giác (trọng lượng kiếm, chấn động)", "vị giác (máu, mồ hôi trong chiến đấu)"],
        "avoid": "tránh tả võ công trừu tượng — neo vào hành động cụ thể và phản ứng đối thủ",
    },
    "Dị Giới": {
        "primary": ["thị giác (cảnh vật lạ, sinh vật, phép thuật hiển thị)", "xúc giác (môi trường xa lạ tác động cơ thể)"],
        "secondary": ["khứu giác (mùi lạ)", "thính giác (âm thanh thế giới khác)"],
        "avoid": "tránh info-dump mô tả thế giới — để nhân vật khám phá và phản ứng tự nhiên",
    },
    "Đô Thị": {
        "primary": ["thính giác (tiếng ồn đô thị, nhạc, cuộc trò chuyện)", "thị giác (ánh đèn, đám đông, không gian)"],
        "secondary": ["xúc giác (vật liệu, nhiệt độ)", "khứu giác (thức ăn, không khí thành phố)"],
        "avoid": "tránh mô tả nội tâm quá dài — dùng hành vi và lựa chọn để lộ tâm lý",
    },
    "_default": {
        "primary": ["thị giác (chi tiết môi trường cụ thể)", "xúc giác (cảm giác cơ thể)"],
        "secondary": ["thính giác", "khứu giác"],
        "avoid": "tránh nói thẳng cảm xúc — dùng hành động và phản ứng vật lý",
    },
}

# ---------------------------------------------------------------------------
# Audit prompt template
# ---------------------------------------------------------------------------

AUDIT_TELLING = """\
Bạn là biên tập viên chuyên phát hiện lỗi "telling" trong văn xuôi. BẮT BUỘC trả về JSON thuần túy.

NHIỆM VỤ: Đọc đoạn văn sau và liệt kê các chỗ tác giả "nói thẳng" (telling) thay vì "diễn tả" (showing).

ĐOẠN VĂN:
{content}

THỂ LOẠI: {genre}

DẤU HIỆU TELLING CẦN TÌM:
- Nêu thẳng cảm xúc: "anh rất buồn", "cô ấy hạnh phúc", "hắn tức giận"
- Nhận xét tính cách: "anh ấy là người tốt bụng", "cô ấy rất thông minh"
- Tóm tắt thay vì diễn tả: "cuộc chiến diễn ra ác liệt", "họ nói chuyện hồi lâu"
- Giải thích động cơ lộ liễu: "vì sợ hãi nên anh ta...", "do tức giận, cô ấy..."

TRẢ VỀ JSON với cấu trúc:
{{
  "violations": [
    {{
      "excerpt": "đoạn trích nguyên văn (tối đa 20 từ)",
      "issue": "lý do đây là telling",
      "suggestion": "gợi ý cách viết lại theo kiểu showing (1-2 câu)"
    }}
  ]
}}

Nếu không có lỗi, trả về {{"violations": []}}.
"""

# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------


def build_show_dont_tell_guidance(genre: str, pacing_type: str = "") -> str:
    """Return a prompt section with show-don't-tell guidance for a genre/pacing.

    Pure string construction — no LLM call.
    """
    palette = SENSORY_PALETTE.get(genre, SENSORY_PALETTE["_default"])

    lines = ["## HƯỚNG DẪN SHOW DON'T TELL"]
    lines.append("")

    # Sensory palette
    lines.append("### Bảng giác quan ưu tiên cho thể loại này:")
    lines.append("Chính: " + " | ".join(palette["primary"]))
    lines.append("Phụ: " + " | ".join(palette["secondary"]))
    lines.append(f"Lưu ý: {palette['avoid']}")
    lines.append("")

    # Ratio guidance based on pacing
    lines.append("### Tỉ lệ action/dialogue vs narration:")
    if pacing_type == "climax":
        lines.append("- Climax: 70% hành động/đối thoại — 30% nội tâm/mô tả")
        lines.append("- Câu ngắn, nhịp nhanh. Không dừng để giải thích cảm xúc.")
    elif pacing_type == "cooldown":
        lines.append("- Cooldown: 40% hành động — 60% nội tâm/mô tả chậm")
        lines.append("- Cho phép nhân vật phản ánh nhưng qua hình ảnh, không nói thẳng.")
    elif pacing_type == "setup":
        lines.append("- Setup: 50% mô tả thế giới/nhân vật — 50% hành động nhỏ")
        lines.append("- Xây dựng bằng chi tiết cụ thể, không liệt kê tính cách trực tiếp.")
    else:
        # rising / twist / default
        lines.append("- Nhịp chuẩn: 60% hành động/đối thoại — 40% mô tả/nội tâm")
        lines.append("- Cân bằng giữa tiến trình cốt truyện và chiều sâu cảm xúc.")
    lines.append("")

    # Anti-patterns
    lines.append("### Anti-patterns cần tránh (thay thế gợi ý):")
    lines.append('- "Anh ấy rất buồn" → Mô tả: anh nhìn chằm vào tường, không nói thêm lời nào.')
    lines.append('- "Cô ấy hạnh phúc" → Mô tả: khóe miệng cô nhếch lên dù cô không để ý.')
    lines.append('- "Hắn tức giận" → Mô tả: hàm hắn siết lại, nắm tay trắng bợt.')
    lines.append('- "Cuộc chiến ác liệt" → Mô tả từng nhát kiếm, từng bước lùi, mồ hôi và máu.')
    lines.append('- "Cô ấy thông minh" → Cho nhân vật giải quyết vấn đề — độc giả tự kết luận.')

    return "\n".join(lines)


def audit_chapter_telling(
    llm: "LLMClient",
    content: str,
    genre: str,
    model: Optional[str] = None,
) -> list[dict]:
    """Call LLM to audit chapter for telling violations.

    Returns list of {excerpt, issue, suggestion} dicts.
    Non-fatal: returns [] on any error.
    """
    try:
        result = llm.generate_json(
            system_prompt="Bạn là biên tập viên chuyên phát hiện lỗi telling/showing. BẮT BUỘC trả về JSON thuần túy.",
            user_prompt=AUDIT_TELLING.format(content=content, genre=genre),
            model=model,
            model_tier="cheap",
        )
        violations = result.get("violations", [])
        if not isinstance(violations, list):
            return []
        return [v for v in violations if isinstance(v, dict)]
    except Exception as e:
        logger.warning("audit_chapter_telling failed (non-fatal): %s", e)
        return []


def build_rewrite_telling_prompt(content: str, violations: list[dict]) -> str:
    """Build a prompt asking the LLM to rewrite only flagged sections.

    Caller is responsible for making the LLM call.
    Returns empty string if no violations.
    """
    if not violations:
        return ""

    lines = ["Dưới đây là một đoạn văn cần được chỉnh sửa theo nguyên tắc SHOW DON'T TELL."]
    lines.append("")
    lines.append("## ĐOẠN VĂN GỐC:")
    lines.append(content)
    lines.append("")
    lines.append("## CÁC LỖI CẦN SỬA:")
    for i, v in enumerate(violations, 1):
        excerpt = v.get("excerpt", "")
        issue = v.get("issue", "")
        suggestion = v.get("suggestion", "")
        lines.append(f"{i}. Đoạn: \"{excerpt}\"")
        if issue:
            lines.append(f"   Lý do: {issue}")
        if suggestion:
            lines.append(f"   Gợi ý: {suggestion}")
    lines.append("")
    lines.append("## YÊU CẦU:")
    lines.append("- Chỉ sửa các đoạn được đánh dấu ở trên, giữ nguyên phần còn lại.")
    lines.append("- Áp dụng kỹ thuật showing: hành động, phản ứng cơ thể, chi tiết cụ thể.")
    lines.append("- Không thêm giải thích hay chú thích — trả về đoạn văn đã sửa hoàn chỉnh.")

    return "\n".join(lines)
