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

    # Validate outline count matches requested num_chapters
    if len(outlines) < num_chapters:
        logger.warning(
            "LLM returned %d outlines but %d requested. Requesting missing chapters...",
            len(outlines), num_chapters,
        )
        outlines = _fill_missing_outlines(
            llm, outlines, num_chapters, title, genre, characters, world, idea, synopsis, model,
        )
    elif len(outlines) > num_chapters:
        logger.warning(
            "LLM returned %d outlines but only %d requested. Trimming...",
            len(outlines), num_chapters,
        )
        outlines = outlines[:num_chapters]

    return synopsis, outlines


def _fill_missing_outlines(
    llm: "LLMClient",
    existing_outlines: list[ChapterOutline],
    num_chapters: int,
    title: str,
    genre: str,
    characters: list[Character],
    world: WorldSetting,
    idea: str,
    synopsis: str,
    model: Optional[str] = None,
) -> list[ChapterOutline]:
    """Fill in missing chapter outlines when LLM returns fewer than requested."""
    existing_nums = {o.chapter_number for o in existing_outlines}
    missing_nums = [i for i in range(1, num_chapters + 1) if i not in existing_nums]

    if not missing_nums:
        return existing_outlines

    chars_text = "\n".join(
        f"- {c.name} ({c.role}): {c.personality}, Động lực: {c.motivation}"
        for c in characters
    )

    existing_text = "\n".join(
        f"Chương {o.chapter_number}: {o.title} - {o.summary}"
        for o in sorted(existing_outlines, key=lambda x: x.chapter_number)
    )

    fill_prompt = f"""Bạn là biên kịch chuyên xây dựng cốt truyện {genre}.
Tiêu đề: {title}
Tóm tắt: {synopsis}
Nhân vật: {chars_text}
Bối cảnh: {world.name}: {world.description}
Ý tưởng: {idea}

Các chương đã có:
{existing_text}

Hãy tạo dàn ý cho các chương còn thiếu: {', '.join(f'chương {n}' for n in missing_nums)}
BẮT BUỘC: Viết bằng tiếng Việt. Đảm bảo logic với các chương đã có.

Trả về JSON:
{{
  "outlines": [
    {{"chapter_number": N, "title": "...", "summary": "...", "key_events": [...], "characters_involved": [...], "emotional_arc": "...", "pacing_type": "...", "arc_id": 1, "foreshadowing_plants": [...], "payoff_references": [...]}}
  ]
}}"""

    try:
        result = llm.generate_json(
            system_prompt="Bạn là biên kịch tài năng. BẮT BUỘC viết bằng tiếng Việt. Trả về JSON.",
            user_prompt=fill_prompt,
            temperature=0.8,
            model=model,
        )
        new_outlines = [ChapterOutline(**o) for o in result.get("outlines", [])]
        all_outlines = list(existing_outlines) + new_outlines
        all_outlines.sort(key=lambda x: x.chapter_number)

        # Final check: ensure we have all chapters
        final_nums = {o.chapter_number for o in all_outlines}
        still_missing = [i for i in range(1, num_chapters + 1) if i not in final_nums]
        if still_missing:
            logger.warning("Still missing chapters after fill: %s. Creating placeholder outlines.", still_missing)
            for ch_num in still_missing:
                all_outlines.append(ChapterOutline(
                    chapter_number=ch_num,
                    title=f"Chương {ch_num}",
                    summary=f"Tiếp tục câu chuyện (chương {ch_num})",
                    key_events=[],
                    characters_involved=[c.name for c in characters[:2]],
                    emotional_arc="rising",
                    pacing_type="rising",
                ))
            all_outlines.sort(key=lambda x: x.chapter_number)

        return all_outlines[:num_chapters]
    except Exception as e:
        logger.error("Failed to fill missing outlines: %s. Creating placeholders.", e)
        all_outlines = list(existing_outlines)
        for ch_num in missing_nums:
            all_outlines.append(ChapterOutline(
                chapter_number=ch_num,
                title=f"Chương {ch_num}",
                summary=f"Tiếp tục câu chuyện (chương {ch_num})",
                key_events=[],
                characters_involved=[c.name for c in characters[:2]],
                emotional_arc="rising",
                pacing_type="rising",
            ))
        all_outlines.sort(key=lambda x: x.chapter_number)
        return all_outlines[:num_chapters]
