"""Bộ điều khiển cường độ mô phỏng thích nghi — tự động leo thang/hạ nhiệt theo drama."""

import logging
from pydantic import BaseModel

logger = logging.getLogger(__name__)

DRAMA_THRESHOLD = 0.5   # Dưới ngưỡng này = vòng yếu
DRAMA_TARGET = 0.65     # Dừng khi trung bình đạt mức này
MIN_ROUNDS = 3
MAX_ROUNDS = 10


class RoundFeedback(BaseModel):
    round_number: int
    drama_score: float
    escalation_applied: bool = False
    note: str = ""


class AdaptiveController:
    """Điều chỉnh cường độ mô phỏng dựa trên phản hồi drama từng vòng."""

    def __init__(
        self,
        base_intensity: dict,
        min_rounds: int = 3,
        max_rounds: int = 10,
        pacing_directive: str = "",
    ):
        self.base = dict(base_intensity)
        self.current = dict(base_intensity)
        self.min_rounds = min_rounds
        self.max_rounds = max_rounds
        self.history: list[RoundFeedback] = []
        self.pacing_directive = (pacing_directive or "").strip().lower()
        if self.pacing_directive == "slow_down":
            self.drama_target = 0.55
        elif self.pacing_directive == "escalate":
            self.drama_target = 0.75
        else:
            self.drama_target = DRAMA_TARGET
        if self.pacing_directive:
            logger.info(f"[Adaptive] pacing={self.pacing_directive} → DRAMA_TARGET={self.drama_target}")

    def record_round(self, round_num: int, drama_score: float) -> None:
        """Ghi lại kết quả vòng và điều chỉnh cường độ cho vòng tiếp theo."""
        fb = RoundFeedback(round_number=round_num, drama_score=drama_score)
        if drama_score < DRAMA_THRESHOLD:
            self._escalate()
            fb.escalation_applied = True
            fb.note = f"Vòng yếu ({drama_score:.2f} < {DRAMA_THRESHOLD}), leo thang"
            logger.info(f"[Adaptive] Vòng {round_num}: drama thấp {drama_score:.2f} → leo thang")
        elif drama_score > 0.85:
            self._deescalate()
            fb.note = f"Drama rất cao ({drama_score:.2f}), hạ nhiệt nhẹ"
            logger.info(f"[Adaptive] Vòng {round_num}: drama cao {drama_score:.2f} → hạ nhiệt")
        self.history.append(fb)

    def should_continue(self, round_num: int) -> bool:
        """True nếu mô phỏng nên chạy thêm một vòng nữa."""
        if round_num <= self.min_rounds:
            return True
        if round_num > self.max_rounds:
            return False
        if not self.history:
            return True
        avg = sum(h.drama_score for h in self.history) / len(self.history)
        return avg < self.drama_target

    def get_current_config(self) -> dict:
        """Trả về cấu hình cường độ hiện tại (có thể đã được leo thang)."""
        return dict(self.current)

    def _escalate(self) -> None:
        """Tăng nhiệt độ +0.05, escalation_scale +0.15, reaction_depth +1."""
        self.current["temperature"] = min(1.0, self.current.get("temperature", 0.85) + 0.05)
        self.current["escalation_scale"] = min(2.0, self.current.get("escalation_scale", 1.0) + 0.15)
        self.current["reaction_depth"] = min(4, self.current.get("reaction_depth", 2) + 1)

    def _deescalate(self) -> None:
        """Giảm nhẹ nhiệt độ -0.03, reaction_depth -1."""
        self.current["temperature"] = max(0.7, self.current.get("temperature", 0.85) - 0.03)
        self.current["reaction_depth"] = max(1, self.current.get("reaction_depth", 2) - 1)

    def get_tension_modifier_actual(self, genre: str, round_num: int, total_rounds: int) -> float:
        """Kết hợp đường cong toán học (0.6) với drama thực tế (0.4) cho tension modifier."""
        try:
            from pipeline.layer2_enhance.drama_patterns import get_tension_modifier
            position = round_num / max(1, total_rounds)
            math_modifier = get_tension_modifier(genre, position)
        except Exception as e:
            logger.debug(f"get_tension_modifier lỗi: {e}")
            math_modifier = 1.0

        if not self.history:
            return math_modifier

        avg_drama = sum(h.drama_score for h in self.history) / len(self.history)
        # Kết hợp: drama thực tế cao → giảm ngưỡng (dễ leo thang hơn)
        actual_component = 1.0 - avg_drama  # 0 khi drama=1.0, 1 khi drama=0.0
        blended = 0.6 * math_modifier + 0.4 * actual_component
        return round(blended, 4)


