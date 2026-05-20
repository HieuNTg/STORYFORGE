"""Simulation continue service — generates the next TranscriptTurn.

Sync LLM call (cheap_model) that, given recent history, characters, and a
topic, produces a single dialogue turn. Standalone fast-path — does NOT
mutate any pipeline state.

Lane contract (CLAUDE.md Rule 7): simulator owns drama/plot dialogue only.
The prompt explicitly refuses craft critique (pacing/prose) so this stays
on the simulator side of the simulator/debate boundary.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

from models.schemas import TranscriptTurn
from services.forge_service import _resilient_json_loads

logger = logging.getLogger(__name__)

CONTINUE_SYSTEM_PROMPT = (
    "Bạn là trình mô phỏng nhân vật cho tiểu thuyết mạng tiếng Việt. "
    "PHẠM VI: chỉ sinh hành động + lời thoại nhân vật. KHÔNG bình luận về "
    "văn phong, nhịp truyện, hay chất lượng prose. Output PHẢI là một JSON "
    "object hợp lệ — không Markdown, không text thừa."
)

CONTINUE_USER_TEMPLATE = """\
Tiếp tục mô phỏng đối thoại nhân vật.

Bối cảnh chủ đề: {topic}
Cường độ kịch tính: {drama}

Nhân vật trong cảnh:
{chars}

Lịch sử gần nhất (tối đa 6 turn):
{history}

Sinh DUY NHẤT 1 turn tiếp theo dưới dạng JSON:

{{
  "senderId": "<id hoặc tên nhân vật trong danh sách trên>",
  "senderName": "<tên hiển thị>",
  "emotion": "<nhãn cảm xúc ngắn, vd: phẫn nộ, lạnh lùng, hoang mang>",
  "actionDetails": "<chỉ dẫn sân khấu / hành động, có thể rỗng>",
  "speech": "<lời thoại nhân vật, có thể rỗng nếu chỉ hành động>"
}}

KHÔNG fence, KHÔNG text ngoài JSON.
"""


def _format_chars(characters: list[dict]) -> str:
    lines: list[str] = []
    for ch in characters[:10]:
        if not isinstance(ch, dict):
            continue
        name = str(ch.get("name") or ch.get("senderName") or "?").strip()[:80]
        role = str(ch.get("role") or "").strip()[:40]
        lines.append(f"- {name}" + (f" ({role})" if role else ""))
    return "\n".join(lines) or "- (không có)"


def _format_history(history: list[Any]) -> str:
    lines: list[str] = []
    for turn in history[-6:]:
        if isinstance(turn, TranscriptTurn):
            sender = turn.senderName
            emotion = turn.emotion
            action = turn.actionDetails
            speech = turn.speech
        elif isinstance(turn, dict):
            sender = str(turn.get("senderName") or turn.get("senderId") or "?")[:80]
            emotion = str(turn.get("emotion") or "")[:80]
            action = str(turn.get("actionDetails") or "")[:500]
            speech = str(turn.get("speech") or "")[:500]
        else:
            continue
        bits = [f"[{sender}]"]
        if emotion:
            bits.append(f"({emotion})")
        if action:
            bits.append(f"*{action}*")
        if speech:
            bits.append(f"« {speech} »")
        lines.append(" ".join(bits))
    return "\n".join(lines) or "(chưa có)"


def continue_dialogue(
    llm: Any,
    characters: list[dict],
    history: list[Any],
    topic: str,
    drama_level: str = "high",
    model: Optional[str] = None,
) -> TranscriptTurn:
    """Generate one next TranscriptTurn. Single attempt, no retry."""
    if not topic or not topic.strip():
        raise ValueError("topic is required")
    if not characters:
        raise ValueError("characters is required")

    # str.format() treats `{` / `}` in user input as field markers — escape so
    # a topic like "rule {x}" cannot KeyError or leak template internals.
    def _safe(s: str) -> str:
        return s.replace("{", "{{").replace("}", "}}")

    safe_topic = _safe(topic.strip().replace('"', "'")[:2000])
    user = CONTINUE_USER_TEMPLATE.format(
        topic=safe_topic,
        drama=drama_level,
        chars=_safe(_format_chars(characters)),
        history=_safe(_format_history(history)),
    )
    raw = llm.generate(
        system_prompt=CONTINUE_SYSTEM_PROMPT,
        user_prompt=user,
        temperature=0.9,
        json_mode=True,
        model_tier="cheap",
        model=model or None,
    )
    data = _resilient_json_loads(raw)
    data.setdefault("id", f"t-cont-{uuid.uuid4().hex[:8]}")
    # Clamp sender to a known character when possible. Preserve character list
    # order — set iteration order is non-deterministic, which would make the
    # fallback flaky across runs.
    known_ordered = [
        str(c.get("name") or "").strip()
        for c in characters
        if isinstance(c, dict) and str(c.get("name") or "").strip()
    ]
    known = set(known_ordered)
    name = str(data.get("senderName") or data.get("senderId") or "").strip()
    if known_ordered and name and name not in known:
        name = known_ordered[0]
    if name:
        data["senderName"] = name
        data["senderId"] = name
    return TranscriptTurn.model_validate(data)


__all__ = ["continue_dialogue"]
