"""Chapter Contract Builder — assembles per-chapter requirements from pipeline data.

Pure Python contract generation (zero LLM). Post-write validation costs 1 cheap LLM call.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from models.schemas import (
        Character, ChapterOutline, ConflictEntry,
        ForeshadowingEntry, MacroArc, PlotThread,
    )

from models.narrative_schemas import ChapterContract

logger = logging.getLogger(__name__)


def build_contract(
    chapter_num: int,
    outline: "ChapterOutline",
    threads: list["PlotThread"] | None = None,
    macro_arcs: list["MacroArc"] | None = None,
    conflicts: list["ConflictEntry"] | None = None,
    foreshadowing_plan: list["ForeshadowingEntry"] | None = None,
    characters: list["Character"] | None = None,
    previous_failures: list[str] | None = None,
    world_rules: list[str] | None = None,
    character_secrets: dict[str, str] | None = None,
) -> ChapterContract:
    """Build a ChapterContract from existing pipeline data. Pure Python."""
    threads = threads or []
    conflicts = conflicts or []
    foreshadowing_plan = foreshadowing_plan or []
    characters = characters or []

    # --- Threads to advance: open threads involving this chapter's characters ---
    chapter_chars = set(getattr(outline, "characters_involved", []) or [])
    open_threads = [t for t in threads if t.status != "resolved"]
    # Prioritize stale threads (not mentioned in 5+ chapters) and threads involving chapter characters
    must_advance = []
    for t in open_threads:
        staleness = chapter_num - (t.last_mentioned_chapter or t.planted_chapter)
        involves_chapter_char = bool(chapter_chars & set(t.involved_characters))
        if staleness >= 5 or involves_chapter_char:
            must_advance.append(t.thread_id)
    must_advance = must_advance[:5]  # cap to avoid prompt bloat

    # --- Foreshadowing seeds to plant / payoffs due ---
    must_plant = [f.hint for f in foreshadowing_plan
                  if f.plant_chapter == chapter_num and not f.planted]
    must_payoff = [f.hint for f in foreshadowing_plan
                   if f.payoff_chapter == chapter_num and f.planted and not f.paid_off]

    # --- Character arc targets ---
    arc_targets: dict[str, str] = {}
    try:
        from pipeline.layer1_story.arc_waypoint_generator import get_expected_stage
        for c in characters:
            wp = get_expected_stage(c, chapter_num)
            if wp:
                arc_targets[c.name] = f"{wp.stage_name} ({int(wp.progress_pct * 100)}%)"
    except Exception as e:
        logger.debug("Arc target resolution failed for ch%d: %s", chapter_num, e)

    # --- Pacing from outline ---
    pacing = getattr(outline, "pacing_type", "") or "rising"

    # --- Emotional endpoint from outline ---
    emotional = getattr(outline, "emotional_arc", "") or ""

    # --- Must-mention characters from outline ---
    must_mention = list(chapter_chars)

    # --- Proactive constraints ---
    secrets = character_secrets or {}
    forbidden_actions = [f"DO NOT reveal {secret}" for secret in secrets.values()]

    return ChapterContract(
        chapter_number=chapter_num,
        must_advance_threads=must_advance,
        must_plant_seeds=must_plant,
        must_payoff=must_payoff,
        character_arc_targets=arc_targets,
        pacing_type=pacing,
        emotional_endpoint=emotional,
        must_mention_characters=must_mention,
        previous_contract_failures=previous_failures or [],
        forbidden_actions=forbidden_actions,
        world_rules=world_rules or [],
        secret_protection=secrets,
    )


def format_contract_for_prompt(contract: ChapterContract) -> str:
    """Format contract as Vietnamese prompt section. Capped at ~1600 chars."""
    parts = []

    if contract.previous_contract_failures:
        parts.append(f"## 🔴 LẦN VIẾT TRƯỚC CỦA CHƯƠNG {contract.chapter_number} ĐÃ BỎ LỠ — BẮT BUỘC SỬA NGAY LẦN NÀY:")
        for f in contract.previous_contract_failures[:8]:
            parts.append(f"  ❗ {f}")
        parts.append("→ Viết lại chương đảm bảo KHẮC PHỤC TẤT CẢ các điểm trên. Không được lặp lại lỗi cũ.\n")

    parts.append(f"## HỢP ĐỒNG CHƯƠNG {contract.chapter_number}")
    parts.append("Chương này BẮT BUỘC phải hoàn thành:")

    if contract.must_advance_threads:
        parts.append(f"• Đẩy tiến tuyến: {', '.join(contract.must_advance_threads[:3])}")
    if contract.must_plant_seeds:
        parts.append(f"• Gieo mầm: {', '.join(contract.must_plant_seeds[:3])}")
    if contract.must_payoff:
        parts.append(f"• Thu hoạch: {', '.join(contract.must_payoff[:3])}")
    if contract.character_arc_targets:
        arc_lines = [f"  - {name}: {stage}" for name, stage in list(contract.character_arc_targets.items())[:4]]
        parts.append("• Arc nhân vật:\n" + "\n".join(arc_lines))
    if contract.pacing_type:
        parts.append(f"• Nhịp: {contract.pacing_type}")
    if contract.emotional_endpoint:
        parts.append(f"• Cảm xúc cuối chương: {contract.emotional_endpoint}")
    if contract.must_mention_characters:
        parts.append(f"• Nhân vật PHẢI xuất hiện: {', '.join(contract.must_mention_characters[:5])}")

    # Proactive constraint section
    has_constraints = (
        contract.forbidden_actions
        or contract.must_maintain
        or contract.world_rules
    )
    if has_constraints:
        parts.append("## RÀNG BUỘC")
        for action in contract.forbidden_actions[:5]:
            parts.append(f"CẤM: {action}")
        for state in contract.must_maintain[:5]:
            parts.append(f"DUY TRÌ: {state}")
        for rule in contract.world_rules[:5]:
            parts.append(f"QUY TẮC THẾ GIỚI: {rule}")

    result = "\n".join(parts)
    if len(result) > 1600:
        result = result[:1597] + "..."
    return result


_VALIDATE_PROMPT = """Đánh giá mức tuân thủ hợp đồng chương. So sánh nội dung chương với yêu cầu.

