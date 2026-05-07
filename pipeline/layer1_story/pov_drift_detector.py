"""POV drift detector — identifies unexpected point-of-view shifts within chapters.

Feature #12: Detect when narrative POV changes mid-chapter without clear transition.
"""

import logging
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from services.llm_client import LLMClient
    from models.schemas import Character

logger = logging.getLogger(__name__)

# Vietnamese POV indicators
FIRST_PERSON = re.compile(r'\b(tôi|ta|mình|tao|tớ)\b', re.IGNORECASE)
THIRD_PERSON_PATTERNS = [
    r'\b(anh ấy|cô ấy|hắn|nàng|gã|y|thị)\b',
    r'\b(nghĩ thầm|tự nhủ|trong lòng)\b',
]


def detect_pov_type(text: str) -> str:
    """Detect primary POV type from text sample.

    Returns: 'first' | 'third' | 'mixed' | 'unknown'
    """
    first_count = len(FIRST_PERSON.findall(text))
    third_count = sum(
        len(re.findall(p, text, re.IGNORECASE))
        for p in THIRD_PERSON_PATTERNS
    )

    if first_count > 10 and third_count < 3:
        return "first"
    elif third_count > 5 and first_count < 3:
        return "third"
    elif first_count > 5 and third_count > 5:
        return "mixed"
    return "unknown"


def extract_pov_character(
    llm: "LLMClient",
    text: str,
    characters: list["Character"],
    model: str | None = None,
) -> dict:
    """Extract the primary POV character from text.

    Returns: {character: str, confidence: float, pov_type: str}
    """
    char_names = [c.name for c in characters[:10]]

    result = llm.generate_json(
        system_prompt="Phân tích POV. Trả JSON.",
        user_prompt=f"""Đoạn văn:
{text[:2000]}

Nhân vật: {', '.join(char_names)}

Xác định:
1. Nhân vật POV chính (ai đang kể/suy nghĩ)
2. Loại POV (ngôi 1/ngôi 3/hỗn hợp)
3. Độ tin cậy (0.0-1.0)

{{"character": "tên nhân vật", "pov_type": "first/third/mixed", "confidence": 0.0-1.0}}""",
        temperature=0.1,
        max_tokens=150,
        model_tier="cheap",
    )

    if isinstance(result, list):
        result = next((x for x in result if isinstance(x, dict)), {})
    if not isinstance(result, dict):
        result = {}

    return {
        "character": result.get("character", ""),
        "pov_type": result.get("pov_type", "unknown"),
        "confidence": float(result.get("confidence", 0.5)),
    }


def detect_pov_drift(
    llm: "LLMClient",
    chapter_content: str,
    characters: list["Character"],
    expected_pov: str | None = None,
    model: str | None = None,
) -> dict:
    """Detect POV drift within a chapter.

    Splits chapter into segments and checks for POV consistency.

    Returns: {
        'consistent': bool,
        'primary_pov': str,
        'drifts': [{segment, from_char, to_char, position}],
        'confidence': float
    }
    """
    # Split into ~500 word segments
    words = chapter_content.split()
    segment_size = 500
    segments = []
    for i in range(0, len(words), segment_size):
        segment_words = words[i:i + segment_size]
        segments.append(" ".join(segment_words))

    if len(segments) < 2:
        return {
            "consistent": True,
            "primary_pov": expected_pov or "",
            "drifts": [],
            "confidence": 1.0,
        }

    # Analyze first and last segments for efficiency
    pov_results = []
    for idx in [0, len(segments) - 1]:
        pov = extract_pov_character(llm, segments[idx], characters, model)
        pov["segment"] = idx
        pov_results.append(pov)

    # Check middle segment if chapter is long enough
    if len(segments) > 3:
        mid_idx = len(segments) // 2
        mid_pov = extract_pov_character(llm, segments[mid_idx], characters, model)
        mid_pov["segment"] = mid_idx
        pov_results.insert(1, mid_pov)

    # Detect drifts
    drifts = []
    primary_char = pov_results[0]["character"]

    for i in range(1, len(pov_results)):
        prev = pov_results[i - 1]
        curr = pov_results[i]

        if curr["character"] and curr["character"] != prev["character"]:
            if curr["confidence"] > 0.6 and prev["confidence"] > 0.6:
                drifts.append({
                    "segment": curr["segment"],
                    "from_char": prev["character"],
                    "to_char": curr["character"],
                    "position": f"segment {curr['segment'] + 1}/{len(segments)}",
                })

    # Calculate overall confidence
    avg_confidence = sum(p["confidence"] for p in pov_results) / len(pov_results)

    return {
        "consistent": len(drifts) == 0,
        "primary_pov": primary_char,
        "pov_type": pov_results[0]["pov_type"],
        "drifts": drifts,
        "confidence": avg_confidence,
    }


def format_pov_warning(drift_result: dict) -> str:
    """Format POV drift detection as warning text."""
    if drift_result.get("consistent", True):
        return ""

    lines = ["## ⚠️ CẢNH BÁO POV DRIFT:"]
    lines.append(f"POV chính: {drift_result.get('primary_pov', '?')}")

    for d in drift_result.get("drifts", [])[:3]:
        lines.append(
            f"- {d['position']}: {d['from_char']} → {d['to_char']}"
        )

    lines.append("Giữ nhất quán POV hoặc thêm chuyển cảnh rõ ràng.")
    return "\n".join(lines)


def validate_chapter_pov(
    llm: "LLMClient",
    chapter_content: str,
    characters: list["Character"],
    expected_pov: str | None = None,
    threshold: float = 0.7,
) -> tuple[bool, str]:
    """Main entry point for POV validation.

    Returns: (passed, warning_text)
    """
    result = detect_pov_drift(llm, chapter_content, characters, expected_pov)

    if result["consistent"] and result["confidence"] >= threshold:
        return True, ""

    warning = format_pov_warning(result)
    if result["drifts"]:
        logger.warning(
            "POV drift detected: %d shifts, confidence %.2f",
            len(result["drifts"]), result["confidence"]
        )

    return result["consistent"], warning
