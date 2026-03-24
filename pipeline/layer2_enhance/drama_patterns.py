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
