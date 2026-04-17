"""Dialogue attribution validator — ensures clear speaker identification.

Feature #16: Detect ambiguous dialogue attribution and unclear speakers.
"""

import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from services.llm_client import LLMClient
    from models.schemas import Character

logger = logging.getLogger(__name__)

# Vietnamese dialogue patterns
DIALOGUE_PATTERN = re.compile(r'[""「『]([^""」』]+)[""」』]')
ATTRIBUTION_PATTERN = re.compile(
    r'(\w+)\s*(?:nói|hỏi|đáp|thì thầm|gào|la|cười|trả lời|thốt|kêu|rên|rít)',
    re.IGNORECASE
)
# Trailing attribution: "..." - Tên nói
TRAILING_ATTR = re.compile(
    r'[""」』]\s*[-–—]\s*(\w+)',
    re.IGNORECASE
)


@dataclass
class DialogueLine:
    """A parsed dialogue line."""
    text: str
    speaker: str = ""
    attribution_type: str = ""  # 'prefix' | 'suffix' | 'context' | 'unclear'
    confidence: float = 0.0
    line_number: int = 0


def extract_dialogue_lines(content: str) -> list[DialogueLine]:
    """Extract dialogue lines with basic attribution detection."""
    lines = content.split('\n')
    dialogues = []

    for i, line in enumerate(lines):
        matches = DIALOGUE_PATTERN.findall(line)
        if not matches:
            continue

        for dialogue_text in matches:
            if len(dialogue_text) < 5:
                continue

            dl = DialogueLine(
                text=dialogue_text[:100],
                line_number=i + 1,
            )

            # Check for prefix attribution
            prefix_match = ATTRIBUTION_PATTERN.search(line.split(dialogue_text)[0] if dialogue_text in line else "")
            if prefix_match:
                dl.speaker = prefix_match.group(1)
                dl.attribution_type = "prefix"
                dl.confidence = 0.9

            # Check for trailing attribution
            if not dl.speaker:
                trailing_match = TRAILING_ATTR.search(line)
                if trailing_match:
                    dl.speaker = trailing_match.group(1)
                    dl.attribution_type = "suffix"
                    dl.confidence = 0.85

            # Check for name in same line
            if not dl.speaker:
                attr_match = ATTRIBUTION_PATTERN.search(line)
                if attr_match:
                    dl.speaker = attr_match.group(1)
                    dl.attribution_type = "context"
                    dl.confidence = 0.7

            if not dl.speaker:
                dl.attribution_type = "unclear"
                dl.confidence = 0.0

            dialogues.append(dl)

    return dialogues


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
                f"- Line {d.line_number}: \"{d.text[:50]}...\""
                for d in unclear[:3]
            )

            try:
                result = llm.generate_json(
                    system_prompt="Xác định người nói. Trả JSON.",
                    user_prompt=f"""Các câu thoại không rõ người nói:
{unclear_text}

Nhân vật: {', '.join(char_names)}

Đoán ai nói dựa trên ngữ cảnh/giọng điệu:
{{"attributions": [{{"line": số, "likely_speaker": "tên", "reason": "lý do"}}]}}""",
                    temperature=0.2,
                    max_tokens=300,
                    model_tier="cheap",
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


def detect_rapid_exchange(content: str, threshold: int = 4) -> list[dict]:
    """Detect rapid dialogue exchanges that may confuse readers.

    Returns list of segments with rapid back-and-forth.
    """
    lines = content.split('\n')
    rapid_exchanges = []
    consecutive_dialogue = 0
    start_line = 0

    for i, line in enumerate(lines):
        if DIALOGUE_PATTERN.search(line):
            if consecutive_dialogue == 0:
                start_line = i
            consecutive_dialogue += 1
        else:
            if consecutive_dialogue >= threshold:
                rapid_exchanges.append({
                    "start_line": start_line + 1,
                    "end_line": i,
                    "dialogue_count": consecutive_dialogue,
                })
            consecutive_dialogue = 0

    # Check final segment
    if consecutive_dialogue >= threshold:
        rapid_exchanges.append({
            "start_line": start_line + 1,
            "end_line": len(lines),
            "dialogue_count": consecutive_dialogue,
        })

    return rapid_exchanges


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

    lines.append("Thêm tag người nói: \"Nội dung\" - Tên nói.")
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
        lines.append(f"- {len(rapid_exchanges)} đoạn thoại nhanh cần thêm tag người nói")

    if unclear_count >= 3:
        lines.append(f"- {unclear_count} câu thoại trước đó không rõ ai nói")

    lines.append("- Mỗi 2-3 câu thoại PHẢI có attribution rõ ràng")
    lines.append("- Format: \"Nội dung\" - Tên nói/hỏi/đáp")

    return "\n".join(lines)
