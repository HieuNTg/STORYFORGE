"""Dialogue attribution validator — ensures clear speaker identification.

Feature #16: Detect ambiguous dialogue attribution and unclear speakers.

Regex pattern constants, the :class:`DialogueLine` dataclass, and the raw-text
parsing helpers live in ``_dialogue_attribution_parsing`` and are re-exported
here so existing import paths keep working.
"""

import logging
from typing import TYPE_CHECKING

from pipeline.layer1_story._dialogue_attribution_parsing import (
    ATTRIBUTION_PATTERN,
    DIALOGUE_PATTERN,
    TRAILING_ATTR,
    DialogueLine,
    detect_rapid_exchange,
    extract_dialogue_lines,
)

if TYPE_CHECKING:
    from models.schemas import Character
    from services.llm_client import LLMClient

logger = logging.getLogger(__name__)

__all__ = [
    "ATTRIBUTION_PATTERN",
    "DIALOGUE_PATTERN",
    "TRAILING_ATTR",
    "DialogueLine",
    "detect_rapid_exchange",
    "extract_dialogue_lines",
    "validate_dialogue_attribution",
    "format_attribution_warning",
    "get_attribution_enforcement_prompt",
]


def validate_dialogue_attribution(
    llm: "LLMClient",
    chapter_content: str,
    characters: list["Character"],
    model: str | None = None,
) -> dict:
    """Validate dialogue attribution clarity.

    Returns: {
        'total_lines': int,
        'clear_attribution': int,
        'unclear_lines': list[DialogueLine],
        'clarity_score': float,
        'suggestions': list[str]
    }
    """
    dialogues = extract_dialogue_lines(chapter_content)

    if not dialogues:
        return {
            "total_lines": 0,
            "clear_attribution": 0,
            "unclear_lines": [],
            "clarity_score": 1.0,
            "suggestions": [],
        }

    clear = [d for d in dialogues if d.attribution_type != "unclear"]
    unclear = [d for d in dialogues if d.attribution_type == "unclear"]

    clarity_score = len(clear) / len(dialogues) if dialogues else 1.0

    suggestions = []
    if unclear:
        suggestions.append(f"{len(unclear)} câu thoại không rõ ai nói")

        # Use LLM to identify likely speakers for unclear lines
        if unclear[:3]:
            char_names = [c.name for c in characters[:10]]
            unclear_text = "\n".join(
                f'- Line {d.line_number}: "{d.text[:50]}..."' for d in unclear[:3]
            )

            try:
                result = llm.generate_json(
                    system_prompt="Xác định người nói. Trả JSON.",
                    user_prompt=f"""Các câu thoại không rõ người nói:
{unclear_text}

Nhân vật: {", ".join(char_names)}

Đoán ai nói dựa trên ngữ cảnh/giọng điệu:
{{"attributions": [{{"line": số, "likely_speaker": "tên", "reason": "lý do"}}]}}""",
                    temperature=0.2,
                    max_tokens=300,
                    model_tier="cheap",
                    expect="dict",
                    list_key="attributions",
                )

                for attr in result.get("attributions", []):
                    line_num = attr.get("line", 0)
                    speaker = attr.get("likely_speaker", "")
                    reason = attr.get("reason", "")
                    if speaker:
                        suggestions.append(
                            f"Line {line_num}: có thể là {speaker} ({reason})"
                        )

            except Exception as e:
                logger.debug(f"Attribution LLM check failed: {e}")

    return {
        "total_lines": len(dialogues),
        "clear_attribution": len(clear),
        "unclear_lines": unclear,
        "clarity_score": clarity_score,
        "suggestions": suggestions,
    }


def format_attribution_warning(validation_result: dict) -> str:
    """Format attribution validation as warning text."""
    if validation_result.get("clarity_score", 1.0) >= 0.8:
        return ""

    lines = ["## ⚠️ CẢNH BÁO ATTRIBUTION:"]
    lines.append(
        f"Độ rõ ràng: {validation_result['clarity_score']:.0%} "
        f"({validation_result['clear_attribution']}/{validation_result['total_lines']})"
    )

    for s in validation_result.get("suggestions", [])[:3]:
        lines.append(f"- {s}")

    lines.append('Thêm tag người nói: "Nội dung" - Tên nói.')
    return "\n".join(lines)


def get_attribution_enforcement_prompt(
    rapid_exchanges: list[dict],
    unclear_count: int,
) -> str:
    """Build prompt text to enforce clear attribution."""
    if not rapid_exchanges and unclear_count < 3:
        return ""

    lines = ["## 💬 YÊU CẦU DIALOGUE:"]

    if rapid_exchanges:
        lines.append(
            f"- {len(rapid_exchanges)} đoạn thoại nhanh cần thêm tag người nói"
        )

    if unclear_count >= 3:
        lines.append(f"- {unclear_count} câu thoại trước đó không rõ ai nói")

    lines.append("- Mỗi 2-3 câu thoại PHẢI có attribution rõ ràng")
    lines.append('- Format: "Nội dung" - Tên nói/hỏi/đáp')

    return "\n".join(lines)
