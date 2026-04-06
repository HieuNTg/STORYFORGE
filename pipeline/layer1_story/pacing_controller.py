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
