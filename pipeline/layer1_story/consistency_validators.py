"""Post-write consistency validators: timeline/location, character names, arc drift."""

import logging
import re

logger = logging.getLogger(__name__)

# --- Arc stage mapping for drift detection ---

_ARC_STAGES = {
    "setup": 0.0, "rising": 0.2, "testing": 0.4,
    "crisis": 0.6, "climax": 0.8, "resolution": 1.0,
}

_ARC_STAGE_ALIASES = {
    "giới thiệu": "setup", "bắt đầu": "setup", "khởi đầu": "setup",
    "phát triển": "rising", "tăng dần": "rising", "leo thang": "rising",
    "thử thách": "testing", "đối mặt": "testing", "xung đột": "testing",
    "khủng hoảng": "crisis", "sụp đổ": "crisis", "tuyệt vọng": "crisis",
    "cao trào": "climax", "đỉnh điểm": "climax", "bùng nổ": "climax",
    "giải quyết": "resolution", "kết thúc": "resolution", "hồi phục": "resolution",
}


def extract_timeline_and_locations(llm, chapter_content: str, chapter_number: int,
                                   prev_timeline: dict, prev_locations: dict) -> tuple[dict, dict]:
    """Extract timeline positions (per POV) and character locations from chapter.

    Returns (timeline_positions, character_locations) dicts.
    Uses cheap LLM tier — single call for both.
    """
    prev_tl_str = ", ".join(f"{k}: {v}" for k, v in prev_timeline.items()) if prev_timeline else "Chưa xác định"
    prev_loc_str = ", ".join(f"{k}: {v}" for k, v in prev_locations.items()) if prev_locations else "Chưa xác định"
    try:
        result = llm.generate_json(
            system_prompt="Trích xuất thời gian và vị trí. Trả về JSON.",
            user_prompt=(
                f"Chương {chapter_number}:\n{chapter_content[:3000]}\n\n"
                f"Thời gian trước đó: {prev_tl_str}\n"
                f"Vị trí trước đó: {prev_loc_str}\n\n"
                "Xác định:\n"
                "1. Mốc thời gian hiện tại CỦA TỪNG nhân vật/POV xuất hiện "
                "(ví dụ: 'buổi sáng ngày thứ 3', '2 tuần sau trận chiến')\n"
                "2. Vị trí hiện tại của TỪNG nhân vật xuất hiện trong chương\n\n"
                '{"timeline_positions": {"tên nhân vật": "mốc thời gian"},'
                ' "character_locations": {"tên nhân vật": "vị trí hiện tại"}}'
            ),
            temperature=0.2,
            max_tokens=400,
            model_tier="cheap",
        )
        # Handle LLM returning unexpected list
        if isinstance(result, list):
            logger.warning("LLM returned list instead of dict for timeline extraction")
            result = {}
        new_timeline = result.get("timeline_positions", {})
        new_locations = result.get("character_locations", {})
        # Merge with previous (update, not replace)
        merged_tl = {**prev_timeline, **new_timeline} if new_timeline else prev_timeline
        merged_loc = {**prev_locations, **new_locations} if new_locations else prev_locations
        return merged_tl, merged_loc
    except Exception as e:
        logger.warning(f"Timeline/location extraction failed ch{chapter_number}: {e}")
        return prev_timeline, prev_locations


def validate_character_names(content: str, characters: list) -> list[str]:
    """Check chapter for character name inconsistencies via regex.

    Returns list of warning strings. Zero LLM cost.
    """
    warnings = []
    canonical_names = {}
    for char in characters:
        full_name = char.name.strip()
        parts = full_name.split()
        given_name = parts[-1] if parts else full_name
        canonical_names[full_name] = given_name

    # Build valid name forms set
    valid_forms = set()
    for full, given in canonical_names.items():
        valid_forms.add(full)
        valid_forms.add(given)
        parts = full.split()
        if len(parts) >= 3:
            valid_forms.add(f"{parts[0]} {parts[-1]}")

    # Group consecutive capitalized words (Unicode-safe via .isupper())
    all_words = re.findall(r'[^\W\d_]+', content, re.UNICODE)
    groups = []
    current_group: list[str] = []
    for word in all_words:
        if word and word[0].isupper():
            current_group.append(word)
        else:
            if current_group:
                groups.append(" ".join(current_group))
                current_group = []
    if current_group:
        groups.append(" ".join(current_group))

    seen_warnings: set[tuple[str, str]] = set()
    for found in groups:
        if found in valid_forms or len(found) < 2:
            continue
        for valid in valid_forms:
            if len(valid) >= 3 and _is_name_variant(found, valid):
                key = (found, valid)
                if key not in seen_warnings:
                    warnings.append(f"Có thể sai tên: '{found}' (giống '{valid}')")
                    seen_warnings.add(key)
                break
    return warnings


