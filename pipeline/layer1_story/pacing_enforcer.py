"""Pacing enforcement — classify chapter pacing + targeted rewrite on mismatch.

L1-F: Pacing was advisory in contracts. Now verified post-write; mismatch triggers rewrite.
1 cheap LLM call per chapter when enabled.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from services.llm_client import LLMClient

logger = logging.getLogger(__name__)


_PACING_LABELS = ("setup", "rising", "climax", "twist", "falling", "resolution", "slow", "fast")


_CLASSIFY_PROMPT = """Phân loại nhịp độ (pacing) của chương truyện sau.

## Nhãn nhịp độ
- setup: giới thiệu chậm rãi, xây dựng bối cảnh
- rising: căng thẳng dâng lên, xung đột tăng
- climax: cao trào, đỉnh điểm xung đột, quyết định lớn
- twist: bước ngoặt bất ngờ, tiết lộ
- falling: hệ quả sau cao trào, giảm tốc
- resolution: giải quyết, kết thúc
- slow: chậm, suy ngẫm nội tâm
- fast: nhanh, hành động liên tục

## Nội dung chương (trích 2000 ký tự đầu + 1000 ký tự cuối)
{excerpt}

## Nhiệm vụ
Xác định nhịp độ thực tế của chương. Trả về JSON hợp lệ (không markdown):
{{
  "detected": "<một trong các nhãn>",
  "confidence": 0.0-1.0,
  "reason": "<ngắn gọn vì sao>"
}}
"""


def verify_pacing(
    llm: "LLMClient",
    content: str,
    target_pacing: str,
    model: str | None = None,
) -> dict:
    """Classify chapter pacing. Returns dict with detected/confidence/reason/match.

    Returns empty dict on failure (non-fatal).
    """
    if not content or not target_pacing:
        return {}
    target = target_pacing.strip().lower()
    excerpt = content[:2000] + ("\n...\n" + content[-1000:] if len(content) > 3000 else "")
    prompt = _CLASSIFY_PROMPT.format(excerpt=excerpt)
    try:
        result = llm.generate_json(
            system_prompt="Bạn là editor phân tích nhịp độ truyện. Trả JSON hợp lệ.",
            user_prompt=prompt,
            model=model,
            model_tier="cheap",
        )
        if not isinstance(result, dict):
            return {}
        detected = str(result.get("detected", "")).strip().lower()
        conf = float(result.get("confidence", 0.0) or 0.0)
        return {
            "detected": detected,
            "confidence": conf,
            "reason": str(result.get("reason", "")),
            "target": target,
            "match": detected == target,
        }
    except Exception as e:
        logger.debug("verify_pacing failed (non-fatal): %s", e)
        return {}


_REWRITE_PROMPT = """Bạn là nhà văn chuyên nghiệp. Viết lại chương truyện để khớp nhịp độ mục tiêu.

## Nhịp độ MỤC TIÊU: {target}
## Nhịp độ thực tế của bản hiện tại: {current}
## Lý do lệch: {reason}

## Toàn bộ chương hiện tại
{content}

## Nhiệm vụ
Viết lại chương để thể hiện đúng nhịp độ "{target}". Yêu cầu:
- GIỮ NGUYÊN các sự kiện chính, nhân vật, cốt truyện.
- Điều chỉnh mật độ hành động, độ dài câu, tần suất đối thoại, miêu tả nội tâm cho khớp nhịp độ mục tiêu.
  - climax: câu ngắn, hành động dồn dập, quyết định then chốt, đẩy cảm xúc lên đỉnh.
  - setup: câu dài hơn, miêu tả bối cảnh, giới thiệu mạch truyện.
  - rising: tăng dần căng thẳng, xung đột lộ diện, nhịp nhanh dần.
  - slow: nội tâm, suy ngẫm, chi tiết cảm giác.
  - fast: hành động liên tục, ít suy ngẫm, chuyển cảnh nhanh.
- Độ dài tương đương chương gốc (±15%).
- Chỉ trả về TOÀN BỘ nội dung chương đã viết lại, không chú thích.
"""


def rewrite_for_pacing(
    llm: "LLMClient",
    content: str,
    target_pacing: str,
    current_pacing: str,
    reason: str = "",
    model: str | None = None,
) -> str:
    """Targeted rewrite when detected pacing mismatches target. Non-fatal fallback to original."""
    if not content or not target_pacing:
        return content
    prompt = _REWRITE_PROMPT.format(
        target=target_pacing, current=current_pacing or "không rõ",
        reason=reason or "nhịp độ không khớp", content=content,
    )
    try:
        revised = llm.generate(
            system_prompt="Bạn là nhà văn. Chỉ trả về nội dung chương.",
            user_prompt=prompt,
            model=model,
            max_tokens=8192,
        )
        if isinstance(revised, str) and len(revised) > max(100, int(len(content) * 0.5)):
            return revised
        logger.warning(
            "rewrite_for_pacing: response too short (%d chars), keeping original",
            len(revised) if isinstance(revised, str) else 0,
        )
    except Exception as e:
        logger.warning("rewrite_for_pacing failed (non-fatal): %s", e)
    return content
