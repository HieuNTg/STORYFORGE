"""Thematic resonance tracker — ensures themes echo throughout story.

Feature #15: Track theme presence per chapter and detect theme drift.
"""

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from services.llm_client import LLMClient

logger = logging.getLogger(__name__)


@dataclass
class ThemePresence:
    """Track theme presence in a chapter."""
    chapter: int
    theme: str
    strength: float = 0.0  # 0-1
    manifestation: str = ""  # How theme appears
    symbols: list[str] = field(default_factory=list)


@dataclass
class ThematicState:
    """Track thematic resonance across story."""
    core_themes: list[str] = field(default_factory=list)
    theme_history: list[ThemePresence] = field(default_factory=list)
    symbol_registry: dict[str, list[int]] = field(default_factory=dict)  # symbol → chapters

    def add_presence(self, presence: ThemePresence) -> None:
        self.theme_history.append(presence)
        for symbol in presence.symbols:
            if symbol not in self.symbol_registry:
                self.symbol_registry[symbol] = []
            self.symbol_registry[symbol].append(presence.chapter)

    def get_theme_coverage(self, theme: str) -> list[int]:
        """Get chapters where theme appears."""
        return [
            p.chapter for p in self.theme_history
            if p.theme == theme and p.strength >= 0.3
        ]

    def get_dormant_themes(self, current_chapter: int, gap_threshold: int = 5) -> list[str]:
        """Get themes not seen for gap_threshold chapters."""
        dormant = []
        for theme in self.core_themes:
            chapters = self.get_theme_coverage(theme)
            if not chapters:
                dormant.append(theme)
            elif current_chapter - max(chapters) >= gap_threshold:
                dormant.append(theme)
        return dormant

    def get_theme_strength_trend(self, theme: str, window: int = 5) -> str:
        """Analyze theme strength trend.

        Returns: 'ascending' | 'descending' | 'stable' | 'absent'
        """
        relevant = [
            p for p in self.theme_history
            if p.theme == theme
        ][-window:]

        if len(relevant) < 2:
            return "absent" if not relevant else "stable"

        strengths = [p.strength for p in relevant]
        avg_change = sum(
            strengths[i] - strengths[i-1]
            for i in range(1, len(strengths))
        ) / (len(strengths) - 1)

        if avg_change > 0.1:
            return "ascending"
        elif avg_change < -0.1:
            return "descending"
        return "stable"


def initialize_thematic_state(premise: dict | None = None) -> ThematicState:
    """Initialize thematic state from premise."""
    state = ThematicState()

    if premise:
        # Extract themes from premise
        themes = premise.get("themes", [])
        if isinstance(themes, str):
            themes = [t.strip() for t in themes.split(",")]
        state.core_themes = themes[:5]

        # Core theme from premise statement
        core = premise.get("core_theme", "") or premise.get("premise_statement", "")
        if core and core not in state.core_themes:
            state.core_themes.insert(0, core[:50])

    return state


def analyze_theme_presence(
    llm: "LLMClient",
    chapter_content: str,
    chapter_number: int,
    core_themes: list[str],
    model: str | None = None,
) -> list[ThemePresence]:
    """Analyze theme presence in chapter.

    Returns list of ThemePresence for each detected theme.
    """
    if not core_themes:
        return []

    themes_text = "\n".join(f"- {t}" for t in core_themes[:5])

    result = llm.generate_json(
        system_prompt="Phân tích chủ đề. Trả JSON.",
        user_prompt=f"""Chương {chapter_number}:
{chapter_content[:3000]}

Chủ đề cốt lõi:
{themes_text}

Phân tích sự hiện diện của từng chủ đề:
- Độ mạnh (0.0-1.0)
- Cách thể hiện (qua hành động/đối thoại/biểu tượng)
- Biểu tượng liên quan

{{"themes": [{{"theme": "tên", "strength": 0.0-1.0, "manifestation": "mô tả", "symbols": ["biểu tượng"]}}]}}""",
        temperature=0.2,
        max_tokens=500,
        model_tier="cheap",
    )

    presences = []
    for t in result.get("themes", []):
        presences.append(ThemePresence(
            chapter=chapter_number,
            theme=t.get("theme", ""),
            strength=float(t.get("strength", 0.0)),
            manifestation=t.get("manifestation", ""),
            symbols=t.get("symbols", []),
        ))

    return presences


