"""Tiered Context Builder — priority-based context for long stories.

4-tier system replaces fixed-window context:
  Tier 1: Full text (last 2 chapters)
  Tier 2: Detailed summary (chapters 3-7 back, ~500 chars each)
  Tier 3: Key events only (older chapters, from StructuredSummary)
  Tier 4: Bible entries (earliest chapters — premise, rules, milestones)

Priority promotion: chapters sharing characters/threads with current chapter
get promoted one tier up.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from models.schemas import Chapter, ChapterOutline, PlotThread, StoryBible

logger = logging.getLogger(__name__)


def build_tiered_context(
    chapter_num: int,
    chapters: list["Chapter"],
    outline: "ChapterOutline",
    open_threads: list["PlotThread"] | None = None,
    story_bible: "StoryBible | None" = None,
    all_chapter_texts: list[str] | None = None,
    max_tokens: int = 3000,
    max_promotions: int = 5,
    prev_chapter: "Chapter | None" = None,
) -> str:
    """Build tiered context string for a chapter. Zero LLM calls."""
    all_chapter_texts = all_chapter_texts or []
    chapters_by_num = {c.chapter_number: c for c in chapters}
    open_threads = open_threads or []

    # Determine tier boundaries
    tier1_start = max(1, chapter_num - 2)  # last 2 chapters
    tier2_start = max(1, chapter_num - 7)  # chapters 3-7 back

    # Identify chapters to promote (share chars/threads with current outline)
    promoted = _get_promoted_chapters(
        chapter_num, outline, chapters_by_num, open_threads, max_promotions,
    )

    parts = []
    est_tokens = 0

    # --- Emotional continuity bridge (prepended before tiers) ---
    bridge = _get_emotional_bridge(prev_chapter)
    if bridge:
        parts.append(bridge)
        est_tokens += len(bridge) // 4

    # --- Tier 1: Full text (last 2 chapters) ---
    tier1_texts = []
    for ch_num in range(tier1_start, chapter_num):
        idx = ch_num - 1
        if 0 <= idx < len(all_chapter_texts) and all_chapter_texts[idx]:
            text = all_chapter_texts[idx][:2000]  # cap per chapter
            tier1_texts.append(f"### Chương {ch_num} (đầy đủ):\n{text}")
    if tier1_texts:
        block = "\n\n".join(tier1_texts)
        block_tokens = len(block) // 4
        if est_tokens + block_tokens <= max_tokens:
            parts.append("## TIER 1 — Nội dung gần nhất\n" + block)
            est_tokens += block_tokens

    # --- Promoted chapters (Tier 2 detail even if normally Tier 3/4) ---
    promoted_texts = []
    for ch_num in promoted:
        if ch_num >= tier1_start:
            continue  # already in tier 1
        ch = chapters_by_num.get(ch_num)
        if ch:
            summary = _get_detailed_summary(ch)
            if summary:
                promoted_texts.append(f"### Chương {ch_num} (⬆ promoted):\n{summary}")
    if promoted_texts:
        block = "\n\n".join(promoted_texts)
        block_tokens = len(block) // 4
        if est_tokens + block_tokens <= max_tokens:
            parts.append("## PROMOTED — Chương liên quan\n" + block)
            est_tokens += block_tokens

    # --- Tier 2: Detailed summaries (chapters 3-7 back) ---
    tier2_texts = []
    for ch_num in range(tier2_start, tier1_start):
        if ch_num in promoted:
            continue  # already shown as promoted
        ch = chapters_by_num.get(ch_num)
        if ch:
            summary = _get_detailed_summary(ch)
            if summary:
                tier2_texts.append(f"### Chương {ch_num}:\n{summary}")
    if tier2_texts:
        block = "\n\n".join(tier2_texts)
        block_tokens = len(block) // 4
        if est_tokens + block_tokens <= max_tokens:
            parts.append("## TIER 2 — Tóm tắt chi tiết\n" + block)
            est_tokens += block_tokens

    # --- Tier 3: Key events only (older chapters) ---
    tier3_texts = []
    for ch_num in range(1, tier2_start):
        if ch_num in promoted:
            continue
        ch = chapters_by_num.get(ch_num)
        if ch and ch.structured_summary:
            events = ch.structured_summary.plot_critical_events
            if events:
                tier3_texts.append(f"Ch{ch_num}: {'; '.join(events[:3])}")
    if tier3_texts:
        block = "\n".join(tier3_texts[-15:])  # cap at 15 oldest chapters
        block_tokens = len(block) // 4
        if est_tokens + block_tokens <= max_tokens:
            parts.append("## TIER 3 — Sự kiện chính\n" + block)
            est_tokens += block_tokens

    # --- Tier 4: Bible context (always included — essential grounding) ---
    if story_bible:
        bible_parts = []
        if story_bible.premise:
            bible_parts.append(f"Tiền đề: {story_bible.premise[:200]}")
        if story_bible.world_rules:
            bible_parts.append(f"Quy tắc: {'; '.join(story_bible.world_rules[:5])}")
        if story_bible.milestone_events:
            bible_parts.append("Mốc: " + "; ".join(story_bible.milestone_events[-5:]))
        if bible_parts:
            block = "\n".join(bible_parts)
            parts.append("## TIER 4 — Nền tảng\n" + block)
            est_tokens += len(block) // 4

    logger.debug(
        "Tiered context for ch%d: ~%d tokens, %d promoted chapters",
        chapter_num, est_tokens, len(promoted),
    )
    return "\n\n".join(parts) if parts else ""


def _get_promoted_chapters(
    chapter_num: int,
    outline: "ChapterOutline",
    chapters_by_num: dict[int, "Chapter"],
    open_threads: list["PlotThread"],
    max_promotions: int,
) -> set[int]:
    """Find chapters to promote to higher tier based on character/thread overlap."""
    promoted: set[int] = set()
    current_chars = set(getattr(outline, "characters_involved", []) or [])

    # Find last significant chapter per character in current outline
    for ch_num in sorted(chapters_by_num.keys(), reverse=True):
        if ch_num >= chapter_num:
            continue
        ch = chapters_by_num[ch_num]
        # Check structured character overlap first
        if ch.structured_summary and current_chars:
            ch_chars = set(ch.structured_summary.character_developments)
            if ch_chars & current_chars:
                promoted.add(ch_num)
                if len(promoted) >= max_promotions:
                    break
                continue
        # Fallback: substring match on summary
        if ch.summary and current_chars:
            for name in current_chars:
                if name in ch.summary:
                    promoted.add(ch_num)
                    break
        if len(promoted) >= max_promotions:
            break

    # Find chapters that last advanced active threads
    for t in open_threads:
        if t.status != "resolved" and t.last_mentioned_chapter and t.last_mentioned_chapter < chapter_num:
            promoted.add(t.last_mentioned_chapter)
        if len(promoted) >= max_promotions:
            break

    return promoted


def _get_emotional_bridge(prev_chapter: "Chapter | None") -> str:
    """Build emotional continuity bridge from previous chapter.

    Returns one-sentence opening anchor or empty string.
    """
    if prev_chapter is None:
        return ""
    ss = getattr(prev_chapter, "structured_summary", None)
    if ss is None:
        return ""
    emotional_shift = getattr(ss, "emotional_shift", None) or getattr(ss, "actual_emotional_arc", None)
    if emotional_shift:
        return f"[CẦU NỐI CẢM XÚC] Chương trước kết thúc với: {emotional_shift}. Tiếp nối tâm trạng này."
    return ""


def _get_detailed_summary(chapter: "Chapter") -> str:
    """Get the best available summary for a chapter (~500 chars)."""
    if chapter.structured_summary:
        ss = chapter.structured_summary
        parts = []
        if ss.plot_critical_events:
            parts.append("Sự kiện: " + "; ".join(ss.plot_critical_events[:3]))
        if ss.character_developments:
            parts.append("Phát triển: " + "; ".join(ss.character_developments[:2]))
        if ss.emotional_shift:
            parts.append(f"Cảm xúc: {ss.emotional_shift}")
        if ss.chapter_ending_hook:
            parts.append(f"Hook: {ss.chapter_ending_hook}")
        result = "\n".join(parts)
        return result[:500]
    elif chapter.summary:
        return chapter.summary[:500]
    return ""