def _is_name_variant(candidate: str, canonical: str) -> bool:
    """Check if candidate is likely a misspelling/variant of canonical."""
    c_low, n_low = candidate.lower(), canonical.lower()
    if c_low == n_low:
        return False
    if c_low in n_low or n_low in c_low:
        return 1 <= abs(len(c_low) - len(n_low)) <= 3
    if len(canonical) >= 4:
        max_dist = 1 if len(canonical) < 6 else 2
        return _edit_distance(c_low, n_low) <= max_dist
    return False


def _edit_distance(s1: str, s2: str) -> int:
    """Levenshtein distance."""
    if len(s1) < len(s2):
        return _edit_distance(s2, s1)
    if not s2:
        return len(s1)
    prev = list(range(len(s2) + 1))
    for c1 in s1:
        curr = [prev[0] + 1]
        for j, c2 in enumerate(s2):
            curr.append(min(prev[j + 1] + 1, curr[j] + 1, prev[j] + (c1 != c2)))
        prev = curr
    return prev[-1]


_TRAVEL_KEYWORDS = (
    "di chuyển", "đi đến", "bay đến", "đến nơi", "hành trình",
    "rời khỏi", "xuất phát", "trên đường", "travel", "journey",
    "lên đường", "quay về", "trở lại", "đáp xuống", "cưỡi",
    "dịch chuyển", "teleport", "xuyên không", "vượt qua",
    "ngày sau", "tuần sau", "tháng sau", "năm sau",
    "sáng hôm sau", "chiều hôm sau", "đêm hôm sau",
)


def validate_location_transitions(
    prev_locations: dict[str, str],
    new_locations: dict[str, str],
    chapter_content: str,
) -> list[str]:
    """Flag impossible character location transitions. Pure Python heuristic.

    Returns list of warning strings.
    """
    if not prev_locations or not new_locations:
        return []

    content_lower = chapter_content.lower() if chapter_content else ""
    has_travel = any(kw in content_lower for kw in _TRAVEL_KEYWORDS)

    warnings = []
    for char_name, new_loc in new_locations.items():
        prev_loc = prev_locations.get(char_name, "")
        if not prev_loc or not new_loc:
            continue
        if prev_loc.lower().strip() == new_loc.lower().strip():
            continue
        if not has_travel and char_name.lower() in content_lower:
            warnings.append(
                f"[VỊ TRÍ] {char_name}: '{prev_loc}' → '{new_loc}' "
                "nhưng không thấy đề cập di chuyển/thời gian trôi qua"
            )
    return warnings


def detect_arc_drift(character_states: list, characters: list,
                     chapter_number: int, total_chapters: int) -> list[str]:
    """Detect characters whose arc_position contradicts expected trajectory progress.

    Returns list of warning strings. Zero LLM cost — pure heuristic.
    """
    if total_chapters <= 0:
        return []
    progress = chapter_number / total_chapters
    warnings = []
    char_map = {c.name: c for c in characters}

    for state in character_states:
        char = char_map.get(state.name)
        if not char or not getattr(char, 'arc_trajectory', ''):
            continue
        pos = state.arc_position.lower().strip()
        pos_normalized = _ARC_STAGE_ALIASES.get(pos, pos)
        pos_value = _ARC_STAGES.get(pos_normalized)
        if pos_value is None:
            continue
        # ±0.3 tolerance band
        if pos_value < max(0.0, progress - 0.3):
            warnings.append(
                f"[ARC DRIFT] {state.name}: '{state.arc_position}' "
                f"({pos_value:.0%}) chậm hơn tiến trình ({progress:.0%}). "
                f"Trajectory: {char.arc_trajectory}"
            )
        elif pos_value > min(1.0, progress + 0.3):
            warnings.append(
                f"[ARC DRIFT] {state.name}: '{state.arc_position}' "
                f"({pos_value:.0%}) nhanh hơn tiến trình ({progress:.0%}). "
                f"Trajectory: {char.arc_trajectory}"
            )
    return warnings
