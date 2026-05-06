"""LLM-based quality validators: world rules enforcement, dialogue voice consistency."""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from services.llm_client import LLMClient

logger = logging.getLogger(__name__)


def validate_world_rules(
    llm: "LLMClient",
    content: str,
    rules: list[str],
    chapter_number: int,
) -> list[str]:
    """Check chapter content against world rules. Returns list of violation descriptions."""
    if not rules:
        return []

    from services.text_utils import excerpt_text
    rules_text = "\n".join(f"{i+1}. {r}" for i, r in enumerate(rules))
    result = llm.generate_json(
        system_prompt="Kiểm tra vi phạm quy tắc thế giới. Trả về JSON bằng tiếng Việt.",
        user_prompt=(
            f"Chương {chapter_number}:\n{excerpt_text(content, max_chars=3000)}\n\n"
            f"QUY TẮC THẾ GIỚI:\n{rules_text}\n\n"
            "Kiểm tra nội dung chương có vi phạm quy tắc nào không. "
            "Chỉ liệt kê vi phạm RÕ RÀNG, CHẮC CHẮN — không suy đoán.\n"
            '{"violations": ["mô tả ngắn gọn vi phạm + quy tắc bị vi phạm"]}'
        ),
        temperature=0.2,
        max_tokens=400,
        model_tier="cheap",
    )
    violations = result.get("violations", [])
    out: list[str] = []
    for v in violations:
        if not v:
            continue
        if isinstance(v, str):
            out.append(v)
        elif isinstance(v, dict):
            parts = [f"{k}: {val}" for k, val in v.items() if val]
            if parts:
                out.append(" — ".join(parts))
        else:
            out.append(str(v))
    return out


def validate_dialogue_voice(
    llm: "LLMClient",
    content: str,
    voice_profiles: list[dict],
    chapter_number: int,
) -> list[str]:
    """Check dialogue consistency against character voice profiles. Returns warnings."""
    if not voice_profiles:
        return []

    from pipeline.layer1_story.character_voice_profiler import format_voice_profiles_for_prompt
    from services.text_utils import excerpt_text
    profiles_text = format_voice_profiles_for_prompt(voice_profiles)
    if not profiles_text:
        return []

    result = llm.generate_json(
        system_prompt="Kiểm tra giọng nói nhân vật trong đối thoại. Trả về JSON bằng tiếng Việt.",
        user_prompt=(
            f"Chương {chapter_number}:\n{excerpt_text(content, max_chars=3000)}\n\n"
            f"{profiles_text}\n\n"
            "So sánh lời thoại trong chương với profile giọng nói. "
            "Chỉ báo cáo sai lệch RÕ RÀNG (sai vocabulary level, mất verbal tics đặc trưng, "
            "giọng quá khác biệt so với profile). Không báo cáo nếu đối thoại phù hợp.\n"
            '{"warnings": ["tên nhân vật: mô tả sai lệch cụ thể"]}'
        ),
        temperature=0.3,
        max_tokens=600,
        model_tier="cheap",
    )
    warnings = result.get("warnings", [])
    out: list[str] = []
    for w in warnings:
        if not w:
            continue
        if isinstance(w, str):
            out.append(w)
        elif isinstance(w, dict):
            parts = [f"{k}: {v}" for k, v in w.items() if v]
            if parts:
                out.append(" — ".join(parts))
        else:
            out.append(str(w))
    return out
