"""Vietnamese genre-specific drama patterns for Layer 2 simulation."""

# Genre drama rules — used to inject genre-specific escalation logic
GENRE_DRAMA_RULES: dict[str, dict] = {
    "Tiên Hiệp": {
        "power_escalation": True,
        "mentor_betrayal_threshold": 0.4,
        "breakthrough_trigger": 1.5,
        "tension_curve": "ascending",
        "escalation_interval": 10,
        "key_patterns": ["tu_luyện_đột_phá", "tông_môn_đại_chiến", "thiên_kiếp"],
    },
    "Cung Đấu": {
        "faction_dynamics": True,
        "new_faction_interval": 15,
        "alliance_shift_rate": 0.3,
        "sentiment_oscillation": 0.35,
        "tension_curve": "oscillating",
        "key_patterns": ["hạ_độc", "liên_minh", "phản_bội_cung_đình"],
    },
    "Ngôn Tình": {
        "emotional_cadence": 6,
        "misunderstanding_rate": 0.4,
        "dialogue_density": "high",
        "tension_curve": "wave",
        "key_patterns": ["hiểu_lầm", "ghen_tuông", "hy_sinh", "tỏ_tình"],
    },
    "Huyền Huyễn": {
        "power_escalation": True,
        "world_expansion_interval": 8,
        "tension_curve": "ascending",
        "key_patterns": ["bí_cảnh", "thần_khí", "đại_năng"],
    },
    "Đô Thị": {
        "social_dynamics": True,
        "rivalry_escalation_rate": 0.25,
        "tension_curve": "wave",
        "key_patterns": ["thương_chiến", "âm_mưu", "phục_thù"],
    },
    "Kiếm Hiệp": {
        "honor_system": True,
        "duel_interval": 5,
        "tension_curve": "ascending",
        "key_patterns": ["quyết_đấu", "giang_hồ", "nghĩa_khí"],
    },
    "Xuyên Không": {
        "knowledge_advantage": True,
        "butterfly_effect_rate": 0.3,
        "tension_curve": "ascending",
        "key_patterns": ["thay_đổi_lịch_sử", "tiên_tri", "nghịch_thiên"],
    },
    "Trọng Sinh": {
        "revenge_planning": True,
        "advantage_decay_rate": 0.1,
        "tension_curve": "ascending",
        "key_patterns": ["phục_thù", "lợi_dụng_tiên_tri", "cải_biến"],
    },
}


def get_genre_rules(genre: str) -> dict:
    """Get drama rules for genre. Falls back to empty dict."""
    if genre in GENRE_DRAMA_RULES:
        return GENRE_DRAMA_RULES[genre]
    genre_lower = genre.lower()
    for key, rules in GENRE_DRAMA_RULES.items():
        if key.lower() in genre_lower or genre_lower in key.lower():
            return rules
    return {}


def get_tension_modifier(genre: str, position: float) -> float:
    """Lấy hệ số điều chỉnh ngưỡng leo thang dựa trên đường cong căng thẳng thể loại và vị trí câu chuyện.

    Trả về <1.0 để leo thang dễ hơn (ngưỡng thấp hơn), >1.0 để khó hơn.
    """
    import math
    rules = get_genre_rules(genre)
    curve = rules.get("tension_curve", "ascending")

    if curve == "ascending":
        # Leo thang dễ hơn khi câu chuyện tiến triển
        return 1.2 - position * 0.5  # 1.2 → 0.7
    elif curve == "oscillating":
        # Mô hình sóng: dễ hơn ở đỉnh (0.3, 0.7), khó hơn ở đáy
        return 1.0 - 0.3 * math.sin(position * math.pi * 2)
    elif curve == "wave":
        # Sóng nhẹ
        return 1.0 - 0.2 * math.sin(position * math.pi * 3)
    elif curve in ("ascending_steps", "escalating_spiral"):
        # Hàm bậc thang: dễ hơn mỗi 25%
        step = int(position * 4)
        return max(0.6, 1.1 - step * 0.15)
    else:
        return 1.0


def get_genre_escalation_prompt(genre: str, round_num: int, total_rounds: int) -> str:
    """Generate genre-specific escalation instruction for simulation prompts."""
    rules = get_genre_rules(genre)
    if not rules:
        return ""

    progress = round_num / max(1, total_rounds)
    patterns = rules.get("key_patterns", [])
    curve = rules.get("tension_curve", "ascending")

    parts = [f"Thể loại: {genre}. Mô hình kịch tính: {curve}."]

    if patterns:
        parts.append(f"Yếu tố đặc trưng: {', '.join(patterns[:3])}.")

    if rules.get("power_escalation") and progress > 0.3:
        parts.append("Nhân vật chính cần đột phá sức mạnh hoặc đối mặt thử thách lớn hơn.")

    if rules.get("faction_dynamics") and progress > 0.2:
        parts.append("Cần thay đổi liên minh hoặc xuất hiện thế lực mới.")

    if rules.get("revenge_planning") and progress < 0.5:
        parts.append("Nhân vật chính đang tích lũy lợi thế, chưa nên bộc lộ hết.")

    if progress > 0.7:
        parts.append("Giai đoạn cao trào — tăng cường xung đột, đẩy mâu thuẫn đến đỉnh điểm.")

    return " ".join(parts)


