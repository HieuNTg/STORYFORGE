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


# ══════════════════════════════════════════════════════════════════════════════
# Phase 6: Long-form Context Compression (100+ chapters)
# ══════════════════════════════════════════════════════════════════════════════


def build_compressed_context(
    chapter_num: int,
    chapters: list["Chapter"],
    outline: "ChapterOutline",
    macro_arcs: list | None = None,
    open_threads: list["PlotThread"] | None = None,
    story_bible: "StoryBible | None" = None,
    all_chapter_texts: list[str] | None = None,
    max_tokens: int = 4000,
    prev_chapter: "Chapter | None" = None,
) -> str:
    """Build compressed context for very long stories (20+ chapters).

    Uses adaptive boundaries and arc-aware compression:
    - Tier 1: Last 2 chapters (full text, capped)
    - Tier 2: Same arc chapters (detailed summary)
    - Tier 3: Cross-arc pivots only (key events)
    - Tier 4: Bible + global state

    Zero LLM calls — pure Python.
    """
    all_chapter_texts = all_chapter_texts or []
    chapters_by_num = {c.chapter_number: c for c in chapters}
    open_threads = open_threads or []
    macro_arcs = macro_arcs or []
    total_chapters = len(chapters)

    # Adaptive tier boundaries based on story length
    tier_config = _compute_adaptive_tiers(chapter_num, total_chapters)

    parts = []
    est_tokens = 0

    # --- Emotional bridge ---
    bridge = _get_emotional_bridge(prev_chapter)
    if bridge:
        parts.append(bridge)
        est_tokens += len(bridge) // 4

    # --- Tier 1: Full text (last N chapters, adaptive) ---
    tier1_budget = int(max_tokens * 0.35)
    tier1_texts = []
    for ch_num in range(tier_config["tier1_start"], chapter_num):
        idx = ch_num - 1
        if 0 <= idx < len(all_chapter_texts) and all_chapter_texts[idx]:
            # Compress older tier1 chapters more aggressively
            age = chapter_num - ch_num
            char_limit = 2000 if age <= 1 else 1200
            text = all_chapter_texts[idx][:char_limit]
            tier1_texts.append(f"### Ch{ch_num}:\n{text}")
    if tier1_texts:
        block = "\n\n".join(tier1_texts)
        if est_tokens + len(block) // 4 <= tier1_budget:
            parts.append("## TIER 1 — Gần nhất\n" + block)
            est_tokens += len(block) // 4

    # --- Tier 2: Same-arc chapters ---
    tier2_budget = int(max_tokens * 0.30)
    current_arc = _get_current_arc(chapter_num, macro_arcs)
    same_arc_chapters = _get_same_arc_chapters(
        chapter_num, current_arc, chapters_by_num, tier_config["tier1_start"],
    )
    tier2_texts = []
    for ch_num in same_arc_chapters[:8]:  # Cap at 8 same-arc chapters
        ch = chapters_by_num.get(ch_num)
        if ch:
            summary = _get_compressed_summary(ch, level="detailed")
            if summary:
                tier2_texts.append(f"### Ch{ch_num}:\n{summary}")
    if tier2_texts:
        block = "\n\n".join(tier2_texts)
        if est_tokens + len(block) // 4 <= tier2_budget:
            parts.append(f"## TIER 2 — Arc hiện tại ({current_arc.name if current_arc else 'unknown'})\n" + block)
            est_tokens += len(block) // 4

    # --- Tier 3: Cross-arc pivots (arc boundaries only) ---
    tier3_budget = int(max_tokens * 0.20)
    pivot_chapters = _get_arc_pivot_chapters(chapters_by_num, macro_arcs, chapter_num)
    tier3_texts = []
    for ch_num in pivot_chapters[:10]:  # Cap at 10 pivots
        ch = chapters_by_num.get(ch_num)
        if ch:
            summary = _get_compressed_summary(ch, level="minimal")
            if summary:
                tier3_texts.append(f"Ch{ch_num}: {summary}")
    if tier3_texts:
        block = "\n".join(tier3_texts)
        if est_tokens + len(block) // 4 <= tier3_budget:
            parts.append("## TIER 3 — Mốc quan trọng\n" + block)
            est_tokens += len(block) // 4

    # --- Tier 4: Global state + Bible ---
    tier4_budget = int(max_tokens * 0.15)
    tier4_parts = []

    # Active threads (urgent/stale only)
    urgent_threads = [t for t in open_threads if t.urgency >= 4 or
                      (t.status == "open" and chapter_num - t.last_mentioned_chapter >= 5)]
    if urgent_threads:
        thread_strs = [f"- {t.description[:50]} (từ ch.{t.planted_chapter})" for t in urgent_threads[:5]]
        tier4_parts.append("Tuyến cần giải quyết:\n" + "\n".join(thread_strs))

    # Bible essentials
    if story_bible:
        if story_bible.premise:
            tier4_parts.append(f"Tiền đề: {story_bible.premise[:150]}")
        if story_bible.world_rules:
            tier4_parts.append(f"Quy tắc: {'; '.join(story_bible.world_rules[:4])}")
        if story_bible.milestone_events:
            # Only last few milestones
            tier4_parts.append("Mốc gần: " + "; ".join(story_bible.milestone_events[-4:]))

    if tier4_parts:
        block = "\n".join(tier4_parts)
        if est_tokens + len(block) // 4 <= tier4_budget:
            parts.append("## TIER 4 — Nền tảng\n" + block)
            est_tokens += len(block) // 4

    logger.debug(
        "Compressed context for ch%d/%d: ~%d tokens, %d pivots, %d same-arc",
        chapter_num, total_chapters, est_tokens, len(pivot_chapters), len(same_arc_chapters),
    )
    return "\n\n".join(parts) if parts else ""


