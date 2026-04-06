"""Dialogue strategy — generates per-character speech guidance for chapter writing."""

import logging
from models.schemas import Character

logger = logging.getLogger(__name__)


def build_dialogue_context(characters: list[Character], genre: str) -> str:
    """Build dialogue guidance string for chapter writing prompt.

    Combines character speech patterns with genre-appropriate dialogue rules.
    """
    lines = []

    # Per-character speech patterns
    chars_with_patterns = [c for c in characters if c.speech_pattern]
    if chars_with_patterns:
        lines.append("PHONG CÁCH NÓI CHUYỆN TỪNG NHÂN VẬT:")
        for c in chars_with_patterns:
            lines.append(f"- {c.name}: {c.speech_pattern}")

    # General dialogue rules
    lines.append("")
    lines.append("QUY TẮC ĐỐI THOẠI:")
    lines.append("- Mỗi dòng đối thoại phải reveal tính cách HOẶC advance plot (tốt nhất là cả hai)")
    lines.append("- Tránh hội thoại exposition dump — show don't tell")
    lines.append("- Subtext > nói thẳng. Nhân vật ít khi nói chính xác điều họ nghĩ")
    lines.append("- Mỗi nhân vật có vocabulary, sentence length, và tone riêng")

    return "\n".join(lines)


def get_speech_pattern_reminder(character_name: str, characters: list[Character]) -> str:
    """Get speech pattern reminder for a specific character."""
    for c in characters:
        if c.name == character_name and c.speech_pattern:
            return f"[{c.name} nói theo style: {c.speech_pattern}]"
    return ""
