"""Validate that arc waypoints are actually executed in chapter content.

Arc waypoints define expected character development stages. This module checks
if the written chapter content reflects those stages, catching drift between
planned arc and actual execution.

Zero-cost heuristics first, optional LLM validation for ambiguous cases.
"""

import logging
import re
from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

from models.schemas import Character, Chapter

if TYPE_CHECKING:
    from services.llm_client import LLMClient

logger = logging.getLogger(__name__)


@dataclass
class ArcValidationResult:
    """Result of validating a character's arc execution in a chapter."""
    character: str
    chapter_number: int
    expected_stage: str
    expected_emotion: str
    found: bool
    confidence: float  # 0.0-1.0
    evidence: str  # snippet or explanation
    severity: str  # "ok", "warning", "critical"


# Emotion keyword groups for heuristic detection
_EMOTION_KEYWORDS = {
    "sợ hãi": ["sợ", "lo sợ", "khiếp", "hoảng", "run rẩy", "e ngại", "kinh hãi"],
    "tức giận": ["giận", "tức", "phẫn nộ", "căm hận", "bực", "điên tiết", "cuồng nộ"],
    "buồn": ["buồn", "đau khổ", "sầu", "tuyệt vọng", "bi thương", "thất vọng", "chán nản"],
    "vui": ["vui", "hạnh phúc", "hân hoan", "phấn khởi", "mừng", "hớn hở", "sung sướng"],
    "can đảm": ["can đảm", "dũng cảm", "mạnh mẽ", "quyết tâm", "kiên định", "bất khuất"],
    "do dự": ["do dự", "phân vân", "lưỡng lự", "ngập ngừng", "không quyết", "bối rối"],
    "cô đấp": ["cố chấp", "khăng khăng", "bướng bỉnh", "ngoan cố", "ương ngạnh"],
    "yêu": ["yêu", "thương", "mến", "si mê", "đắm đuối", "trìu mến"],
    "hối hận": ["hối hận", "ân hận", "day dứt", "tự trách", "hối tiếc", "ray rứt"],
    "quyết tâm": ["quyết tâm", "kiên quyết", "dứt khoát", "cương quyết", "bất di bất dịch"],
    "phủ nhận": ["phủ nhận", "từ chối", "không chấp nhận", "chối bỏ", "khước từ"],
    "chấp nhận": ["chấp nhận", "đón nhận", "tiếp nhận", "cam chịu", "thuận theo"],
}

# Stage keyword groups
_STAGE_KEYWORDS = {
    "phủ nhận": ["phủ nhận", "từ chối", "không tin", "bác bỏ", "chối"],
    "khủng hoảng": ["khủng hoảng", "sụp đổ", "tan vỡ", "đổ vỡ", "hoảng loạn"],
    "thức tỉnh": ["thức tỉnh", "nhận ra", "hiểu ra", "ngộ ra", "giác ngộ"],
    "chuyển biến": ["thay đổi", "chuyển biến", "biến đổi", "lột xác"],
    "trưởng thành": ["trưởng thành", "lớn lên", "chín chắn", "già dặn"],
    "hy sinh": ["hy sinh", "từ bỏ", "buông bỏ", "cống hiến"],
    "chiến đấu": ["chiến đấu", "đấu tranh", "chống lại", "kháng cự"],
    "đối mặt": ["đối mặt", "đối diện", "giáp mặt", "trực diện"],
    "trốn chạy": ["trốn chạy", "bỏ trốn", "lẩn tránh", "né tránh"],
}


def _find_character_mentions(content: str, char_name: str) -> list[str]:
    """Extract sentences mentioning a character."""
    sentences = re.split(r'[.!?。]\s*', content)
    mentions = []
    name_lower = char_name.lower()
    name_parts = name_lower.split()
    for sent in sentences:
        sent_lower = sent.lower()
        if name_lower in sent_lower or any(p in sent_lower for p in name_parts if len(p) > 2):
            mentions.append(sent.strip())
    return mentions[:20]  # Cap for performance


def _heuristic_emotion_match(text: str, expected_emotion: str) -> tuple[bool, float, str]:
    """Check if text contains expected emotion keywords. Returns (found, confidence, evidence)."""
    text_lower = text.lower()
    expected_lower = expected_emotion.lower()

    # Direct keyword groups
    for emotion_key, keywords in _EMOTION_KEYWORDS.items():
        if emotion_key in expected_lower or expected_lower in emotion_key:
            for kw in keywords:
                if kw in text_lower:
                    idx = text_lower.find(kw)
                    start = max(0, idx - 30)
                    end = min(len(text), idx + len(kw) + 30)
                    return True, 0.7, text[start:end].strip()

    # Partial match on expected emotion directly
    emotion_parts = expected_lower.replace(",", " ").replace("/", " ").split()
    for part in emotion_parts:
        part = part.strip()
        if len(part) > 2 and part in text_lower:
            idx = text_lower.find(part)
            start = max(0, idx - 30)
            end = min(len(text), idx + len(part) + 30)
            return True, 0.6, text[start:end].strip()

    return False, 0.0, ""