# ══════════════════════════════════════════════════════════════════════════════
# Phase 6: Genre Drama Ceiling — prevent melodrama
# ══════════════════════════════════════════════════════════════════════════════

# Drama ceiling per genre — prevents over-the-top melodrama
# Scale: 0.0-1.0 where 1.0 = maximum possible drama
GENRE_DRAMA_CEILING: dict[str, float] = {
    "Tiên Hiệp": 0.85,      # High drama expected
    "Cung Đấu": 0.80,       # Political intrigue, moderate ceiling
    "Ngôn Tình": 0.70,      # Romance, lower ceiling to avoid melodrama
    "Huyền Huyễn": 0.85,    # Fantasy, high drama OK
    "Đô Thị": 0.75,         # Modern setting, more grounded
    "Kiếm Hiệp": 0.82,      # Martial arts, honor duels
    "Xuyên Không": 0.80,    # Isekai
    "Trọng Sinh": 0.78,     # Rebirth revenge
    "Hài Hước": 0.60,       # Comedy — much lower ceiling
    "Trinh Thám": 0.72,     # Mystery — tension not melodrama
    "Kinh Dị": 0.75,        # Horror — atmospheric not hysterical
}

# Melodrama indicators — phrases that signal over-dramatic writing
MELODRAMA_INDICATORS: list[str] = [
    "tim như vỡ vụn",
    "nước mắt tuôn như suối",
    "đau đớn đến tận xương",
    "trời đất sụp đổ",
    "như dao cắt vào tim",
    "máu lạnh như băng",
    "gào thét thảm thiết",
    "quỳ sụp xuống đất",
    "chết đi sống lại",
    "đập nát mọi thứ",
    "la hét điên cuồng",
    "khóc ngất đi",
    "nghẹn ngào không thốt nên lời",
]


def get_genre_drama_ceiling(genre: str) -> float:
    """Get drama ceiling for genre. Returns 0.75 as default."""
    if genre in GENRE_DRAMA_CEILING:
        return GENRE_DRAMA_CEILING[genre]
    genre_lower = genre.lower()
    for key, ceiling in GENRE_DRAMA_CEILING.items():
        if key.lower() in genre_lower or genre_lower in key.lower():
            return ceiling
    return 0.75  # Default moderate ceiling


def detect_melodrama(content: str, threshold: int = 3) -> tuple[bool, list[str]]:
    """Detect melodramatic writing in content.

    Args:
        content: Text to analyze
        threshold: Number of indicators before flagging

    Returns:
        (is_melodramatic, found_indicators)
    """
    content_lower = content.lower()
    found = []

    for indicator in MELODRAMA_INDICATORS:
        if indicator in content_lower:
            found.append(indicator)

    return len(found) >= threshold, found


def calculate_drama_score_with_ceiling(
    raw_score: float,
    genre: str,
    chapter_position: float = 0.5,
) -> float:
    """Calculate drama score with genre ceiling applied.

    Args:
        raw_score: Original drama score (0.0-1.0)
        genre: Story genre
        chapter_position: Position in story (0.0-1.0)

    Returns:
        Adjusted drama score respecting genre ceiling
    """
    ceiling = get_genre_drama_ceiling(genre)

    # Allow slight ceiling increase for climax chapters (70-90% through story)
    if 0.7 <= chapter_position <= 0.9:
        ceiling = min(0.95, ceiling + 0.1)

    # Apply ceiling
    adjusted = min(raw_score, ceiling)

    return round(adjusted, 3)


def format_drama_ceiling_prompt(genre: str, chapter_position: float = 0.5) -> str:
    """Generate prompt instruction for drama ceiling.

    Used in enhancement prompts to prevent melodrama.
    """
    ceiling = get_genre_drama_ceiling(genre)
    ceiling_pct = int(ceiling * 100)

    is_climax = 0.7 <= chapter_position <= 0.9

    lines = [
        f"## ⚠️ GIỚI HẠN KỊCH TÍNH (Thể loại {genre})",
        f"Mức kịch tính tối đa: {ceiling_pct}%",
    ]

    if is_climax:
        lines.append("Đây là chương cao trào — có thể tăng thêm 10%.")
    else:
        lines.append("KHÔNG được quá mức — tránh melodrama, giữ thực tế cảm xúc.")

    lines.append("")
    lines.append("TRÁNH các cụm từ sáo rỗng như:")
    lines.append(", ".join(f'"{ind}"' for ind in MELODRAMA_INDICATORS[:5]))

    return "\n".join(lines)


def suggest_drama_reduction(content: str, target_reduction: float = 0.15) -> list[str]:
    """Suggest ways to reduce melodrama in content.

    Returns list of suggestions for the enhancer.
    """
    suggestions = []
    is_melodrama, found = detect_melodrama(content, threshold=2)

    if found:
        suggestions.append(f"Thay thế/bỏ các cụm từ sáo: {', '.join(found[:3])}")

    # Check for exclamation overuse
    exclamation_count = content.count("!")
    if exclamation_count > 10:
        suggestions.append(f"Giảm dấu chấm than (hiện có {exclamation_count})")

    # Check for dialogue density
    dialogue_ratio = content.count('"') / max(1, len(content.split()))
    if dialogue_ratio > 0.3:
        suggestions.append("Thêm mô tả hành động, giảm mật độ đối thoại")

    if not suggestions:
        suggestions.append("Dùng ngôn ngữ tinh tế hơn, ít cường điệu")

    return suggestions
