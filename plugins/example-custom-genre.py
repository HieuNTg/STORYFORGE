"""Example plugin: adds a custom genre "Cyberpunk VN" with its own drama rules.

Demonstrates:
- Registering a new genre by extending on_genre_rules
- Modifying scores in on_score (adds a small bonus when drama is very high)
- Leaving on_export as a no-op (default behaviour)

Copy and rename this file to create your own plugin. The plugin loader
automatically discovers any StoryForgePlugin subclass in plugins/*.py.
"""

from __future__ import annotations

from typing import Any

from plugins.base import StoryForgePlugin


# Drama rules definition for the custom genre
_CYBERPUNK_RULES: dict[str, Any] = {
    "escalation_pattern": "tech_dystopia",
    "key_beats": [
        "Nhân vật khám phá bí mật tập đoàn cầm quyền",
        "Cấy ghép công nghệ gây ra khủng hoảng nhân tính",
        "Liên minh ngầm bị lộ khiến bản đồ thế lực thay đổi",
        "Cuộc nổi dậy cuối cùng chống lại hệ thống kiểm soát",
    ],
    "tension_curve": "escalating_spiral",
    "dialogue_style": "đường phố kỹ thuật số",
    "emotional_peaks": ["lộ bí mật tập đoàn", "khủng hoảng bản sắc", "hy sinh vì tự do"],
    "pacing_note": "Căng thẳng công nghệ xen kẽ với xung đột nhân tính mỗi 6-8 chương",
}


class CustomGenrePlugin(StoryForgePlugin):
    """Adds Cyberpunk VN genre rules and a high-drama score bonus."""

    name = "custom-genre-cyberpunk"
    version = "0.1.0"
    description = "Adds Cyberpunk VN genre support and a small drama quality bonus."

    def register(self) -> None:
        """Validate that our rules dict has the expected structure."""
        required = {"escalation_pattern", "key_beats", "tension_curve", "dialogue_style"}
        missing = required - _CYBERPUNK_RULES.keys()
        if missing:
            raise ValueError(f"CustomGenrePlugin: missing rule keys {missing}")

    def on_genre_rules(self, genre: str, rules: dict[str, Any]) -> dict[str, Any] | None:
        """Inject Cyberpunk VN rules when the genre matches.

        Returns the custom rules dict for "Cyberpunk VN" (case-insensitive match).
        Returns None for all other genres so the existing rules are unchanged.
        """
        if "cyberpunk" in genre.lower():
            return dict(_CYBERPUNK_RULES)  # return a copy to avoid mutation
        return None

    def on_score(self, scores: dict[str, float]) -> dict[str, float] | None:
        """Apply a small +0.1 drama bonus when drama score is already >= 4.5.

        This demonstrates how a plugin can nudge scores post-hoc.
        Values are clamped to the [1, 5] range after adjustment.
        """
        drama = scores.get("drama", 0.0)
        if drama >= 4.5:
            adjusted = dict(scores)
            adjusted["drama"] = min(5.0, drama + 0.1)
            # Recalculate overall if present
            if "overall" in adjusted:
                dim_keys = ["coherence", "character_consistency", "drama", "writing_quality"]
                present = [adjusted[k] for k in dim_keys if k in adjusted]
                if present:
                    adjusted["overall"] = round(sum(present) / len(present), 4)
            return adjusted
        return None