def _heuristic_stage_match(text: str, expected_stage: str) -> tuple[bool, float, str]:
    """Check if text reflects expected arc stage. Returns (found, confidence, evidence)."""
    text_lower = text.lower()
    expected_lower = expected_stage.lower()

    # Direct keyword groups
    for stage_key, keywords in _STAGE_KEYWORDS.items():
        if stage_key in expected_lower or expected_lower in stage_key:
            for kw in keywords:
                if kw in text_lower:
                    idx = text_lower.find(kw)
                    start = max(0, idx - 40)
                    end = min(len(text), idx + len(kw) + 40)
                    return True, 0.7, text[start:end].strip()

    # Direct stage name match
    stage_parts = expected_lower.replace(",", " ").replace("/", " ").split()
    for part in stage_parts:
        part = part.strip()
        if len(part) > 2 and part in text_lower:
            idx = text_lower.find(part)
            start = max(0, idx - 40)
            end = min(len(text), idx + len(part) + 40)
            return True, 0.6, text[start:end].strip()

    return False, 0.0, ""


def validate_arc_execution_heuristic(
    chapter: Chapter,
    character: Character,
    chapter_number: int,
) -> Optional[ArcValidationResult]:
    """Validate arc execution using zero-cost heuristics only.

    Returns None if character has no waypoint for this chapter.
    """
    from pipeline.layer1_story.arc_waypoint_generator import get_expected_stage

    waypoint = get_expected_stage(character, chapter_number)
    if not waypoint:
        return None

    # Find character mentions
    mentions = _find_character_mentions(chapter.content, character.name)
    if not mentions:
        return ArcValidationResult(
            character=character.name,
            chapter_number=chapter_number,
            expected_stage=waypoint.stage_name,
            expected_emotion=waypoint.emotional_state,
            found=False,
            confidence=0.0,
            evidence="Nhân vật không xuất hiện trong chương",
            severity="warning",
        )

    combined_text = " ".join(mentions)

    # Check stage match
    stage_found, stage_conf, stage_evidence = _heuristic_stage_match(
        combined_text, waypoint.stage_name
    )

    # Check emotion match
    emotion_found, emotion_conf, emotion_evidence = _heuristic_emotion_match(
        combined_text, waypoint.emotional_state
    )

    # Combine results
    found = stage_found or emotion_found
    confidence = max(stage_conf, emotion_conf)
    evidence = stage_evidence or emotion_evidence

    # Determine severity
    if found and confidence >= 0.6:
        severity = "ok"
    elif found and confidence >= 0.4:
        severity = "warning"
    elif not found and waypoint.progress_pct >= 0.8:
        # Critical arc moments (climax, resolution) need validation
        severity = "critical"
    else:
        severity = "warning"

    return ArcValidationResult(
        character=character.name,
        chapter_number=chapter_number,
        expected_stage=waypoint.stage_name,
        expected_emotion=waypoint.emotional_state,
        found=found,
        confidence=confidence,
        evidence=evidence or "Không tìm thấy bằng chứng rõ ràng",
        severity=severity,
    )


_LLM_PROMPT = """\
Kiểm tra xem đoạn văn có thể hiện giai đoạn arc của nhân vật không.

Nhân vật: {character}
Giai đoạn arc mong đợi: {stage_name}
Cảm xúc mong đợi: {emotional_state}
Mô tả: {description}

Đoạn văn (các câu có nhắc đến nhân vật):
{text}

Trả về JSON:
{{
  "found": true/false,
  "confidence": 0.0-1.0,
  "evidence": "trích dẫn ngắn từ văn bản",
  "reasoning": "giải thích ngắn gọn"
}}"""


