"""Emotional state + trust primitives for the character agent.

Internal module for ``_agent``: relationship/mood constant tables and the
small :class:`EmotionalState` and :class:`TrustEdge` value objects that
:class:`~pipeline.layer2_enhance._agent.CharacterAgent` composes. Public names
are re-exported from ``_agent`` so existing import paths keep working.
"""

# Tension deltas by relationship type
TENSION_DELTAS = {
    "đồng_minh": -0.1,
    "liên_minh": -0.1,
    "đối_thủ": 0.2,
    "kẻ_thù": 0.3,
    "phản_bội": 0.3,
    "tình_nhân": -0.15,
    "sư_phụ": -0.05,
    "gia_đình": -0.1,
    "chưa_rõ": 0.0,
}

# Moods and their drama multipliers
MOOD_DRAMA = {
    "bình_thường": 1.0,
    "tức_giận": 1.5,
    "sợ_hãi": 1.3,
    "đau_khổ": 1.4,
    "hận_thù": 1.8,
    "yêu": 1.2,
    "tham_lam": 1.3,
    "kiêu_ngạo": 1.4,
    "tuyệt_vọng": 1.6,
    "quyết_tâm": 1.1,
}

# Mood transitions based on event types
MOOD_TRIGGERS = {
    "phản_bội": "phẫn_nộ",
    "tiết_lộ": "sốc",
    "đối_đầu": "quyết_tâm",
    "hy_sinh": "đau_khổ",
    "đảo_ngược": "hoang_mang",
    "liên_minh": "hy_vọng",
    "xung_đột": "căng_thẳng",
}


class EmotionalState:
    """Track character's emotional evolution across simulation rounds."""

    def __init__(self):
        self.mood: str = "bình_thường"
        self.energy: float = 0.7  # 0=exhausted, 1=peak
        self.stakes: float = 0.3  # 0=nothing to lose, 1=everything at stake
        self.mood_history: list[str] = []
        self.arc_trajectory: list[
            tuple[int, str, float]
        ] = []  # (vòng, tâm_trạng, drama_multiplier)

    def update(self, new_mood: str, energy_delta: float = 0, stakes_delta: float = 0):
        """Update emotional state. Records history."""
        if new_mood and new_mood in MOOD_DRAMA:
            self.mood_history.append(self.mood)
            self.mood = new_mood
        self.energy = max(0.0, min(1.0, self.energy + energy_delta))
        self.stakes = max(0.0, min(1.0, self.stakes + stakes_delta))

    def update_mood(self, event_type: str):
        """Update mood based on event type using MOOD_TRIGGERS mapping."""
        new_mood = MOOD_TRIGGERS.get(event_type)
        if new_mood and new_mood != self.mood:
            self.mood_history.append(self.mood)
            self.mood = new_mood
            if len(self.mood_history) > 20:
                self.mood_history = self.mood_history[-20:]

    def update_energy(self, delta: float):
        """Adjust energy (positive=gain, negative=drain)."""
        self.energy = max(0.0, min(1.0, self.energy + delta))

    def update_stakes(self, delta: float):
        """Adjust personal stakes."""
        self.stakes = max(0.0, min(1.0, self.stakes + delta))

    @property
    def drama_multiplier(self) -> float:
        """How much this character's state amplifies drama. Bounded to [0.5, 3.0]."""
        base = MOOD_DRAMA.get(self.mood, 1.0)
        desperation = self.stakes * (1.0 - self.energy) * 0.5
        return min(3.0, max(0.5, base + desperation))

    def record_round(self, round_number: int):
        """Ghi lại trạng thái hiện tại để theo dõi arc cảm xúc."""
        self.arc_trajectory.append((round_number, self.mood, self.drama_multiplier))

    def to_prompt_text(self) -> str:
        """Format for LLM prompt injection."""
        return (
            f"Tâm trạng: {self.mood} | Năng lượng: {self.energy:.1f} | "
            f"Mức rủi ro: {self.stakes:.1f}"
        )


class TrustEdge:
    """Directed trust relationship between two characters."""

    def __init__(self, target: str, trust: float = 50.0):
        self.target = target
        self.trust = trust  # 0-100
        self.history: list[str] = []

    def update(self, delta: float, reason: str = ""):
        """Modify trust. Negative = betrayal/distrust."""
        old = self.trust
        self.trust = max(0.0, min(100.0, self.trust + delta))
        if reason:
            self.history.append(f"{old:.0f}→{self.trust:.0f}: {reason[:80]}")

    @property
    def is_betrayal_trigger(self) -> bool:
        """Trust dropped >30 points recently (last update)."""
        if not self.history:
            return False
        last = self.history[-1]
        parts = last.split("→")
        if len(parts) >= 2:
            try:
                old_val = float(parts[0])
                new_val = float(parts[1].split(":")[0])
                return (old_val - new_val) > 30
            except ValueError:
                return False
        return False
