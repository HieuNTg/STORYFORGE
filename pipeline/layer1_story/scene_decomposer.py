"""Scene decomposer — breaks a chapter outline into 3-5 scenes before chapter writing."""

import logging
import threading
from typing import Optional, TYPE_CHECKING

from models.schemas import Character, WorldSetting, ChapterOutline

if TYPE_CHECKING:
    from services.llm_client import LLMClient

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

DECOMPOSE_SCENES = """Bạn là biên kịch chuyên nghiệp. Hãy phân tích dàn ý chương sau và chia thành 3-5 cảnh cụ thể.

## THÔNG TIN CHƯƠNG
Chương: {chapter_number} — {title}
Tóm tắt: {summary}
Sự kiện chính: {key_events}
Nhân vật tham gia: {characters_involved}
Cung bậc cảm xúc: {emotional_arc}
Nhịp độ: {pacing_type}

## NHÂN VẬT
{characters_text}

## BỐI CẢNH THẾ GIỚI
{world_text}

## THỂ LOẠI
{genre}

## YÊU CẦU
Chia chương thành 3-5 cảnh. Mỗi cảnh cần có mục đích tường minh, xung đột nội tâm hoặc ngoại cảnh, và kết quả rõ ràng.
Đảm bảo các cảnh kết nối mạch lạc và cùng nhau hoàn thành cung bậc cảm xúc của chương.

Trả về JSON hợp lệ theo định dạng:
{{
  "scenes": [
    {{
      "scene_number": 1,
      "location": "nơi diễn ra cảnh",
      "pov_character": "nhân vật góc nhìn",
      "characters_present": ["nhân vật 1", "nhân vật 2"],
      "goal": "mục tiêu tường thuật của cảnh này",
      "conflict": "xung đột hoặc trở ngại",
      "outcome": "kết quả (thành công/thất bại/phức tạp hóa)",
      "sensory_focus": ["giác quan 1", "giác quan 2"],
      "emotional_beat": "cung bậc cảm xúc của cảnh"
    }}
  ]
}}

Chỉ trả JSON, không giải thích thêm."""

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

CLIMAX_PACING_TYPES = {
    "climax",
    "đỉnh điểm",
    "twist",
    "bước ngoặt",
    "crisis",
    "khủng hoảng",
}


def should_decompose(chapter_number: int, pacing_type: str) -> bool:
    """Return True if this chapter should be scene-decomposed before writing.

    Climax/twist chapters are always decomposed.
    All other chapters default to True (can be gated by config later).
    """
    if pacing_type and pacing_type.lower() in CLIMAX_PACING_TYPES:
        return True
    return True  # default: always decompose


# ---------------------------------------------------------------------------
# Per-outline memoisation
# ---------------------------------------------------------------------------
# A global lock guards creation of the per-outline locks only. The build itself
# runs under the outline's own lock, so two callers for the same chapter
# serialise into one decomposition while different chapters still run in
# parallel — a single global lock would serialise the whole batch.
_SCENE_LOCK_REGISTRY_LOCK = threading.Lock()
_SCENE_CACHE_ATTR = "_scene_decomposition_cache"
_SCENE_LOCK_ATTR = "_scene_decomposition_lock"


def _outline_lock(outline) -> "threading.Lock | None":
    try:
        existing = getattr(outline, _SCENE_LOCK_ATTR, None)
        if existing is not None:
            return existing
        with _SCENE_LOCK_REGISTRY_LOCK:
            existing = getattr(outline, _SCENE_LOCK_ATTR, None)
            if existing is None:
                existing = threading.Lock()
                setattr(outline, _SCENE_LOCK_ATTR, existing)
            return existing
    except Exception:  # pragma: no cover — outline refuses the attribute
        return None


def _cache_key(genre: str, model: Optional[str]) -> tuple:
    return (genre or "", model or "")


def _cached_scenes(outline, genre: str, model: Optional[str]):
    """Return the memoised decomposition for this outline, or None."""
    try:
        cache = getattr(outline, _SCENE_CACHE_ATTR, None)
    except Exception:  # pragma: no cover - defensive
        return None
    if not cache:
        return None
    return cache.get(_cache_key(genre, model))


def _store_scenes(outline, genre: str, model: Optional[str], scenes: list) -> None:
    """Memoise a decomposition, including an empty one (a failure is a result)."""
    try:
        cache = getattr(outline, _SCENE_CACHE_ATTR, None)
        if cache is None:
            cache = {}
            setattr(outline, _SCENE_CACHE_ATTR, cache)
        cache[_cache_key(genre, model)] = scenes
    except Exception:  # pragma: no cover - outline refuses the attribute
        pass


