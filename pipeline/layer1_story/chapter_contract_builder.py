"""Chapter Contract Builder — assembles per-chapter requirements from pipeline data.

Pure Python contract generation (zero LLM). Post-write validation costs 1 cheap LLM call.
"""

import json
import logging
from typing import Optional

from models.narrative_schemas import ChapterContract

# Assembly + event-matching helpers live in _chapter_contract_assembly; re-imported
# here so existing chapter_contract_builder.<name> imports and patch targets work.
from pipeline.layer1_story._chapter_contract_assembly import (
    build_contract,
    events_for_chapter,
    extract_chapter_num,
)

logger = logging.getLogger(__name__)

__all__ = [
    "build_contract",
    "events_for_chapter",
    "extract_chapter_num",
    "format_contract_for_prompt",
    "validate_contract_compliance",
]


def format_contract_for_prompt(contract: ChapterContract) -> str:
    """Format contract as Vietnamese prompt section. Capped at ~1600 chars."""
    parts = []

    if contract.previous_contract_failures:
        parts.append(
            f"## 🔴 LẦN VIẾT TRƯỚC CỦA CHƯƠNG {contract.chapter_number} ĐÃ BỎ LỠ — BẮT BUỘC SỬA NGAY LẦN NÀY:"
        )
        for f in contract.previous_contract_failures[:8]:
            parts.append(f"  ❗ {f}")
        parts.append(
            "→ Viết lại chương đảm bảo KHẮC PHỤC TẤT CẢ các điểm trên. Không được lặp lại lỗi cũ.\n"
        )

    parts.append(f"## HỢP ĐỒNG CHƯƠNG {contract.chapter_number}")
    parts.append("Chương này BẮT BUỘC phải hoàn thành:")

    if contract.must_advance_threads:
        parts.append(
            f"• Đẩy tiến tuyến: {', '.join(contract.must_advance_threads[:3])}"
        )
    if contract.must_plant_seeds:
        parts.append(f"• Gieo mầm: {', '.join(contract.must_plant_seeds[:3])}")
    if contract.must_payoff:
        parts.append(f"• Thu hoạch: {', '.join(contract.must_payoff[:3])}")
    if contract.character_arc_targets:
        arc_lines = [
            f"  - {name}: {stage}"
            for name, stage in list(contract.character_arc_targets.items())[:4]
        ]
        parts.append("• Arc nhân vật:\n" + "\n".join(arc_lines))
    if contract.pacing_type:
        parts.append(f"• Nhịp: {contract.pacing_type}")
    if contract.emotional_endpoint:
        parts.append(f"• Cảm xúc cuối chương: {contract.emotional_endpoint}")
    if contract.must_mention_characters:
        parts.append(
            f"• Nhân vật PHẢI xuất hiện: {', '.join(contract.must_mention_characters[:5])}"
        )

    # Proactive constraint section
    has_constraints = (
        contract.forbidden_actions or contract.must_maintain or contract.world_rules
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