def _compute_adaptive_tiers(chapter_num: int, total_chapters: int) -> dict:
    """Compute tier boundaries based on story length."""
    if total_chapters <= 10:
        # Short story: standard tiers
        return {"tier1_start": max(1, chapter_num - 2)}
    elif total_chapters <= 30:
        # Medium story: slightly wider tier 1
        return {"tier1_start": max(1, chapter_num - 3)}
    else:
        # Long story: aggressive compression
        return {"tier1_start": max(1, chapter_num - 2)}


def _get_current_arc(chapter_num: int, macro_arcs: list) -> "object | None":
    """Find which macro arc contains this chapter."""
    for arc in macro_arcs:
        if hasattr(arc, "chapter_start") and hasattr(arc, "chapter_end"):
            if arc.chapter_start <= chapter_num <= arc.chapter_end:
                return arc
    return None


def _get_same_arc_chapters(
    chapter_num: int,
    current_arc: "object | None",
    chapters_by_num: dict[int, "Chapter"],
    exclude_after: int,
) -> list[int]:
    """Get chapters from the same arc (excluding tier 1)."""
    if not current_arc:
        return []

    arc_start = getattr(current_arc, "chapter_start", 1)
    arc_end = min(chapter_num - 1, getattr(current_arc, "chapter_end", chapter_num))

    same_arc = []
    for ch_num in range(arc_start, arc_end + 1):
        if ch_num >= exclude_after:
            continue  # Already in tier 1
        if ch_num in chapters_by_num:
            same_arc.append(ch_num)

    # Prioritize: arc boundaries, then most recent
    arc_boundary = [arc_start, arc_end]
    result = [c for c in same_arc if c in arc_boundary]
    result += [c for c in reversed(same_arc) if c not in result]
    return result


def _get_arc_pivot_chapters(
    chapters_by_num: dict[int, "Chapter"],
    macro_arcs: list,
    current_chapter: int,
) -> list[int]:
    """Get arc boundary chapters (first/last chapter of each arc)."""
    pivots = set()
    for arc in macro_arcs:
        start = getattr(arc, "chapter_start", 0)
        end = getattr(arc, "chapter_end", 0)
        if start > 0 and start < current_chapter and start in chapters_by_num:
            pivots.add(start)
        if end > 0 and end < current_chapter and end in chapters_by_num:
            pivots.add(end)

    # Also include chapters with critical events
    for ch_num, ch in chapters_by_num.items():
        if ch_num >= current_chapter:
            continue
        if ch.structured_summary:
            events = ch.structured_summary.plot_critical_events or []
            # Check for "critical" keywords
            for e in events:
                if any(kw in e.lower() for kw in ["chết", "phản bội", "tiết lộ", "kết thúc", "hy sinh"]):
                    pivots.add(ch_num)
                    break

    return sorted(pivots)


def _get_compressed_summary(chapter: "Chapter", level: str = "detailed") -> str:
    """Get summary at specified compression level.

    Levels:
      - detailed: ~300 chars, events + developments
      - minimal: ~100 chars, critical events only
    """
    if level == "minimal":
        if chapter.structured_summary and chapter.structured_summary.plot_critical_events:
            return "; ".join(chapter.structured_summary.plot_critical_events[:2])[:100]
        elif chapter.summary:
            return chapter.summary[:100]
        return ""

    # detailed level
    if chapter.structured_summary:
        ss = chapter.structured_summary
        parts = []
        if ss.plot_critical_events:
            parts.append("; ".join(ss.plot_critical_events[:2]))
        if ss.character_developments:
            parts.append("(" + ", ".join(ss.character_developments[:2]) + ")")
        return " ".join(parts)[:300]
    elif chapter.summary:
        return chapter.summary[:300]
    return ""


def should_use_compressed_context(total_chapters: int, threshold: int = 20) -> bool:
    """Determine if compressed context should be used."""
    return total_chapters >= threshold
