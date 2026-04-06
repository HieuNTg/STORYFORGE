"""Plot thread tracker — maintains narrative threads across chapters."""

import logging
from typing import Optional, TYPE_CHECKING

from models.schemas import PlotThread, StructuredSummary
from services import prompts

if TYPE_CHECKING:
    from services.llm_client import LLMClient

logger = logging.getLogger(__name__)


def extract_plot_threads(
    llm: "LLMClient",
    content: str,
    chapter_number: int,
    existing_threads: list[PlotThread],
) -> dict:
    """Extract new, progressed, and resolved threads from chapter content.

    Returns dict with keys: new_threads, progressed_threads, resolved_threads.
    """
    threads_text = "\n".join(
        f"- [{t.thread_id}] {t.description} (status: {t.status})"
        for t in existing_threads if t.status != "resolved"
    ) or "Chưa có threads nào."

    from services.text_utils import excerpt_text
    result = llm.generate_json(
        system_prompt="Trích xuất tuyến truyện. Trả về JSON bằng tiếng Việt.",
        user_prompt=prompts.EXTRACT_PLOT_THREADS.format(
            chapter_number=chapter_number,
            content=excerpt_text(content, max_chars=4000),
            existing_threads=threads_text,
        ),
        temperature=0.3,
        max_tokens=1500,
        model_tier="cheap",
    )
    return result


def update_threads(
    existing_threads: list[PlotThread],
    extraction_result: dict,
    chapter_number: int,
) -> list[PlotThread]:
    """Update thread list based on extraction results. Returns updated list."""
    thread_map = {t.thread_id: t for t in existing_threads}

    # Mark progressed threads
    for tid in extraction_result.get("progressed_threads", []):
        if tid in thread_map:
            thread_map[tid].status = "progressing"
            thread_map[tid].last_mentioned_chapter = chapter_number

    # Mark resolved threads
    for tid in extraction_result.get("resolved_threads", []):
        if tid in thread_map:
            thread_map[tid].status = "resolved"
            thread_map[tid].resolution_chapter = chapter_number

    # Add new threads
    for new_t in extraction_result.get("new_threads", []):
        if isinstance(new_t, dict):
            tid = new_t.get("thread_id", f"thread_ch{chapter_number}_{len(thread_map)}")
            if tid not in thread_map:
                try:
                    thread_map[tid] = PlotThread(
                        thread_id=tid,
                        description=new_t.get("description", ""),
                        planted_chapter=chapter_number,
                        status="open",
                        involved_characters=new_t.get("involved_characters", []),
                        last_mentioned_chapter=chapter_number,
                    )
                except Exception as e:
                    logger.warning("Skipping malformed thread: %s", e)

    return list(thread_map.values())


def format_threads_for_prompt(threads: list[PlotThread], max_threads: int = 15) -> str:
    """Format open threads for injection into chapter writing prompt."""
    open_threads = [t for t in threads if t.status != "resolved"]
    # Prioritize: recently mentioned first, then by planted chapter
    open_threads.sort(key=lambda t: t.last_mentioned_chapter, reverse=True)
    open_threads = open_threads[:max_threads]

    if not open_threads:
        return "Chưa có tuyến truyện đang mở."

    lines = []
    for t in open_threads:
        lines.append(f"- [{t.thread_id}] {t.description} (từ ch.{t.planted_chapter}, {t.status})")
    return "\n".join(lines)


def get_stale_threads(threads: list[PlotThread], current_chapter: int, stale_gap: int = 10) -> list[PlotThread]:
    """Find threads that haven't been mentioned in `stale_gap` chapters."""
    return [
        t for t in threads
        if t.status != "resolved"
        and (current_chapter - t.last_mentioned_chapter) >= stale_gap
    ]
