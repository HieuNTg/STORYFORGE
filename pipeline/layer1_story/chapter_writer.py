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


def _append_consistency_context(parts: list[str], context: StoryContext) -> None:
    """Append timeline, location, arc drift, and name warnings to prompt parts."""
    if context.timeline_positions:
        tl_lines = [f"- {name}: {tl}" for name, tl in context.timeline_positions.items()]
        parts.append("## Mốc thời gian hiện tại:\n" + "\n".join(tl_lines))
    if context.character_locations:
        loc_lines = [f"- {name}: {loc}" for name, loc in context.character_locations.items()]
        parts.append("## Vị trí nhân vật hiện tại:\n" + "\n".join(loc_lines))
    if context.arc_drift_warnings:
        drift_text = "\n".join(context.arc_drift_warnings)
        parts.append(
            f"## [CẢNH BÁO ARC NHÂN VẬT - PHẢI ĐIỀU CHỈNH]:\n{drift_text}\n"
            "Hãy đẩy nhân vật tiến về đúng hướng arc trajectory trong chương này."
        )
    if context.name_warnings:
        name_issues = "; ".join(context.name_warnings[:5])
        parts.append(
            f"## [CẢNH BÁO TÊN NHÂN VẬT]: {name_issues}\n"
            "PHẢI dùng tên nhân vật chính xác như đã định nghĩa. Không dùng biến thể hay viết tắt."
        )


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
            rel_lines = []
            for s in context.character_states:
                if getattr(s, "cumulative_relationships", None):
                    rel_lines.append(f"- {s.name}: {'; '.join(s.cumulative_relationships[-5:])}")
            if rel_lines:
                parts.append("## Diễn biến mối quan hệ:\n" + "\n".join(rel_lines))
        if context and context.plot_events:
            events_text = "\n".join(
                f"- Ch.{e.chapter_number}: {e.event}" for e in context.plot_events[-10:]
            )
            parts.append(f"## Sự kiện quan trọng đã xảy ra:\n{events_text}")
        if context:
            _append_consistency_context(parts, context)
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
        rel_lines = []
        for s in context.character_states:
            if getattr(s, "cumulative_relationships", None):
                rel_lines.append(f"- {s.name}: {'; '.join(s.cumulative_relationships[-5:])}")
        if rel_lines:
            parts.append("## Diễn biến mối quan hệ:\n" + "\n".join(rel_lines))
    if context.plot_events:
        events_text = "\n".join(
            f"- Ch.{e.chapter_number}: {e.event}" for e in context.plot_events[-10:]
        )
        parts.append(f"## Sự kiện quan trọng đã xảy ra:\n{events_text}")

    _append_consistency_context(parts, context)
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
    # NEW narrative context params:
    open_threads=None,
    active_conflicts=None,
    foreshadowing_to_plant=None,
    foreshadowing_to_payoff=None,
    pacing_type: str = "",
    enhancement_context: str = "",
    current_arc_context: str = "",
) -> tuple[str, str]:
    """Build system/user prompts for chapter writing. Returns (system_prompt, user_prompt)."""
    chars_text = "\n".join(
        f"- {c.name} ({c.role}): {c.personality}\n  Tiểu sử: {c.background}"
        + (f"\n  Giọng nói: {c.speech_pattern}" if getattr(c, 'speech_pattern', '') else "")
        for c in characters
    )
    chars_constraints_lines = [
        f"- {c.name}: bí mật=[{c.secret}] | điểm gãy=[{c.breaking_point}]"
        for c in characters
        if getattr(c, 'secret', '') or getattr(c, 'breaking_point', '')
    ]
    chars_constraints = "\n".join(chars_constraints_lines) if chars_constraints_lines else "Không có ràng buộc đặc biệt."
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

    # Prepare new narrative context strings
    try:
        from pipeline.layer1_story.plot_thread_tracker import format_threads_for_prompt
        threads_text = format_threads_for_prompt(open_threads or [])
    except Exception:
        threads_text = "Chưa có tuyến truyện đang mở."
    try:
        from pipeline.layer1_story.conflict_web_builder import format_conflicts_for_prompt
        conflicts_text = format_conflicts_for_prompt(active_conflicts or [])
    except Exception:
        conflicts_text = "Không có xung đột active."
    try:
        from pipeline.layer1_story.foreshadowing_manager import format_seeds_for_prompt, format_payoffs_for_prompt
        seeds_text = format_seeds_for_prompt(foreshadowing_to_plant or [])
        payoffs_text = format_payoffs_for_prompt(foreshadowing_to_payoff or [])
    except Exception:
        seeds_text = "Không có foreshadowing cần gieo."
        payoffs_text = "Không có foreshadowing cần payoff."
    try:
        from pipeline.layer1_story.dialogue_strategy import build_dialogue_context
        build_dialogue_context(characters, genre)  # generate for side-effects; not directly injected
    except Exception:
        pass

    # Resolve pacing type — fallback to outline field, then "rising"
    resolved_pacing = pacing_type or getattr(outline, "pacing_type", "") or "rising"

    # Build world text with era, rules, locations
    world_lines = [f"{world.name}: {world.description}"]
    if getattr(world, 'era', ''):
        world_lines.append(f"Thời đại: {world.era}")
    if getattr(world, 'rules', []):
        world_lines.append("Quy tắc PHẢI tuân thủ:\n" + "\n".join(f"  • {r}" for r in world.rules))
    if getattr(world, 'locations', []):
        world_lines.append("Địa điểm: " + ", ".join(world.locations[:5]))
    world_text = "\n".join(world_lines)

    # Build strong pacing directive per pacing_type
    _PACING_DIRECTIVES = {
        "climax": "⚡ CLIMAX — Viết quyết định KHÔNG THỂ đảo ngược. Đối đầu trực tiếp. Cảm xúc bùng nổ. Mỗi câu phải đẩy action forward. Không có cảnh dừng.",
        "twist": "🌀 TWIST — Đảo ngược kỳ vọng hoàn toàn. Tiết lộ thông tin ẩn. Hành động bất ngờ NHƯNG hợp lý khi nhìn lại. Kết chương sốc.",
        "rising": "📈 RISING — Cản trở liên tục leo thang. Mỗi chọn lựa đắt giá hơn. Hệ quả tích lũy. Kết chương PHẢI khiến đọc tiếp ngay.",
        "setup": "🏗️ SETUP — Gieo thông tin tự nhiên, không lộ liễu. Xây quan hệ có chiều sâu. Tạo câu hỏi ngầm. Tuyệt đối không nhàm chán.",
        "cooldown": "🌊 COOLDOWN — Nhân vật xử lý hệ quả sâu sắc. Phát triển nội tâm. Hé lộ chiều sâu mới. Chuẩn bị mâu thuẫn lớn hơn.",
    }
    pacing_directive = _PACING_DIRECTIVES.get(resolved_pacing, "")

    sys_prompt = (
        f"Bạn là tiểu thuyết gia tài năng viết truyện {genre} bằng tiếng Việt. "
        f"BẮT BUỘC: Toàn bộ output phải viết bằng tiếng Việt, không được dùng ngôn ngữ khác."
    )
    user_prompt = prompts.WRITE_CHAPTER.format(
        genre=genre, style=style, title=title,
        world=world_text,
        characters=chars_text,
        chars_constraints=chars_constraints,
        chapter_number=outline.chapter_number,
        chapter_title=outline.title,
        outline=outline_text,
        previous_summary=context_text,
        current_arc_context=current_arc_context,
        word_count=word_count,
        open_threads=threads_text,
        active_conflicts=conflicts_text,
        foreshadowing_to_plant=seeds_text,
        foreshadowing_to_payoff=payoffs_text,
        pacing_type=resolved_pacing,
        pacing_directive=pacing_directive,
    )
    user_prompt = build_adaptive_write_prompt(user_prompt, genre, pacing_type=resolved_pacing)
    # Inject enhancement context (theme premise, voice profiles, scene structure, show-don't-tell)
    if enhancement_context:
        user_prompt += "\n\n" + enhancement_context
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
    open_threads=None,
    active_conflicts=None,
    foreshadowing_to_plant=None,
    foreshadowing_to_payoff=None,
    pacing_type: str = "",
    enhancement_context: str = "",
    current_arc_context: str = "",
) -> Chapter:
    """Write a single chapter (non-streaming)."""
    sys_prompt, user_prompt = build_chapter_prompt(
        config, title, genre, style, characters, world, outline,
        word_count, context, previous_summary, rag_kb=rag_kb,
        open_threads=open_threads, active_conflicts=active_conflicts,
        foreshadowing_to_plant=foreshadowing_to_plant,
        foreshadowing_to_payoff=foreshadowing_to_payoff,
        pacing_type=pacing_type,
        enhancement_context=enhancement_context,
        current_arc_context=current_arc_context,
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
    open_threads=None,
    active_conflicts=None,
    foreshadowing_to_plant=None,
    foreshadowing_to_payoff=None,
    pacing_type: str = "",
    enhancement_context: str = "",
    current_arc_context: str = "",
) -> Chapter:
    """Write chapter with streaming. Calls stream_callback(partial_text) each chunk."""
    sys_prompt, user_prompt = build_chapter_prompt(
        config, title, genre, style, characters, world, outline,
        word_count, context, rag_kb=rag_kb,
        open_threads=open_threads, active_conflicts=active_conflicts,
        foreshadowing_to_plant=foreshadowing_to_plant,
        foreshadowing_to_payoff=foreshadowing_to_payoff,
        pacing_type=pacing_type,
        enhancement_context=enhancement_context,
        current_arc_context=current_arc_context,
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
            model=model, open_threads=open_threads, active_conflicts=active_conflicts,
            foreshadowing_to_plant=foreshadowing_to_plant,
            foreshadowing_to_payoff=foreshadowing_to_payoff, pacing_type=pacing_type,
            enhancement_context=enhancement_context,
            current_arc_context=current_arc_context,
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