def decompose_chapter_scenes(
    llm: "LLMClient",
    outline: ChapterOutline,
    characters: list[Character],
    world: WorldSetting,
    genre: str,
    model: Optional[str] = None,
) -> list[dict]:
    """Decompose a chapter outline into 3-5 scene dicts.

    Returns an empty list on failure (non-fatal).

    The result is memoised on the outline. Both the sequential write path
    (`scene_write_prep`) and the enhancement-context builder decompose the same
    chapter, gated on the same `enable_scene_decomposition` flag — so every
    chapter paid for this twice, for byte-identical output.
    """
    cached = _cached_scenes(outline, genre, model)
    if cached is not None:
        return cached

    lock = _outline_lock(outline)
    if lock is not None:
        with lock:
            # Another caller for this chapter may have finished while we waited.
            cached = _cached_scenes(outline, genre, model)
            if cached is not None:
                return cached
            return _decompose_uncached(
                llm, outline, characters, world, genre, model
            )
    return _decompose_uncached(llm, outline, characters, world, genre, model)


def _decompose_uncached(
    llm: "LLMClient",
    outline: ChapterOutline,
    characters: list[Character],
    world: WorldSetting,
    genre: str,
    model: Optional[str] = None,
) -> list[dict]:
    """The actual decomposition. Callers go through decompose_chapter_scenes."""
    chars_text = "\n".join(
        f"- {c.name} ({c.role}): {c.personality}" for c in characters
    )
    world_text = f"{world.name}: {world.description}"
    if world.locations:
        locs = (
            ", ".join(world.locations)
            if isinstance(world.locations, list)
            else str(world.locations)
        )
        world_text += f"\nĐịa điểm: {locs}"
    if world.era:
        world_text += f"\nThời đại: {world.era}"

    key_events = (
        "\n".join(f"- {e}" for e in outline.key_events)
        if outline.key_events
        else "Không có"
    )
    chars_involved = (
        ", ".join(outline.characters_involved)
        if outline.characters_involved
        else "Không có"
    )

    user_prompt = DECOMPOSE_SCENES.format(
        chapter_number=outline.chapter_number,
        title=outline.title,
        summary=outline.summary,
        key_events=key_events,
        characters_involved=chars_involved,
        emotional_arc=outline.emotional_arc or "Không xác định",
        pacing_type=outline.pacing_type or "normal",
        characters_text=chars_text,
        world_text=world_text,
        genre=genre,
    )

    try:
        result = llm.generate_json(
            system_prompt="Bạn là biên kịch chuyên nghiệp. BẮT BUỘC viết bằng tiếng Việt. Trả về JSON.",
            user_prompt=user_prompt,
            model=model,
            expect="dict",
            list_key="scenes",
        )
        scenes = result.get("scenes", [])
        if not isinstance(scenes, list):
            logger.warning(
                "decompose_chapter_scenes: unexpected scenes type %s", type(scenes)
            )
            _store_scenes(outline, genre, model, [])
            return []
        # Clamp to 3-5 scenes
        scenes = scenes[:5]
        _store_scenes(outline, genre, model, scenes)
        return scenes
    except Exception as exc:
        logger.warning(
            "decompose_chapter_scenes failed for chapter %s: %s",
            outline.chapter_number,
            exc,
        )
        # Memoise the failure too: retrying it on the second call site would
        # double the cost of a chapter that already failed once.
        _store_scenes(outline, genre, model, [])
        return []


def format_scenes_for_prompt(scenes: list[dict]) -> str:
    """Format scene list into a compact string section for injection into chapter writing prompt."""
    if not scenes:
        return ""

    lines = ["## CẤU TRÚC CẢNH (bám sát khi viết chương):"]
    for s in scenes:
        num = s.get("scene_number", "?")
        location = s.get("location", "")
        pov = s.get("pov_character", "")
        present = ", ".join(s.get("characters_present", [])) or pov
        goal = s.get("goal", "")
        conflict = s.get("conflict", "")
        outcome = s.get("outcome", "")
        senses = ", ".join(s.get("sensory_focus", [])) or ""
        beat = s.get("emotional_beat", "")

        lines.append(f"\n[Cảnh {num}] {location} | POV: {pov}")
        if present and present != pov:
            lines.append(f"  Nhân vật: {present}")
        lines.append(f"  Mục tiêu: {goal}")
        lines.append(f"  Xung đột: {conflict}")
        lines.append(f"  Kết quả: {outcome}")
        if senses:
            lines.append(f"  Giác quan: {senses}")
        if beat:
            lines.append(f"  Cảm xúc: {beat}")

    return "\n".join(lines)
