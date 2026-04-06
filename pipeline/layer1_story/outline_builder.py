"""Outline and world-building generation functions."""

import logging
from typing import Optional, TYPE_CHECKING

from models.schemas import Character, WorldSetting, ChapterOutline
from services import prompts

if TYPE_CHECKING:
    from services.llm_client import LLMClient

logger = logging.getLogger(__name__)


def suggest_titles(
    llm: "LLMClient",
    genre: str,
    requirements: str = "",
    model: Optional[str] = None,
) -> list[str]:
    """Suggest story titles for a given genre."""
    result = llm.generate_json(
        system_prompt="Bạn là nhà văn sáng tạo. BẮT BUỘC viết bằng tiếng Việt. Trả về JSON.",
        user_prompt=prompts.SUGGEST_TITLE.format(
            genre=genre, requirements=requirements
        ),
        model=model,
    )
    return result.get("titles", [])


def generate_world(
    llm: "LLMClient",
    config,
    title: str,
    genre: str,
    characters: list[Character],
    rag_kb=None,
    model: Optional[str] = None,
) -> WorldSetting:
    """Generate world setting, optionally injecting RAG context."""
    chars_text = "\n".join(
        f"- {c.name} ({c.role}): {c.personality}" for c in characters
    )
    world_prompt = prompts.GENERATE_WORLD.format(
        genre=genre, title=title, characters=chars_text,
    )

    # Prepend RAG context if enabled
    if config.pipeline.rag_enabled and rag_kb is not None and rag_kb.is_available:
        rag_docs = rag_kb.query(f"world setting {genre} {title}", n_results=3)
        if rag_docs:
            rag_section = prompts.RAG_CONTEXT_SECTION.format(
                rag_context="\n---\n".join(rag_docs)
            )
            world_prompt = rag_section + world_prompt

    result = llm.generate_json(
        system_prompt="Bạn là kiến trúc sư thế giới. BẮT BUỘC viết bằng tiếng Việt. Trả về JSON.",
        user_prompt=world_prompt,
        model=model,
    )
    return WorldSetting(**result)


def generate_outline(
    llm: "LLMClient",
    title: str,
    genre: str,
    characters: list[Character],
    world: WorldSetting,
    idea: str,
    num_chapters: int = 10,
    model: Optional[str] = None,
    macro_arcs=None,  # NEW: list[MacroArc] or None
) -> tuple[str, list[ChapterOutline]]:
    """Generate story outline. Returns (synopsis, outlines)."""
    chars_text = "\n".join(
        f"- {c.name} ({c.role}): {c.personality}, Động lực: {c.motivation}"
        for c in characters
    )
    user_prompt = prompts.GENERATE_OUTLINE.format(
        genre=genre, title=title, characters=chars_text,
        world=f"{world.name}: {world.description}",
        idea=idea, num_chapters=num_chapters,
    )
    if macro_arcs:
        try:
            from pipeline.layer1_story.macro_outline_builder import format_arcs_for_prompt
            arcs_context = (
                "## CẤU TRÚC MACRO ARC (cần bám sát khi tạo dàn ý):\n"
                + format_arcs_for_prompt(macro_arcs)
                + "\n\n"
            )
            user_prompt = arcs_context + user_prompt
        except Exception as e:
            logger.warning("Failed to inject macro arcs into outline prompt: %s", e)
    result = llm.generate_json(
        system_prompt="Bạn là biên kịch tài năng. BẮT BUỘC viết bằng tiếng Việt. Trả về JSON.",
        user_prompt=user_prompt,
        temperature=0.9,
        model=model,
    )
    synopsis = result.get("synopsis", "")
    outlines = [ChapterOutline(**o) for o in result.get("outlines", [])]
    return synopsis, outlines
