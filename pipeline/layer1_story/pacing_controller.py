"""Pacing controller — ensures narrative rhythm across chapters."""

import logging

logger = logging.getLogger(__name__)

# Valid pacing types
PACING_TYPES = ("setup", "rising", "climax", "cooldown", "twist")

# Recommended pacing patterns (repeating cycles)
PACING_CYCLE = ["setup", "rising", "rising", "climax", "cooldown"]


def validate_pacing(pacing_type: str) -> str:
    """Validate and normalize pacing type."""
    if pacing_type in PACING_TYPES:
        return pacing_type
    return "rising"  # safe default


def detect_pacing_issues(pacing_history: list[str], max_consecutive: int = 3) -> list[str]:
    """Detect pacing rhythm issues. Returns list of warnings."""
    warnings = []
    if len(pacing_history) < 2:
        return warnings

    # Check consecutive same pacing
    consecutive = 1
    for i in range(1, len(pacing_history)):
        if pacing_history[i] == pacing_history[i - 1]:
            consecutive += 1
        else:
            consecutive = 1
        if consecutive > max_consecutive:
            warnings.append(
                f"Cảnh báo: {consecutive} chương liên tiếp cùng nhịp '{pacing_history[i]}' — cần đổi nhịp"
            )

    # Check too many climax in a row
    recent = pacing_history[-5:]
    climax_count = recent.count("climax")
    if climax_count >= 3:
        warnings.append("Cảnh báo: quá nhiều climax liên tiếp — người đọc sẽ mệt, cần cooldown")

    # Check no cooldown after climax
    for i in range(1, len(pacing_history)):
        if pacing_history[i - 1] == "climax" and pacing_history[i] == "climax":
            warnings.append(f"Cảnh báo: climax liên tiếp tại vị trí {i-1}-{i} — nên có cooldown xen kẽ")
            break

    return warnings


def suggest_next_pacing(pacing_history: list[str]) -> str:
    """Suggest ideal pacing for the next chapter based on history."""
    if not pacing_history:
        return "setup"

    last = pacing_history[-1]
    if last == "climax":
        return "cooldown"
    if last == "cooldown":
        return "setup"
    if last == "setup":
        return "rising"
    if last == "rising":
        # After 2+ rising, suggest climax
        rising_count = 0
        for p in reversed(pacing_history):
            if p == "rising":
                rising_count += 1
            else:
                break
        return "climax" if rising_count >= 2 else "rising"
    return "rising"


def compare_pacing(intended: str, actual: str) -> str | None:
    """Compare intended pacing with actual emotional arc. Returns mismatch description or None."""
    if not intended or not actual:
        return None
    intended_n = validate_pacing(intended)
    actual_n = _normalize_emotional_arc(actual)
    if not actual_n or intended_n == actual_n:
        return None
    return f"Dự kiến '{intended_n}' nhưng thực tế '{actual_n}'"


def compute_pacing_adjustment(intended: str, actual: str, history: list[str] | None = None) -> str:
    """Compute a Vietnamese pacing correction directive for next chapter. Pure Python."""
    mismatch = compare_pacing(intended, actual)
    if not mismatch:
        return ""
    intended_n = validate_pacing(intended)
    actual_n = _normalize_emotional_arc(actual)
    # Determine correction direction
    intended_level = _PACING_LEVELS.get(intended_n, 2)
    actual_level = _PACING_LEVELS.get(actual_n, 2)
    diff = intended_level - actual_level
    if diff > 0:
        direction = "LEO THANG — tăng cường độ, xung đột, tốc độ"
    elif diff < 0:
        direction = "HẠ NHIỆT — giảm tốc, phản ánh, xây dựng nội tâm"
    else:
        direction = "GIỮ NHỊP — duy trì cường độ hiện tại"
    # Cap adjustment: max 1 level jump
    target = _level_to_pacing(min(actual_level + 1, 4) if diff > 0 else max(actual_level - 1, 0))
    return (
        f"[ĐIỀU CHỈNH NHỊP ĐỘ] Chương trước {mismatch}. "
        f"Chương này PHẢI: {direction}. Nhắm đến nhịp '{target}'."
    )


# --- Pacing level mapping for mismatch detection ---

_PACING_LEVELS = {"setup": 0, "cooldown": 1, "rising": 2, "twist": 3, "climax": 4}

_EMOTIONAL_ARC_MAP = {
    "bình lặng": "setup", "giới thiệu": "setup", "khởi đầu": "setup",
    "phát triển": "rising", "tăng dần": "rising", "leo thang": "rising",
    "căng thẳng": "rising", "hồi hộp": "rising",
    "cao trào": "climax", "đỉnh điểm": "climax", "bùng nổ": "climax",
    "hạ nhiệt": "cooldown", "phản ánh": "cooldown", "nghỉ ngơi": "cooldown",
    "bất ngờ": "twist", "lật ngược": "twist", "twist": "twist",
    "setup": "setup", "rising": "rising", "climax": "climax",
    "cooldown": "cooldown",
}


def _normalize_emotional_arc(arc: str) -> str:
    """Map free-form Vietnamese emotional arc to pacing type."""
    arc_lower = arc.lower().strip()
    if arc_lower in PACING_TYPES:
        return arc_lower
    for keyword, pacing in _EMOTIONAL_ARC_MAP.items():
        if keyword in arc_lower:
            return pacing
    return ""


def _level_to_pacing(level: int) -> str:
    """Convert numeric level back to pacing type."""
    for name, lvl in _PACING_LEVELS.items():
        if lvl == level:
            return name
    return "rising"


def get_word_count_modifier(pacing_type: str) -> float:
    """Return word count multiplier based on pacing type."""
    modifiers = {
        "setup": 1.1,     # slightly longer for world-building
        "rising": 1.0,    # standard
        "climax": 1.2,    # longer for big scenes
        "cooldown": 0.85, # shorter, reflective
        "twist": 0.95,    # slightly shorter, punchy
    }
    return modifiers.get(pacing_type, 1.0)