def detect_thematic_drift(
    state: ThematicState,
    current_chapter: int,
    total_chapters: int,
) -> dict:
    """Detect if story is drifting from core themes.

    Returns: {
        'drifting': bool,
        'dormant_themes': list,
        'declining_themes': list,
        'dominant_theme': str,
        'balance_score': float
    }
    """
    dormant = state.get_dormant_themes(current_chapter, gap_threshold=5)

    declining = []
    for theme in state.core_themes:
        trend = state.get_theme_strength_trend(theme)
        if trend == "descending":
            declining.append(theme)

    # Find dominant theme
    theme_scores = {}
    for theme in state.core_themes:
        presences = [
            p for p in state.theme_history
            if p.theme == theme
        ]
        if presences:
            theme_scores[theme] = sum(p.strength for p in presences) / len(presences)

    dominant = max(theme_scores, key=theme_scores.get) if theme_scores else ""

    # Calculate balance score (variance in theme coverage)
    if len(theme_scores) > 1:
        avg_score = sum(theme_scores.values()) / len(theme_scores)
        variance = sum((s - avg_score) ** 2 for s in theme_scores.values()) / len(theme_scores)
        balance = max(0, 1 - variance * 2)  # Lower variance = higher balance
    else:
        balance = 1.0

    return {
        "drifting": len(dormant) > 0 or len(declining) > len(state.core_themes) // 2,
        "dormant_themes": dormant,
        "declining_themes": declining,
        "dominant_theme": dominant,
        "balance_score": balance,
        "theme_scores": theme_scores,
    }


def format_thematic_guidance(
    drift_result: dict,
    state: ThematicState,
    chapter_number: int,
) -> str:
    """Format thematic guidance for chapter writing."""
    lines = []

    if drift_result.get("dormant_themes"):
        lines.append("## 📚 CHỦ ĐỀ CẦN NHẮC LẠI:")
        for t in drift_result["dormant_themes"][:3]:
            symbols = state.symbol_registry.get(t, [])
            symbol_hint = f" (symbols: {', '.join(symbols[:2])})" if symbols else ""
            lines.append(f"- {t}{symbol_hint}")

    if drift_result.get("declining_themes"):
        lines.append("\n## ⚠️ CHỦ ĐỀ ĐANG SUY YẾU:")
        for t in drift_result["declining_themes"][:2]:
            lines.append(f"- {t}")

    if not lines and drift_result.get("dominant_theme"):
        # Suggest balancing
        dominant = drift_result["dominant_theme"]
        others = [t for t in state.core_themes if t != dominant]
        if others:
            lines.append("## 📊 CÂN BẰNG CHỦ ĐỀ:")
            lines.append(f"- Chủ đề mạnh: {dominant}")
            lines.append(f"- Cần tăng: {', '.join(others[:2])}")

    return "\n".join(lines)


def audit_thematic_resonance(
    state: ThematicState,
    final_chapter: int,
) -> dict:
    """Audit thematic coverage at story end.

    Returns coverage and balance metrics.
    """
    coverage = {}
    for theme in state.core_themes:
        chapters = state.get_theme_coverage(theme)
        coverage[theme] = {
            "chapters": chapters,
            "count": len(chapters),
            "percentage": len(chapters) / final_chapter * 100 if final_chapter else 0,
            "trend": state.get_theme_strength_trend(theme),
        }

    # Symbol usage
    symbol_usage = {
        s: {"chapters": chs, "count": len(chs)}
        for s, chs in state.symbol_registry.items()
    }

    return {
        "theme_coverage": coverage,
        "symbol_usage": symbol_usage,
        "total_symbols": len(state.symbol_registry),
        "well_covered": [t for t, c in coverage.items() if c["percentage"] >= 50],
        "under_covered": [t for t, c in coverage.items() if c["percentage"] < 30],
    }
