"""Chapter writing functions: prompt building, streaming, extraction."""

import logging
from typing import Optional, TYPE_CHECKING

from models.schemas import (
    Character, WorldSetting, ChapterOutline, Chapter, PlotEvent, StoryContext,
    count_words,
)
from services import prompts
from services.adaptive_prompts import build_adaptive_write_prompt
from services.text_utils import excerpt_text

if TYPE_CHECKING:
    from services.llm_client import LLMClient

logger = logging.getLogger(__name__)


def excerpt(content: str, max_chars: int = 4000) -> str:
    """Extract beginning + end of content for extraction prompts."""
    return excerpt_text(content, max_chars=max_chars)


def format_context(
    context: StoryContext,
    bible_context: str = "",
    full_chapter_texts: Optional[list[str]] = None,
) -> str:
    """Format StoryContext into a prompt string.

    Long-context mode: includes full chapter texts.
    Bible context mode: uses story bible instead of rolling summaries.
    """
    if full_chapter_texts:
        parts = ["## Toàn bộ nội dung các chương trước:"]
        for i, text in enumerate(full_chapter_texts, start=1):
            parts.append(f"### Chương {i}:\n{text}")
        if context and context.character_states:
            states_text = "\n".join(
                f"- {s.name}: tâm trạng={s.mood}, vị trí={s.arc_position}, "
                f"hành động cuối={s.last_action}"
                for s in context.character_states
            )
            parts.append(f"## Trạng thái nhân vật hiện tại:\n{states_text}")
        if context and context.plot_events:
            events_text = "\n".join(
                f"- Ch.{e.chapter_number}: {e.event}" for e in context.plot_events[-10:]
            )
            parts.append(f"## Sự kiện quan trọng đã xảy ra:\n{events_text}")
        return "\n\n".join(parts)

    if not context or (not context.recent_summaries and not context.character_states):
        return bible_context or "Đây là chương đầu tiên."

    if bible_context:
        return bible_context

    parts = []
    if context.recent_summaries:
        parts.append("## Bối cảnh các chương trước:\n" + "\n---\n".join(context.recent_summaries))
    if context.character_states:
        states_text = "\n".join(
            f"- {s.name}: tâm trạng={s.mood}, vị trí={s.arc_position}, "
            f"hành động cuối={s.last_action}"
            for s in context.character_states
        )
        parts.append(f"## Trạng thái nhân vật hiện tại:\n{states_text}")
    if context.plot_events:
        events_text = "\n".join(
            f"- Ch.{e.chapter_number}: {e.event}" for e in context.plot_events[-10:]
        )
        parts.append(f"## Sự kiện quan trọng đã xảy ra:\n{events_text}")
    return "\n\n".join(parts)


def build_chapter_prompt(
    config,
    title: str,
    genre: str,
    style: str,
    characters: list[Character],
    world: WorldSetting,
    outline: ChapterOutline,
    word_count: int,
    context: Optional[StoryContext] = None,
    previous_summary: str = "",
    bible_context: str = "",
    full_chapter_texts: Optional[list[str]] = None,
    rag_kb=None,
    knowledge_graph=None,
) -> tuple[str, str]:
    """Build system/user prompts for chapter writing. Returns (system_prompt, user_prompt)."""
    chars_text = "\n".join(
        f"- {c.name} ({c.role}): {c.personality}\n  Tiểu sử: {c.background}"
        for c in characters
    )
    outline_text = (
        f"Tóm tắt: {outline.summary}\n"
        f"Sự kiện chính: {', '.join(outline.key_events)}\n"
        f"Cảm xúc: {outline.emotional_arc}"
    )
    context_text = (
        format_context(context, bible_context, full_chapter_texts)
        if context
        else (bible_context or previous_summary or "Đây là chương đầu tiên.")
    )

    # Append RAG context if enabled
    if config.pipeline.rag_enabled and rag_kb is not None and rag_kb.is_available:
        query_text = f"chapter {outline.chapter_number} {outline.summary}"
        rag_docs = rag_kb.query(query_text, n_results=3)
        if rag_docs:
            rag_section = prompts.RAG_CONTEXT_SECTION.format(
                rag_context="\n---\n".join(rag_docs)
            )
            context_text = context_text + "\n\n" + rag_section

    # Knowledge graph entity context (gated behind rag_enabled)
    if config.pipeline.rag_enabled and knowledge_graph is not None:
        try:
            char_names = [c.name for c in characters]
            entity_ctx = knowledge_graph.get_entity_context(char_names)
            if entity_ctx:
                context_text += "\n\n## Character Relationships:\n" + entity_ctx
        except Exception as e:
            logger.debug(f"Knowledge graph unavailable: {e}")

    sys_prompt = (
        f"Bạn là tiểu thuyết gia tài năng viết truyện {genre} bằng tiếng Việt. "
        f"BẮT BUỘC: Toàn bộ output phải viết bằng tiếng Việt, không được dùng ngôn ngữ khác."
    )
    user_prompt = prompts.WRITE_CHAPTER.format(
        genre=genre, style=style, title=title,
        world=f"{world.name}: {world.description}",
        characters=chars_text,
        chapter_number=outline.chapter_number,
        chapter_title=outline.title,
        outline=outline_text,
        previous_summary=context_text,
        word_count=word_count,
    )
    user_prompt = build_adaptive_write_prompt(user_prompt, genre)
    # Reinforce Vietnamese at end of prompt (after all context) to prevent
    # language drift in later chapters where context is very long
    user_prompt += "\n\n[NHẮC LẠI: Viết hoàn toàn bằng tiếng Việt. Không dùng tiếng Anh hay ngôn ngữ khác.]"
    return sys_prompt, user_prompt


