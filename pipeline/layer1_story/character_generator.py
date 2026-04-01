"""Character generation and state extraction functions."""

import logging
from typing import Optional, TYPE_CHECKING

from models.schemas import Character, CharacterState
from services import prompts

if TYPE_CHECKING:
    from services.llm_client import LLMClient

logger = logging.getLogger(__name__)


def _excerpt(content: str, max_chars: int = 4000) -> str:
    """Extract beginning + end of content for extraction prompts."""
    if len(content) <= max_chars:
        return content
    head = max_chars * 2 // 3
    tail = max_chars - head
    return content[:head] + "\n...\n" + content[-tail:]


def generate_characters(
    llm: "LLMClient",
    title: str,
    genre: str,
    idea: str,
    num_characters: int = 5,
    model: Optional[str] = None,
) -> list[Character]:
    """Generate character list from story premise."""
    result = llm.generate_json(
        system_prompt="Bạn là nhà văn chuyên xây dựng nhân vật. Trả về JSON.",
        user_prompt=prompts.GENERATE_CHARACTERS.format(
            genre=genre, title=title, idea=idea,
            num_characters=num_characters,
        ),
        model=model,
    )
    return [Character(**c) for c in result.get("characters", [])]


def extract_character_states(
    llm: "LLMClient",
    content: str,
    characters: list[Character],
) -> list[CharacterState]:
    """Extract character states from chapter content. Low temp, cheap call."""
    chars_text = ", ".join(c.name for c in characters)
    result = llm.generate_json(
        system_prompt="Trích xuất trạng thái nhân vật. Trả về JSON.",
        user_prompt=prompts.EXTRACT_CHARACTER_STATE.format(
            content=_excerpt(content), characters=chars_text,
        ),
        temperature=0.3,
        max_tokens=1000,
        model_tier="cheap",
    )
    states = []
    for s in result.get("character_states", []):
        try:
            states.append(CharacterState(**s))
        except Exception as e:
            logger.debug(f"Skipping invalid character state: {e}")
            continue
    return states