# ══════════════════════════════════════════════════════════════════════════════
# Phase 6: Genre Drama Ceiling Controller
# ══════════════════════════════════════════════════════════════════════════════


class DramaCeilingController:
    """Enforce drama ceiling to prevent melodrama.

    Works alongside AdaptiveController to cap drama levels per genre.
    """

    def __init__(self, genre: str, chapter_position: float = 0.5):
        from pipeline.layer2_enhance.drama_patterns import get_genre_drama_ceiling
        self.genre = genre
        self.chapter_position = chapter_position
        self.base_ceiling = get_genre_drama_ceiling(genre)
        self.ceiling = self._compute_adjusted_ceiling()
        self.violations: list[dict] = []

    def _compute_adjusted_ceiling(self) -> float:
        """Compute ceiling adjusted for story position."""
        ceiling = self.base_ceiling

        # Climax allowance
        if 0.7 <= self.chapter_position <= 0.9:
            ceiling = min(0.95, ceiling + 0.10)
        # Opening/setup — lower ceiling
        elif self.chapter_position < 0.15:
            ceiling = max(0.50, ceiling - 0.10)

        return ceiling

    def check_and_cap(self, drama_score: float, chapter_num: int = 0) -> tuple[float, bool]:
        """Check drama score and cap if needed.

        Returns (capped_score, was_capped).
        """
        if drama_score <= self.ceiling:
            return drama_score, False

        self.violations.append({
            "chapter": chapter_num,
            "original": drama_score,
            "capped_to": self.ceiling,
            "excess": drama_score - self.ceiling,
        })

        logger.info(
            f"[DramaCeiling] Ch{chapter_num}: capped {drama_score:.2f} → {self.ceiling:.2f} "
            f"(genre={self.genre}, position={self.chapter_position:.0%})"
        )

        return self.ceiling, True

    def check_melodrama(self, content: str, chapter_num: int = 0) -> tuple[bool, list[str]]:
        """Check for melodrama in content.

        Returns (is_melodramatic, indicators_found).
        """
        from pipeline.layer2_enhance.drama_patterns import detect_melodrama

        is_melodrama, found = detect_melodrama(content, threshold=3)

        if is_melodrama:
            self.violations.append({
                "chapter": chapter_num,
                "type": "melodrama",
                "indicators": found,
            })
            logger.warning(
                f"[DramaCeiling] Ch{chapter_num}: melodrama detected ({len(found)} indicators)"
            )

        return is_melodrama, found

    def get_enforcement_prompt(self) -> str:
        """Get prompt block for drama ceiling enforcement."""
        from pipeline.layer2_enhance.drama_patterns import format_drama_ceiling_prompt
        return format_drama_ceiling_prompt(self.genre, self.chapter_position)

    def get_summary(self) -> dict:
        """Get summary of ceiling enforcement."""
        capped = [v for v in self.violations if "capped_to" in v]
        melodrama = [v for v in self.violations if v.get("type") == "melodrama"]

        return {
            "genre": self.genre,
            "ceiling": self.ceiling,
            "position": self.chapter_position,
            "total_capped": len(capped),
            "total_melodrama": len(melodrama),
            "avg_excess": (
                sum(v["excess"] for v in capped) / len(capped)
                if capped else 0.0
            ),
        }


def apply_drama_ceiling_to_events(
    events: list,
    genre: str,
    chapter_position: float = 0.5,
) -> list:
    """Apply drama ceiling to simulation events.

    Modifies drama_score in-place and returns modified events.
    """
    controller = DramaCeilingController(genre, chapter_position)

    for event in events:
        if hasattr(event, "drama_score"):
            original = event.drama_score
            capped, was_capped = controller.check_and_cap(original)
            if was_capped:
                event.drama_score = capped

    return events
