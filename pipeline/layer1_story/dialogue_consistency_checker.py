"""Dialogue consistency checker — validates character voice across chapters.

Bug #6: Voice profiles are extracted but not enforced.
This module provides post-write validation of dialogue consistency.
"""

import logging
import re
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from services.llm_client import LLMClient
    from models.schemas import Character

logger = logging.getLogger(__name__)

# Regex to extract dialogue
DIALOGUE_PATTERN = re.compile(r'[""「]([^""」]+)[""」]')
SPEAKER_PATTERN = re.compile(r'(\w+)\s*(?:nói|hỏi|đáp|thì thầm|gào|la|cười|trả lời)')


def extract_dialogue_by_character(
    content: str,
    characters: list["Character"],
) -> dict[str, list[str]]:
    """Extract dialogue lines attributed to each character.

    Returns: {character_name: [dialogue_line1, dialogue_line2, ...]}
    """
    char_names = {c.name.lower(): c.name for c in characters}
    result = {c.name: [] for c in characters}

    lines = content.split('\n')
    current_speaker = None

    for line in lines:
        line_lower = line.lower()

        # Check for speaker attribution
        for name_lower, name in char_names.items():
            if name_lower in line_lower:
                speaker_match = SPEAKER_PATTERN.search(line_lower)
                if speaker_match:
                    current_speaker = name
                    break

        # Extract dialogue
        dialogues = DIALOGUE_PATTERN.findall(line)
        if dialogues and current_speaker:
            for d in dialogues:
                if len(d) > 5:  # Skip very short fragments
                    result[current_speaker].append(d)

    return result


def check_voice_consistency(
    llm: "LLMClient",
    chapter_content: str,
    characters: list["Character"],
    model: Optional[str] = None,
) -> dict:
    """Check dialogue consistency against character voice profiles.

    Returns: {
        'consistent': bool,
        'violations': [{character, dialogue, expected_pattern, issue}],
        'score': float (0-1)
    }
    """
    dialogue_by_char = extract_dialogue_by_character(chapter_content, characters)

    # Filter to characters with voice profiles
    chars_with_voice = [
        c for c in characters
        if getattr(c, 'speech_pattern', '') or getattr(c, 'voice_profile', '')
    ]

    if not chars_with_voice:
        return {'consistent': True, 'violations': [], 'score': 1.0}

    violations = []
    total_checked = 0

    for char in chars_with_voice:
        dialogues = dialogue_by_char.get(char.name, [])
        if not dialogues:
            continue

        voice_profile = getattr(char, 'speech_pattern', '') or getattr(char, 'voice_profile', '')

        # Check each dialogue sample (max 5 per character)
        for dialogue in dialogues[:5]:
            total_checked += 1
            try:
                result = llm.generate_json(
                    system_prompt="Kiểm tra dialogue có khớp voice profile. Trả JSON.",
                    user_prompt=f"""Voice profile của {char.name}: {voice_profile}

Dialogue: "{dialogue}"

Đánh giá dialogue này có khớp voice profile không?
{{"match": true/false, "confidence": 0.0-1.0, "issue": "mô tả vấn đề nếu có"}}""",
                    temperature=0.1,
                    max_tokens=200,
                    model_tier="cheap",
                )

                if not result.get('match', True):
                    violations.append({
                        'character': char.name,
                        'dialogue': dialogue[:100],
                        'expected_pattern': voice_profile[:100],
                        'issue': result.get('issue', 'Không khớp voice profile'),
                        'confidence': result.get('confidence', 0.5),
                    })
            except Exception as e:
                logger.debug(f"Voice check failed for {char.name}: {e}")

    score = 1.0 - (len(violations) / max(total_checked, 1))

    return {
        'consistent': len(violations) == 0,
        'violations': violations,
        'score': score,
        'total_checked': total_checked,
    }


def format_voice_warnings(check_result: dict) -> str:
    """Format voice consistency issues as warning text."""
    if check_result.get('consistent', True):
        return ""

    lines = ["## ⚠️ CẢNH BÁO GIỌNG NÓI NHÂN VẬT:"]
    for v in check_result.get('violations', [])[:5]:
        lines.append(
            f"- {v['character']}: \"{v['dialogue'][:50]}...\" → {v['issue']}"
        )
    lines.append("PHẢI duy trì voice profile đã định nghĩa cho mỗi nhân vật.")
    return "\n".join(lines)


def dialogue_consistency_check(
    llm: "LLMClient",
    chapter_content: str,
    characters: list["Character"],
    model: Optional[str] = None,
    threshold: float = 0.7,
) -> tuple[bool, str]:
    """Main entry point for dialogue consistency check.

    Returns: (passed, warning_text)
    """
    result = check_voice_consistency(llm, chapter_content, characters, model)

    if result['score'] >= threshold:
        return True, ""

    warning = format_voice_warnings(result)
    logger.warning(
        "Dialogue consistency score %.2f < %.2f threshold, %d violations",
        result['score'], threshold, len(result['violations'])
    )
    return False, warning
