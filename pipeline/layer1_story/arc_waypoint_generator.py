"""Generate structured arc waypoints for each character.

Replaces flat arc_trajectory string with stage-by-stage waypoints so the
chapter writer knows exactly where each character should be in their arc.
One LLM call for all characters at story init time.
"""

import logging
from typing import Optional, TYPE_CHECKING

from models.narrative_schemas import ArcWaypoint
from models.schemas import Character

if TYPE_CHECKING:
    from services.llm_client import LLMClient

logger = logging.getLogger(__name__)

_PROMPT = """\
Bạn là chuyên gia phát triển nhân vật. Hãy tạo CÁC GIAI ĐOẠN ARC cho từng nhân vật.

Thể loại: {genre}
Số chương: {num_chapters}

NHÂN VẬT:
{characters_text}

YÊU CẦU:
- Mỗi nhân vật cần 3-5 giai đoạn arc (stage)
- Mỗi giai đoạn có: chapter_start, chapter_end, mô tả ngắn, cảm xúc chủ đạo
- Các giai đoạn phải liên tục (chapter_end stage N = chapter_start stage N+1 - 1)
- Tiến trình phải từ 0% đến 100%
- Nhân vật phụ ít giai đoạn hơn (2-3)

Trả về JSON:
{{
  "characters": [
    {{
      "name": "Tên nhân vật",
      "waypoints": [
        {{
          "stage_name": "phủ nhận",
          "chapter_start": 1,
          "chapter_end": 10,
          "description": "Từ chối thay đổi, bám víu cuộc sống cũ",
          "emotional_state": "sợ hãi, cố chấp",
          "progress_pct": 0.2
        }}
      ]
    }}
  ]
}}"""


def generate_arc_waypoints(
    llm: "LLMClient",
    characters: list[Character],
    num_chapters: int,
    genre: str = "",
    model: Optional[str] = None,
) -> dict[str, list[ArcWaypoint]]:
    """Generate structured arc waypoints for all characters. Returns {name: [ArcWaypoint]}."""
    chars_text = "\n".join(
        f"- {c.name} ({c.role}): {c.personality}. Arc: {c.arc_trajectory or 'chưa rõ'}. "
        f"Xung đột nội tâm: {c.internal_conflict or 'chưa rõ'}"
        for c in characters
    )
    prompt = _PROMPT.format(
        genre=genre, num_chapters=num_chapters, characters_text=chars_text,
    )
    try:
        result = llm.generate_json(
            system_prompt="Bạn là trợ lý tạo cấu trúc arc nhân vật. Trả về JSON bằng tiếng Việt.",
            user_prompt=prompt,
            temperature=0.5,
            max_tokens=2000,
            model=model,
        )
    except Exception as e:
        logger.warning("Arc waypoint generation failed: %s", e)
        return {}

    waypoints_map: dict[str, list[ArcWaypoint]] = {}
    for entry in result.get("characters", []):
        name = entry.get("name", "")
        if not name:
            continue
        wps = []
        for wp_data in entry.get("waypoints", []):
            try:
                wps.append(ArcWaypoint(
                    stage_name=wp_data.get("stage_name", ""),
                    chapter_range=[wp_data.get("chapter_start", 1), wp_data.get("chapter_end", num_chapters)],
                    description=wp_data.get("description", ""),
                    emotional_state=wp_data.get("emotional_state", ""),
                    progress_pct=float(wp_data.get("progress_pct", 0.0)),
                ))
            except Exception as e:
                logger.debug("Skipping invalid waypoint for %s: %s", name, e)
        if wps:
            waypoints_map[name] = wps
    return waypoints_map


def apply_waypoints_to_characters(
    characters: list[Character],
    waypoints_map: dict[str, list[ArcWaypoint]],
) -> None:
    """Attach generated waypoints to Character objects in-place."""
    for c in characters:
        wps = waypoints_map.get(c.name, [])
        if wps:
            c.arc_waypoints = [wp.model_dump() for wp in wps]


def get_expected_stage(
    character: Character, chapter_number: int,
) -> Optional[ArcWaypoint]:
    """Lookup which arc stage a character should be at for a given chapter. Pure Python."""
    for wp_data in getattr(character, "arc_waypoints", []):
        wp = wp_data if isinstance(wp_data, ArcWaypoint) else ArcWaypoint(**wp_data) if isinstance(wp_data, dict) else None
        if wp and wp.chapter_range[0] <= chapter_number <= wp.chapter_range[1]:
            return wp
    return None


def format_arc_stages_for_prompt(
    characters: list[Character], chapter_number: int,
) -> str:
    """Format expected arc stages for all characters at a given chapter. Vietnamese output."""
    lines = []
    for c in characters:
        wp = get_expected_stage(c, chapter_number)
        if wp:
            lines.append(
                f"- {c.name}: giai đoạn '{wp.stage_name}' ({int(wp.progress_pct * 100)}%) "
                f"— {wp.description}. Cảm xúc: {wp.emotional_state}"
            )
    if not lines:
        return ""
    return "## MỤC TIÊU ARC NHÂN VẬT CHƯƠNG NÀY:\n" + "\n".join(lines)


def update_arc_progression_cache(
    cache: dict[str, list[dict]],
    results: list,
    chapter_number: int,
    cap_per_character: int = 15,
) -> None:
    """L1-C: Append arc validation results to per-character cache. Mutates in place.

    `results` is the list returned by validate_all_arcs (ArcValidationResult objects).
    Cache shape: {character_name: [{chapter, stage_name, progress_pct, emotion, found, confidence, severity}]}
    """
    for r in results or []:
        name = getattr(r, "character", "") or ""
        if not name:
            continue
        entry = {
            "chapter": int(getattr(r, "chapter_number", chapter_number) or chapter_number),
            "stage_name": getattr(r, "expected_stage", "") or "",
            "emotion": getattr(r, "expected_emotion", "") or "",
            "found": bool(getattr(r, "found", False)),
            "confidence": float(getattr(r, "confidence", 0.0) or 0.0),
            "severity": getattr(r, "severity", "") or "",
        }
        history = cache.get(name) or []
        # Deduplicate: overwrite existing entry for same chapter
        history = [e for e in history if e.get("chapter") != entry["chapter"]]
        history.append(entry)
        cache[name] = sorted(history, key=lambda e: e.get("chapter", 0))[-cap_per_character:]


def format_arc_progression_for_prompt(
    cache: dict[str, list[dict]],
    characters: list[Character],
    current_chapter: int,
    lookback: int = 3,
) -> str:
    """Format last N chapters of arc progression per character for chapter writer prompt.

    Helps the writer avoid arc regression and maintain continuity.
    """
    if not cache:
        return ""
    lines: list[str] = []
    for c in characters:
        history = cache.get(c.name) or []
        recent = [e for e in history if e.get("chapter", 0) < current_chapter][-lookback:]
        if not recent:
            continue
        parts = []
        for e in recent:
            marker = "✓" if e.get("found") else "✗"
            parts.append(
                f"ch{e.get('chapter')}:{e.get('stage_name') or '?'}{marker}"
            )
        lines.append(f"- {c.name}: " + " → ".join(parts))
    if not lines:
        return ""
    return "## LỊCH SỬ ARC GẦN ĐÂY (tránh lùi giai đoạn):\n" + "\n".join(lines)
