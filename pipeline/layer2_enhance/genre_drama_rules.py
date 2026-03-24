"""Vietnamese genre-specific drama patterns and escalation rules."""

GENRE_DRAMA_RULES: dict[str, dict] = {
    "Tiên Hiệp": {
        "escalation_pattern": "power_progression",
        "key_beats": [
            "Protagonist breakthrough → rival obtains higher power",
            "Hidden technique reveal at critical moment",
            "Mentor betrayal seed at ~40% story",
            "Sect tournament escalation",
        ],
        "tension_curve": "ascending_steps",  # Staircase pattern
        "dialogue_style": "formal_martial",
        "emotional_peaks": ["breakthrough", "near_death", "power_reveal"],
        "pacing_note": "Power gap < 1.5x antagonist → trigger breakthrough chapter",
    },
    "Huyền Huyễn": {
        "escalation_pattern": "mystery_reveal",
        "key_beats": [
            "World rule discovery changes everything",
            "Hidden bloodline/artifact activation",
            "Alliance betrayal during crisis",
            "Realm ascension as story milestone",
        ],
        "tension_curve": "ascending_steps",
        "dialogue_style": "mystical_formal",
        "emotional_peaks": ["realm_break", "secret_reveal", "sacrifice"],
        "pacing_note": "New mystery layer every 10-15 chapters",
    },
    "Đô Thị": {
        "escalation_pattern": "social_climbing",
        "key_beats": [
            "Business rivalry escalation",
            "Hidden identity exposure",
            "Family conflict deepens",
            "Power structure collapse",
        ],
        "tension_curve": "wave",
        "dialogue_style": "modern_sharp",
        "emotional_peaks": ["public_humiliation", "revenge_success", "secret_exposed"],
        "pacing_note": "Social status change every 5-8 chapters",
    },
    "Ngôn Tình": {
        "escalation_pattern": "emotional_cycle",
        "key_beats": [
            "Misunderstanding → cold war → reconciliation",
            "Jealousy trigger from third party",
            "Sacrifice reveals true feelings",
            "External threat forces cooperation",
        ],
        "tension_curve": "oscillating",  # Up-down emotional waves
        "dialogue_style": "intimate_emotional",
        "emotional_peaks": ["heartbreak", "confession", "reunion"],
        "pacing_note": "Emotional cycle every 5-7 chapters. Dialogue density high.",
    },
    "Cung Đấu": {
        "escalation_pattern": "faction_warfare",
        "key_beats": [
            "Multi-faction alliance shifting",
            "Poison/assassination attempt",
            "Political favor manipulation",
            "New faction introduction forces realignment",
        ],
        "tension_curve": "escalating_spiral",
        "dialogue_style": "courtly_scheming",
        "emotional_peaks": ["betrayal_reveal", "power_seized", "ally_falls"],
        "pacing_note": "New faction every N chapters. Sentiment oscillate 30-40%.",
    },
    "Xuyên Không": {
        "escalation_pattern": "knowledge_advantage",
        "key_beats": [
            "Future knowledge creates advantage",
            "Butterfly effect causes unexpected crisis",
            "Historical event divergence",
            "Identity secret threatens exposure",
        ],
        "tension_curve": "wave",
        "dialogue_style": "anachronistic_mix",
        "emotional_peaks": ["timeline_crisis", "identity_exposed", "history_changed"],
        "pacing_note": "Knowledge advantage diminishes over time → new conflicts needed",
    },
    "Trọng Sinh": {
        "escalation_pattern": "revenge_arc",
        "key_beats": [
            "Revenge plan execution phase",
            "Enemy discovers protagonist's advantage",
            "Past ally becomes current threat",
            "Butterfly effect of changed decisions",
        ],
        "tension_curve": "ascending_steps",
        "dialogue_style": "calculating_cold",
        "emotional_peaks": ["revenge_complete", "new_threat", "moral_dilemma"],
        "pacing_note": "Each revenge target = one arc. New threats from changed timeline.",
    },
    "Kiếm Hiệp": {
        "escalation_pattern": "honor_conflict",
        "key_beats": [
            "Martial arts tournament escalation",
            "Master-disciple bond tested",
            "Justice vs loyalty dilemma",
            "Ultimate technique discovery",
        ],
        "tension_curve": "ascending_steps",
        "dialogue_style": "classical_heroic",
        "emotional_peaks": ["duel_climax", "betrayal_by_ally", "sacrifice_for_honor"],
        "pacing_note": "Honor dilemma every 8-10 chapters",
    },
}


def get_genre_rules(genre: str) -> dict:
    """Get drama rules for genre. Falls back to generic if not found."""
    # Try exact match first
    if genre in GENRE_DRAMA_RULES:
        return GENRE_DRAMA_RULES[genre]
    # Try partial match (Vietnamese genre names can vary)
    genre_lower = genre.lower()
    for key, rules in GENRE_DRAMA_RULES.items():
        if key.lower() in genre_lower or genre_lower in key.lower():
            return rules
    # Generic fallback
    return {
        "escalation_pattern": "standard",
        "key_beats": ["Conflict escalation", "Character revelation", "Climactic confrontation"],
        "tension_curve": "ascending",
        "dialogue_style": "natural",
        "emotional_peaks": ["climax", "revelation", "resolution"],
        "pacing_note": "Standard dramatic arc",
    }


def get_genre_enhancement_hints(genre: str, chapter_num: int, total_chapters: int) -> str:
    """Generate genre-specific enhancement hints for a chapter position."""
    rules = get_genre_rules(genre)
    position = chapter_num / max(total_chapters, 1)

    hints = [f"Thể loại: {genre} — Phong cách đối thoại: {rules['dialogue_style']}"]

    # Position-based beat suggestion
    if position < 0.25:
        hints.append(f"Giai đoạn mở đầu — thiết lập: {rules['key_beats'][0]}")
    elif position < 0.5:
        hints.append(f"Giai đoạn phát triển — leo thang: {rules['key_beats'][1]}")
        if rules['escalation_pattern'] == 'power_progression' and position > 0.35:
            hints.append("⚡ Đây là thời điểm seed phản bội sư phụ (~40% truyện)")
    elif position < 0.75:
        hints.append(f"Giai đoạn cao trào — xung đột: {rules['key_beats'][2]}")
    else:
        hints.append(f"Giai đoạn kết — giải quyết: {rules['key_beats'][3]}")

    # Emotional peak suggestions
    peak_text = ", ".join(rules['emotional_peaks'])
    hints.append(f"Đỉnh cảm xúc cần hướng tới: {peak_text}")
    hints.append(f"Lưu ý pacing: {rules['pacing_note']}")

    return "\n".join(hints)