HỢP ĐỒNG:
{contract}

NỘI DUNG CHƯƠNG (500 ký tự đầu):
{chapter_excerpt}

Trả lời JSON:
{{
  "compliance_score": 0.0-1.0,
  "met": ["yêu cầu đã đạt"],
  "failures": ["yêu cầu bị bỏ lỡ — mô tả ngắn"]
}}
CHỈ trả JSON, không giải thích."""


def validate_contract_compliance(
    llm,
    chapter_content: str,
    contract: ChapterContract,
    model: Optional[str] = None,
) -> dict:
    """Validate chapter content against contract. 1 cheap LLM call.

    Returns: {"compliance_score": float, "met": list[str], "failures": list[str]}
    """
    contract_text = format_contract_for_prompt(contract)
    excerpt = chapter_content[:500]
    prompt = _VALIDATE_PROMPT.format(contract=contract_text, chapter_excerpt=excerpt)

    try:
        raw = llm.generate(
            system_prompt="Bạn là editor kiểm tra chất lượng truyện. Trả lời bằng JSON.",
            user_prompt=prompt,
            max_tokens=1024,
            model=model,
        )
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0]
        result = json.loads(raw)
        return {
            "compliance_score": float(result.get("compliance_score", 0.0)),
            "met": result.get("met", []),
            "failures": result.get("failures", []),
        }
    except Exception as e:
        logger.warning("Contract validation parse failed: %s", e)
        return {"compliance_score": 0.0, "met": [], "failures": []}
