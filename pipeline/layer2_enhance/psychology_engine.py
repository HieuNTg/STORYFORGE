"""Psychology Engine — trích xuất tâm lý sâu của nhân vật và tính toán kịch tính."""

import logging
from models.schemas import Character, CharacterPsychology, GoalHierarchy, VulnerabilityEntry
from services.llm_client import LLMClient
from services.prompts.layer2_enhanced_prompts import EXTRACT_PSYCHOLOGY

logger = logging.getLogger(__name__)

_WOUND_KEYWORDS = {
    "phản_bội", "bỏ rơi", "mất mát", "thất bại", "sỉ nhục",
    "xấu hổ", "bị lừa", "tổn thương", "cô đơn", "chối bỏ",
}


class PsychologyEngine:
    """Trích xuất và quản lý tâm lý nhân vật để tăng cường kịch tính."""

    def __init__(self):
        self.llm = LLMClient()

    def extract_psychology(
        self,
        character: Character,
        all_characters: list[Character],
    ) -> CharacterPsychology:
        """Gọi LLM để trích xuất tâm lý sâu từ các trường Character hiện có.

        Trả về CharacterPsychology rỗng nếu LLM thất bại (non-fatal).
        """
        other_names = ", ".join(
            c.name for c in all_characters if c.name != character.name
        ) or "không có"

        try:
            result = self.llm.generate_json(
                system_prompt=(
                    "Bạn là chuyên gia tâm lý học nhân vật. "
                    "Phân tích kỹ lưỡng và trả về JSON chính xác. "
                    "LUÔN viết bằng tiếng Việt."
                ),
                user_prompt=EXTRACT_PSYCHOLOGY.format(
                    name=character.name,
                    personality=character.personality or "không rõ",
                    background=character.background or "không rõ",
                    motivation=character.motivation or "không rõ",
                    secret=character.secret or "không có",
                    internal_conflict=character.internal_conflict or "không có",
                    breaking_point=character.breaking_point or "không rõ",
                    other_characters=other_names,
                ),
                temperature=0.7,
            )

            goals = GoalHierarchy(
                primary_goal=result.get("primary_goal", ""),
                hidden_motive=result.get("hidden_motive", ""),
                fear=result.get("fear", ""),
                shame_trigger=result.get("shame_trigger", ""),
            )

            vulnerabilities: list[VulnerabilityEntry] = []
            for v in result.get("vulnerabilities", []):
                try:
                    vulnerabilities.append(VulnerabilityEntry(
                        wound=v.get("wound", ""),
                        exploiters=v.get("exploiters", []),
                        drama_multiplier=float(v.get("drama_multiplier", 1.5)),
                    ))
                except Exception as ve:
                    logger.debug(f"Bỏ qua vulnerability lỗi cho {character.name}: {ve}")

            defenses = result.get("defenses", [])
            if not isinstance(defenses, list):
                defenses = []

            psychology = CharacterPsychology(
                character_name=character.name,
                goals=goals,
                vulnerabilities=vulnerabilities,
                pressure=0.0,
                defenses=defenses,
            )
            logger.info(
                f"Trích xuất tâm lý '{character.name}': "
                f"{len(vulnerabilities)} điểm yếu, {len(defenses)} cơ chế phòng vệ"
            )
            return psychology

        except Exception as e:
            logger.warning(f"Không thể trích xuất tâm lý '{character.name}': {e}")
            return CharacterPsychology(character_name=character.name)

    def compute_drama_potential(self, psychology: CharacterPsychology) -> float:
        """Tính tiềm năng kịch tính: avg(vuln.drama_multiplier) * pressure.

        Bounded [0.5, 3.0]. Nếu không có vulnerability, trả về 0.5.
        """
        if not psychology.vulnerabilities:
            return 0.5
        avg_multiplier = sum(
            v.drama_multiplier for v in psychology.vulnerabilities
        ) / len(psychology.vulnerabilities)
        potential = avg_multiplier * psychology.pressure
        return min(3.0, max(0.5, potential))

    def update_pressure(
        self,
        psychology: CharacterPsychology,
        event_type: str,
        attacker: str,
    ) -> None:
        """Tăng áp lực khi sự kiện nhắm vào điểm yếu của nhân vật.

        - +0.15 nếu attacker có thể khai thác một vulnerability
        - +0.1 nếu event_type khớp với từ khóa vết thương
        """
        delta = 0.0
        event_lower = event_type.lower()

        for vuln in psychology.vulnerabilities:
            if attacker in vuln.exploiters:
                delta += 0.15
                break  # chỉ tính một lần dù có nhiều vulnerability

        if any(kw in event_lower for kw in _WOUND_KEYWORDS):
            delta += 0.1

        if delta > 0:
            psychology.pressure = min(1.0, psychology.pressure + delta)
            logger.debug(
                f"Áp lực '{psychology.character_name}' tăng {delta:.2f} "
                f"(attacker={attacker}, event={event_type}) → {psychology.pressure:.2f}"
            )

    def apply_thread_pressure(
        self,
        psychology: CharacterPsychology,
        threads: list,
        current_chapter: int,
        max_bump: float = 0.30,
    ) -> float:
        """Bump pressure for characters involved in stale urgent plot threads.

        Rules:
          - urgency >= 4 AND staleness (current - last_mentioned) >= 2 → +0.15
          - urgency == 5 AND status == 'open' → additional +0.05
          - Per-call cumulative bump capped at max_bump (default 0.30).

        Returns the applied delta (0.0 if no bump). Safe on empty threads.
        """
        if not threads:
            return 0.0
        name = psychology.character_name
        total = 0.0
        matched = []
        for t in threads:
            involved = getattr(t, "involved_characters", []) or []
            if name not in involved:
                continue
            urgency = getattr(t, "urgency", 3) or 3
            if urgency < 4:
                continue
            # Convention: fall back to planted_chapter when never mentioned (0-default)
            last_ch = getattr(t, "last_mentioned_chapter", 0) or getattr(t, "planted_chapter", current_chapter)
            if current_chapter - last_ch < 2:
                continue
            bump = 0.15
            if urgency == 5 and getattr(t, "status", "open") == "open":
                bump += 0.05
            total = min(max_bump, total + bump)
            matched.append(getattr(t, "thread_id", "?"))
            if total >= max_bump:
                break
        if total > 0:
            psychology.pressure = min(1.0, psychology.pressure + total)
            logger.info(
                f"[Pressure] {name}: +{total:.2f} from {len(matched)} urgent stale threads "
                f"→ {psychology.pressure:.2f}"
            )
        return total
