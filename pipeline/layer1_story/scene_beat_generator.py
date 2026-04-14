"""Scene beat generator — breaks chapters into scene-level structure."""

import logging
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from services.llm_client import LLMClient
    from models.schemas import ChapterOutline, WorldSetting

logger = logging.getLogger(__name__)


class SceneBeat(BaseModel):
    scene_num: int
    characters: list[str] = Field(default_factory=list)
    setting: str = ""
    action: str = ""
    tension_level: float = Field(default=0.5, ge=0.0, le=1.0)
    pov: str = ""
    emotional_goal: str = ""


def generate_scene_beats(
    llm: "LLMClient",
    outline: "ChapterOutline",
    characters: list,
    world: "WorldSetting",
    genre: str,
    model_tier: str = "cheap",
    pacing_type: str | None = None,
) -> list[SceneBeat]:
    """Generate scene-level beat structure for any chapter type.

    Returns list[SceneBeat]. Returns [] on failure or if generation is skipped.
    Pass pacing_type to override outline.pacing_type (pass "" to force generation
    regardless of pacing type).
    """
    pacing = pacing_type if pacing_type is not None else (getattr(outline, 'pacing_type', '') or '')

    chars_text = ", ".join(c.name for c in characters[:5])

    try:
        result = llm.generate_json(
            system_prompt="Bạn là chuyên gia cấu trúc cảnh truyện. BẮT BUỘC viết bằng tiếng Việt. Trả về JSON.",
            user_prompt=(
                f"Thể loại: {genre}\n"
                f"Chương {outline.chapter_number}: {outline.title}\n"
                f"Tóm tắt: {outline.summary}\n"
                f"Sự kiện chính: {', '.join(outline.key_events)}\n"
                f"Nhân vật: {chars_text}\n"
                + (f"Loại chương: {pacing}\n" if pacing else "")
                + "\nChia chương thành 3-5 cảnh (scene). Mỗi cảnh cần:\n"
                '{"scenes": [{'
                '"scene_num": 1, '
                '"characters": ["tên"], '
                '"setting": "địa điểm/thời điểm", '
                '"action": "hành động/sự kiện chính", '
                '"tension_level": 0.5, '
                '"pov": "nhân vật POV", '
                '"emotional_goal": "cảm xúc/mục tiêu cảnh này"'
                '}]}'
            ),
            temperature=0.7,
            max_tokens=700,
            model_tier=model_tier,
        )
        raw_scenes = result.get("scenes", [])
        if not raw_scenes:
            return []

        beats: list[SceneBeat] = []
        for s in raw_scenes:
            try:
                # Map legacy field names from older prompt schema
                if "characters_present" in s and "characters" not in s:
                    s["characters"] = s.pop("characters_present")
                if "emotional_beat" in s and "emotional_goal" not in s:
                    s["emotional_goal"] = s.pop("emotional_beat")
                # Drop unknown keys before constructing model
                allowed = SceneBeat.model_fields.keys()
                filtered = {k: v for k, v in s.items() if k in allowed}
                beats.append(SceneBeat(**filtered))
            except Exception as exc:
                logger.debug(f"Skipping invalid scene beat: {exc}")
        return beats
    except Exception as e:
        logger.debug(f"Scene beat generation failed for ch{outline.chapter_number}: {e}")
        return []


def format_beats_for_prompt(beats: list[SceneBeat]) -> str:
    """Format scene beats into a string suitable for injection into a chapter prompt."""
    if not beats:
        return ""
    lines = ["## CẤU TRÚC CẢNH:"]
    for b in beats:
        chars = ", ".join(b.characters) if b.characters else "?"
        tension_pct = int(b.tension_level * 100)
        pov_part = f" [POV: {b.pov}]" if b.pov else ""
        lines.append(
            f"Cảnh {b.scene_num}{pov_part}: [{b.setting}] "
            f"{b.action} — tension {tension_pct}% "
            f"(mục tiêu: {b.emotional_goal}) "
            f"[nhân vật: {chars}]"
        )
    lines.append("Viết đúng theo cấu trúc cảnh trên, đảm bảo mỗi cảnh có đủ chiều sâu.")
    return "\n".join(lines)
