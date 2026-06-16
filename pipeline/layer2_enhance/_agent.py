"""Agent nhân vật với emotional state và trust network.

Mood/tension constant tables and the ``EmotionalState`` / ``TrustEdge`` value
objects live in ``_agent_state`` and are re-exported here so existing import
paths keep working.
"""

from models.schemas import AgentPost, Character, CharacterPsychology

from pipeline.layer2_enhance._agent_state import (
    MOOD_DRAMA,
    MOOD_TRIGGERS,
    TENSION_DELTAS,
    EmotionalState,
    TrustEdge,
)

__all__ = [
    "MOOD_DRAMA",
    "MOOD_TRIGGERS",
    "TENSION_DELTAS",
    "EmotionalState",
    "TrustEdge",
    "CharacterAgent",
]


class CharacterAgent:
    """Agent with emotional state, trust network, and memory."""

    def __init__(self, character: Character):
        self.character = character
        self.memory: list[str] = []
        self._memory_scores: list[float] = []
        self.posts: list[AgentPost] = []
        self.emotion = EmotionalState()
        self.trust_map: dict[str, TrustEdge] = {}
        self.psychology: CharacterPsychology | None = None
        self.waypoint_floor: float = 0.0
        self.waypoint_stage: str = ""

    @property
    def emotional_state(self) -> EmotionalState:
        """Alias for emotion — compatibility with reaction chain code."""
        return self.emotion

    def set_waypoint(self, stage: str, progress_pct: float):
        self.waypoint_stage = stage
        self.waypoint_floor = max(0.0, min(1.0, float(progress_pct)))

    def add_memory(self, event: str, importance: float = 0.0):
        """Thêm ký ức với điểm quan trọng. Sự kiện quan trọng cao sẽ được giữ lại khi cắt tỉa."""
        if importance <= 0:
            importance = self._score_importance(event)
        self.memory.append(event)
        self._memory_scores.append(importance)
        if len(self.memory) > 50:
            self._prune_memory()

    def _score_importance(self, event: str) -> float:
        """Chấm điểm độ quan trọng của ký ức. Sự kiện leo thang/có liên quan trực tiếp được điểm cao hơn."""
        escalation_keywords = {
            "phản_bội",
            "tiết_lộ",
            "đối_đầu",
            "hy_sinh",
            "đảo_ngược",
            "escalation",
        }
        if any(kw in event for kw in escalation_keywords):
            return 1.0
        if self.character.name in event:
            return 0.8
        return 0.5

    def _prune_memory(self):
        """Xóa ký ức kém quan trọng nhất để duy trì giới hạn 50."""
        while len(self.memory) > 50:
            min_idx = min(
                range(len(self._memory_scores)), key=lambda i: self._memory_scores[i]
            )
            self.memory.pop(min_idx)
            self._memory_scores.pop(min_idx)

    def process_event(self, event_type: str, is_target: bool = False):
        """Update emotional state based on event. Called from reaction chain."""
        self.emotion.update_mood(event_type)
        if is_target:
            self.emotion.update_stakes(0.15)
            self.emotion.update_energy(-0.1)
        else:
            self.emotion.update_energy(-0.05)

    def get_trust(self, target: str) -> TrustEdge:
        """Get or create trust edge to target character."""
        if target not in self.trust_map:
            self.trust_map[target] = TrustEdge(target)
        return self.trust_map[target]

    def get_drama_multiplier(self) -> float:
        """Tính hệ số kịch tính pha trộn psychology + emotion.

        Khi có psychology: vuln_avg * pressure + emotion.drama_multiplier * 0.3
        Khi không có psychology: fallback về emotion.drama_multiplier.
        """
        if self.psychology and self.psychology.vulnerabilities:
            vuln_avg = sum(
                v.drama_multiplier for v in self.psychology.vulnerabilities
            ) / len(self.psychology.vulnerabilities)
            blended = (
                vuln_avg * (1.0 + self.psychology.pressure)
                + self.emotion.drama_multiplier * 0.3
            )
            return min(3.0, max(self.emotion.drama_multiplier, blended))
        return self.emotion.drama_multiplier

    def get_arc_summary(self) -> str:
        """Tóm tắt arc cảm xúc để đưa vào prompt."""
        if not self.emotion.arc_trajectory:
            return "Chưa có dữ liệu arc."
        moods = [m for _, m, _ in self.emotion.arc_trajectory]
        return f"Arc cảm xúc: {' → '.join(moods[-5:])}"

    def get_emotional_context(self) -> str:
        """Format emotional state + trust + psychology for prompt injection."""
        trust_text = ", ".join(
            f"{name}: {edge.trust:.0f}/100" for name, edge in self.trust_map.items()
        )
        base = (
            f"{self.emotion.to_prompt_text()} | Tin tưởng: [{trust_text or 'chưa rõ'}]"
        )
        if self.psychology:
            psych_parts = []
            if self.psychology.goals.fear:
                psych_parts.append(f"Nỗi sợ: {self.psychology.goals.fear}")
            if self.psychology.vulnerabilities:
                wounds = ", ".join(v.wound for v in self.psychology.vulnerabilities[:2])
                psych_parts.append(f"Điểm yếu: {wounds}")
            if self.psychology.pressure > 0.1:
                psych_parts.append(f"Áp lực: {self.psychology.pressure:.2f}")
            if psych_parts:
                base += " | " + " | ".join(psych_parts)
        return base
