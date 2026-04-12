"""Plot thread tracker — maintains narrative threads across chapters."""

import logging
from typing import TYPE_CHECKING

from models.schemas import PlotThread
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

    # Mark resolved threads (with dependency validation)
    for tid in extraction_result.get("resolved_threads", []):
        if tid in thread_map:
            allowed, reason = validate_thread_resolution(thread_map[tid], list(thread_map.values()))
            if allowed:
                thread_map[tid].status = "resolved"
                thread_map[tid].resolution_chapter = chapter_number
            else:
                logger.warning("Thread %s resolution blocked: %s", tid, reason)

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
                        depends_on=new_t.get("depends_on", []),
                        blocks=new_t.get("blocks", []),
                        urgency=min(5, max(1, int(new_t.get("urgency", 3)))),
                    )
                except Exception as e:
                    logger.warning("Skipping malformed thread: %s", e)

    return list(thread_map.values())


def format_threads_for_prompt(threads: list[PlotThread], max_threads: int = 15) -> str:
    """Format open threads for injection into chapter writing prompt.

    Sorted by urgency (desc) then staleness (desc) for priority-based prompting.
    """
    open_threads = [t for t in threads if t.status != "resolved"]
    # Sort: urgency desc, then staleness desc (least recently mentioned first)
    open_threads.sort(key=lambda t: (t.urgency, -(t.last_mentioned_chapter or 0)), reverse=True)
    open_threads = open_threads[:max_threads]

    if not open_threads:
        return "Chưa có tuyến truyện đang mở."

    lines = []
    for t in open_threads:
        deps = f" [chờ: {', '.join(t.depends_on)}]" if t.depends_on else ""
        urg = f" ⚡{t.urgency}" if t.urgency >= 4 else ""
        lines.append(f"- [{t.thread_id}] {t.description} (từ ch.{t.planted_chapter}, {t.status}{urg}{deps})")
    return "\n".join(lines)


def get_stale_threads(threads: list[PlotThread], current_chapter: int, stale_gap: int = 10) -> list[PlotThread]:
    """Find threads that haven't been mentioned in `stale_gap` chapters."""
    return [
        t for t in threads
        if t.status != "resolved"
        and (current_chapter - t.last_mentioned_chapter) >= stale_gap
    ]


def validate_thread_resolution(
    thread: PlotThread, all_threads: list[PlotThread],
) -> tuple[bool, str]:
    """Check if a thread can be resolved (all dependencies met).

    Returns (allowed, reason). Pure Python, no LLM.
    """
    if not thread.depends_on:
        return True, ""

    thread_map = {t.thread_id: t for t in all_threads}
    unresolved_deps = []
    for dep_id in thread.depends_on:
        dep = thread_map.get(dep_id)
        if dep and dep.status != "resolved":
            unresolved_deps.append(dep_id)

    if unresolved_deps:
        return False, f"Unresolved dependencies: {', '.join(unresolved_deps)}"
    return True, ""


def escalate_urgency(threads: list[PlotThread], current_chapter: int, gap: int = 5) -> None:
    """Auto-escalate urgency for threads not mentioned in `gap` chapters. In-place."""
    for t in threads:
        if t.status == "resolved":
            continue
        chapters_since = current_chapter - (t.last_mentioned_chapter or t.planted_chapter)
        if chapters_since >= gap and t.urgency < 5:
            t.urgency = min(5, t.urgency + 1)