def write_chapter(
    llm: "LLMClient",
    config,
    title: str,
    genre: str,
    style: str,
    characters: list[Character],
    world: WorldSetting,
    outline: ChapterOutline,
    previous_summary: str = "",
    word_count: int = 2000,
    context: Optional[StoryContext] = None,
    rag_kb=None,
    model: Optional[str] = None,
) -> Chapter:
    """Write a single chapter (non-streaming)."""
    sys_prompt, user_prompt = build_chapter_prompt(
        config, title, genre, style, characters, world, outline,
        word_count, context, previous_summary, rag_kb=rag_kb,
    )
    content = llm.generate(
        system_prompt=sys_prompt,
        user_prompt=user_prompt,
        max_tokens=8192,
        model=model,
    )
    return Chapter(
        chapter_number=outline.chapter_number,
        title=outline.title,
        content=content,
        word_count=count_words(content),
    )


def write_chapter_stream(
    llm: "LLMClient",
    config,
    title: str,
    genre: str,
    style: str,
    characters: list[Character],
    world: WorldSetting,
    outline: ChapterOutline,
    word_count: int = 2000,
    context: Optional[StoryContext] = None,
    stream_callback=None,
    rag_kb=None,
    model: Optional[str] = None,
) -> Chapter:
    """Write chapter with streaming. Calls stream_callback(partial_text) each chunk."""
    sys_prompt, user_prompt = build_chapter_prompt(
        config, title, genre, style, characters, world, outline,
        word_count, context, rag_kb=rag_kb,
    )

    full_content = ""
    try:
        for token in llm.generate_stream(
            system_prompt=sys_prompt,
            user_prompt=user_prompt,
            max_tokens=8192,
            model=model,
        ):
            full_content += token
            if stream_callback:
                stream_callback(full_content)
    except Exception as e:
        logger.warning(f"Stream failed, falling back to generate: {e}")
        return write_chapter(
            llm, config, title, genre, style, characters, world,
            outline, word_count=word_count, context=context, rag_kb=rag_kb,
            model=model,
        )

    return Chapter(
        chapter_number=outline.chapter_number,
        title=outline.title,
        content=full_content,
        word_count=count_words(full_content),
    )


def summarize_chapter(llm: "LLMClient", content: str) -> str:
    """Summarize a chapter for use as context in the next chapter."""
    return llm.generate(
        system_prompt="Bạn là trợ lý tóm tắt nội dung. BẮT BUỘC viết bằng tiếng Việt.",
        user_prompt=prompts.SUMMARIZE_CHAPTER.format(content=content[:3000])
        + "\n\n[Tóm tắt bằng tiếng Việt.]",
        temperature=0.3,
        max_tokens=500,
        model_tier="cheap",
    )


def extract_plot_events(
    llm: "LLMClient",
    content: str,
    chapter_number: int,
) -> list[PlotEvent]:
    """Extract key plot events from chapter content."""
    result = llm.generate_json(
        system_prompt="Trích xuất sự kiện cốt truyện. Trả về JSON bằng tiếng Việt.",
        user_prompt=prompts.EXTRACT_PLOT_EVENTS.format(
            content=excerpt(content), chapter_number=chapter_number,
        ),
        temperature=0.3,
        max_tokens=1000,
        model_tier="cheap",
    )
    events = []
    for e in result.get("events", []):
        try:
            events.append(PlotEvent(chapter_number=chapter_number, **e))
        except Exception as ex:
            logger.debug(f"Skipping invalid plot event: {ex}")
            continue
    return events