def validate_arc_execution_llm(
    llm: "LLMClient",
    chapter: Chapter,
    character: Character,
    chapter_number: int,
    model: Optional[str] = None,
) -> Optional[ArcValidationResult]:
    """Validate arc execution using LLM for higher accuracy.

    Use for critical chapters (climax, arc boundaries) or when heuristic is uncertain.
    """
    from pipeline.layer1_story.arc_waypoint_generator import get_expected_stage

    waypoint = get_expected_stage(character, chapter_number)
    if not waypoint:
        return None

    mentions = _find_character_mentions(chapter.content, character.name)
    if not mentions:
        return ArcValidationResult(
            character=character.name,
            chapter_number=chapter_number,
            expected_stage=waypoint.stage_name,
            expected_emotion=waypoint.emotional_state,
            found=False,
            confidence=0.0,
            evidence="Nhân vật không xuất hiện trong chương",
            severity="warning",
        )

    combined_text = " ".join(mentions[:10])  # Cap for token efficiency

    prompt = _LLM_PROMPT.format(
        character=character.name,
        stage_name=waypoint.stage_name,
        emotional_state=waypoint.emotional_state,
        description=waypoint.description,
        text=combined_text[:2000],
    )

    try:
        result = llm.generate_json(
            system_prompt="Bạn là chuyên gia phân tích phát triển nhân vật. Trả về JSON.",
            user_prompt=prompt,
            temperature=0.2,
            max_tokens=300,
            model=model,
            model_tier="cheap",
        )

        found = bool(result.get("found", False))
        confidence = float(result.get("confidence", 0.5))
        evidence = str(result.get("evidence", ""))[:200]

        if found and confidence >= 0.6:
            severity = "ok"
        elif found and confidence >= 0.4:
            severity = "warning"
        elif not found and waypoint.progress_pct >= 0.8:
            severity = "critical"
        else:
            severity = "warning"

        return ArcValidationResult(
            character=character.name,
            chapter_number=chapter_number,
            expected_stage=waypoint.stage_name,
            expected_emotion=waypoint.emotional_state,
            found=found,
            confidence=confidence,
            evidence=evidence,
            severity=severity,
        )
    except Exception as e:
        logger.warning("Arc LLM validation failed for %s ch%d: %s", character.name, chapter_number, e)
        # Fallback to heuristic
        return validate_arc_execution_heuristic(chapter, character, chapter_number)


def validate_all_arcs(
    chapter: Chapter,
    characters: list[Character],
    chapter_number: int,
    llm: Optional["LLMClient"] = None,
    use_llm_for_critical: bool = True,
) -> list[ArcValidationResult]:
    """Validate arc execution for all characters in a chapter.

    Uses heuristics by default, LLM only for critical/ambiguous cases.
    """
    results = []

    for char in characters:
        # Start with heuristic
        result = validate_arc_execution_heuristic(chapter, char, chapter_number)
        if result is None:
            continue

        # Escalate to LLM if critical and ambiguous
        if (
            use_llm_for_critical
            and llm
            and result.severity == "critical"
            and result.confidence < 0.5
        ):
            llm_result = validate_arc_execution_llm(llm, chapter, char, chapter_number)
            if llm_result:
                result = llm_result

        results.append(result)

    return results


def format_arc_warnings(results: list[ArcValidationResult]) -> list[str]:
    """Format validation results as warning strings for logging/UI."""
    warnings = []
    for r in results:
        if r.severity == "ok":
            continue
        prefix = "⚠️" if r.severity == "warning" else "🚨"
        status = "không tìm thấy" if not r.found else f"yếu ({r.confidence:.0%})"
        warnings.append(
            f"{prefix} Ch{r.chapter_number} {r.character}: "
            f"arc '{r.expected_stage}' {status}"
        )
    return warnings


def get_arc_drift_summary(
    all_results: list[ArcValidationResult],
) -> dict:
    """Aggregate arc validation results across chapters for reporting."""
    total = len(all_results)
    if total == 0:
        return {"total": 0, "ok": 0, "warning": 0, "critical": 0, "drift_rate": 0.0}

    ok = sum(1 for r in all_results if r.severity == "ok")
    warning = sum(1 for r in all_results if r.severity == "warning")
    critical = sum(1 for r in all_results if r.severity == "critical")

    drift_rate = (warning + critical) / total

    return {
        "total": total,
        "ok": ok,
        "warning": warning,
        "critical": critical,
        "drift_rate": drift_rate,
        "by_character": _group_by_character(all_results),
    }


def _group_by_character(results: list[ArcValidationResult]) -> dict:
    """Group results by character for detailed reporting."""
    grouped: dict[str, list[dict]] = {}
    for r in results:
        if r.character not in grouped:
            grouped[r.character] = []
        grouped[r.character].append({
            "chapter": r.chapter_number,
            "stage": r.expected_stage,
            "found": r.found,
            "severity": r.severity,
        })
    return grouped
