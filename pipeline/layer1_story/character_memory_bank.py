"""Character emotional memory bank — tracks per-character emotional history across chapters."""

import logging
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from services.llm_client import LLMClient

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class EmotionalMemory(BaseModel):
    """Một ký ức cảm xúc của nhân vật từ một sự kiện cụ thể."""

    chapter: int
    trigger_event: str
    emotion: str
    intensity: float = Field(ge=0.0, le=1.0)
    target_character: str = ""  # Nhân vật gây ra cảm xúc này
    resolved: bool = False


class CharacterMemoryBank(BaseModel):
    """Ngân hàng ký ức cảm xúc của một nhân vật."""

    character_name: str
    emotional_memories: list[EmotionalMemory] = []
    persistent_mood_modifiers: list[str] = []  # e.g. "mất niềm tin sau phản bội"
    relationship_emotions: dict[str, str] = {}  # other_char -> feeling


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_EXTRACT_PROMPT = """Phân tích nội dung chương và trích xuất ký ức cảm xúc cho các nhân vật.

CHƯƠNG {chapter_num}:
{chapter_excerpt}

NHÂN VẬT CẦN PHÂN TÍCH: {characters}

Trả về JSON:
{{
  "characters": [
    {{
      "character_name": "tên nhân vật",
      "emotional_memories": [
        {{
          "chapter": {chapter_num},
          "trigger_event": "sự kiện kích hoạt (ngắn gọn)",
          "emotion": "tên cảm xúc",
          "intensity": 0.0-1.0,
          "target_character": "nhân vật gây ra (hoặc rỗng)",
          "resolved": false
        }}
      ],
      "persistent_mood_modifiers": ["mô tả tâm trạng kéo dài (nếu có)"],
      "relationship_emotions": {{"nhân_vật_kia": "cảm xúc hiện tại"}}
    }}
  ]
}}
CHỈ trả JSON. Tối đa 3 ký ức cảm xúc nổi bật nhất mỗi nhân vật."""


# ---------------------------------------------------------------------------
# Functions
# ---------------------------------------------------------------------------

def extract_emotional_memories(
    llm: "LLMClient",
    chapter_text: str,
    characters: list,
    chapter_num: int,
) -> dict[str, CharacterMemoryBank]:
    """Trích xuất ký ức cảm xúc từ nội dung chương. Một LLM call duy nhất (cheap tier).

    Args:
        llm: LLM client instance.
        chapter_text: Full chapter text to analyze.
        characters: List of character names (str) or Character objects with .name.
        chapter_num: Current chapter number.

    Returns:
        Dict keyed by character name → CharacterMemoryBank.
    """
    char_names = [
        c if isinstance(c, str) else getattr(c, "name", str(c))
        for c in characters
    ]
    if not char_names:
        return {}

    from services.text_utils import excerpt_text  # lazy import — avoids circular dep

    result = llm.generate_json(
        system_prompt="Bạn là chuyên gia tâm lý nhân vật. Trả về JSON bằng tiếng Việt.",
        user_prompt=_EXTRACT_PROMPT.format(
            chapter_num=chapter_num,
            chapter_excerpt=excerpt_text(chapter_text, max_chars=3000),
            characters=", ".join(char_names),
        ),
        temperature=0.3,
        max_tokens=1500,
        model_tier="cheap",
    )

    banks: dict[str, CharacterMemoryBank] = {}
    # Handle LLM returning list directly instead of {characters} dict
    char_data = result if isinstance(result, list) else result.get("characters", [])
    for entry in char_data:
        if not isinstance(entry, dict):
            continue
        name = entry.get("character_name", "").strip()
        if not name:
            continue
        try:
            memories = [
                EmotionalMemory(**m)
                for m in entry.get("emotional_memories", [])
                if isinstance(m, dict)
            ]
            banks[name] = CharacterMemoryBank(
                character_name=name,
                emotional_memories=memories,
                persistent_mood_modifiers=entry.get("persistent_mood_modifiers", []),
                relationship_emotions=entry.get("relationship_emotions", {}),
            )
        except Exception as exc:
            logger.warning("Bỏ qua memory bank lỗi cho '%s': %s", name, exc)

    return banks


def format_memories_for_prompt(
    banks: dict[str, CharacterMemoryBank],
    last_n: int = 3,
) -> str:
    """Định dạng ký ức cảm xúc thành bullet list gọn cho system prompt.

    Args:
        banks: Dict keyed by character name → CharacterMemoryBank.
        last_n: Number of most recent memories to show per character.

    Returns:
        Compact multi-line string, one bullet per memory.
    """
    if not banks:
        return "Không có ký ức cảm xúc."

    lines: list[str] = []
    for bank in banks.values():
        recent = bank.emotional_memories[-last_n:] if bank.emotional_memories else []
        for mem in recent:
            target = f", với {mem.target_character}" if mem.target_character else ""
            lines.append(
                f"• {bank.character_name}: {mem.emotion}{target}"
                f" (từ Ch{mem.chapter}, trigger: {mem.trigger_event})"
            )
        if bank.persistent_mood_modifiers:
            for mod in bank.persistent_mood_modifiers:
                lines.append(f"  → {bank.character_name} [tâm trạng]: {mod}")

    return "\n".join(lines) if lines else "Không có ký ức cảm xúc."


def merge_memory_banks(
    existing: dict[str, CharacterMemoryBank],
    new_banks: dict[str, CharacterMemoryBank],
) -> dict[str, CharacterMemoryBank]:
    """Merge new extractions into existing memory banks. Upsert by character name.

    Args:
        existing: Current story-state memory banks.
        new_banks: Newly extracted banks for the latest chapter.

    Returns:
        Updated dict (existing is mutated in-place and returned).
    """
    for name, new_bank in new_banks.items():
        if name not in existing:
            existing[name] = new_bank
        else:
            bank = existing[name]
            bank.emotional_memories.extend(new_bank.emotional_memories)
            # Merge mood modifiers — deduplicate
            seen = set(bank.persistent_mood_modifiers)
            for mod in new_bank.persistent_mood_modifiers:
                if mod not in seen:
                    bank.persistent_mood_modifiers.append(mod)
                    seen.add(mod)
            # Overwrite relationship emotions with latest values
            bank.relationship_emotions.update(new_bank.relationship_emotions)
    return existing
