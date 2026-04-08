"""Dialogue Subtext Layer — phân tích says-vs-means và tạo hướng dẫn đối thoại."""

import logging
from pydantic import BaseModel, Field
from models.schemas import Character, CharacterPsychology
from services.llm_client import LLMClient

logger = logging.getLogger(__name__)

DIALOGUE_SUBTEXT_GUIDANCE = """Phân tích đối thoại trong đoạn văn sau. Với MỖI câu thoại quan trọng, chỉ ra điều nhân vật nói và điều họ thực sự muốn.

NỘI DUNG:
{content}

NHÂN VẬT VÀ TÂM LÝ:
{character_psychology}

KIẾN THỨC CỦA TỪNG NHÂN VẬT:
{knowledge_state}

Trả về JSON:
{{
  "dialogue_analysis": [
    {{
      "character": "tên",
      "says": "câu nói nguyên văn",
      "means": "ý nghĩa thực sự / điều muốn đạt được",
      "subtext_type": "deflection/half_truth/loaded_silence/misdirection/genuine",
      "tension_contribution": 0.7
    }}
  ],
  "enhancement_guidance": "hướng dẫn cụ thể để cải thiện đối thoại: thêm im lặng đầy ý nghĩa, lời nói nửa vời, né tránh..."
}}"""


class DialogueLine(BaseModel):
    character: str
    says: str
    means: str
    subtext_type: str = "genuine"  # deflection|half_truth|loaded_silence|misdirection|genuine
    tension_contribution: float = 0.0


class DialogueSubtextAnalyzer:
    """Phân tích lớp subtext đối thoại và tạo hướng dẫn nâng cấp."""

    def __init__(self):
        self.llm = LLMClient()

    def analyze_dialogue(
        self,
        chapter_content: str,
        characters: list[Character],
    ) -> list[DialogueLine]:
        """Trích xuất và phân tích đối thoại từ nội dung chương."""
        char_desc = "\n".join(
            f"- {c.name}: {c.personality}. Bí mật: {c.secret or 'không có'}."
            for c in characters
        )
        try:
            result = self.llm.generate_json(
                system_prompt="Phân tích đối thoại chuyên sâu. Trả về JSON.",
                user_prompt=DIALOGUE_SUBTEXT_GUIDANCE.format(
                    content=chapter_content[:3000],
                    character_psychology=char_desc or "Không có thông tin",
                    knowledge_state="Không có thông tin kiến thức cụ thể",
                ),
                temperature=0.3,
                max_tokens=1024,
                model_tier="cheap",
            )
            lines = result.get("dialogue_analysis", [])
            return [
                DialogueLine(
                    character=d.get("character", ""),
                    says=d.get("says", ""),
                    means=d.get("means", ""),
                    subtext_type=d.get("subtext_type", "genuine"),
                    tension_contribution=float(d.get("tension_contribution", 0.0)),
                )
                for d in lines
            ]
        except Exception as e:
            logger.debug(f"Dialogue analysis failed: {e}")
            return []

    def generate_subtext_guidance(
        self,
        psychology_map: dict[str, CharacterPsychology],
        knowledge_state: dict[str, list[str]],
    ) -> str:
        """Tạo hướng dẫn đối thoại từ tâm lý và kiến thức từng nhân vật.

        Logic: nhân vật sợ X, không biết Y → khi Y xuất hiện thì né tránh hoặc nửa sự thật.
        """
        if not psychology_map:
            return ""

        parts: list[str] = []
        for char_name, psych in psychology_map.items():
            char_parts: list[str] = [f"[{char_name}]"]

            fear = (psych.goals.fear if psych.goals else "") or ""
            if hasattr(psych, "goals") and psych.goals:
                hidden = getattr(psych.goals, "hidden_motive", "") or ""
                if hidden:
                    char_parts.append(f"  Động cơ ẩn: {hidden}")
            if fear:
                char_parts.append(f"  Sợ: {fear}")

            defenses = getattr(psych, "defenses", []) or []
            if defenses:
                char_parts.append(f"  Cơ chế phòng vệ: {', '.join(defenses[:2])}")

            # known facts → character CAN speak openly about these
            known = knowledge_state.get(char_name, [])
            # Secrets from other chars this one doesn't know:
            all_facts = {f for facts in knowledge_state.values() for f in facts}
            unknown = [f for f in all_facts if f not in set(known)]
            if unknown:
                char_parts.append(
                    f"  Chưa biết: {', '.join(unknown[:3])} → "
                    "khi chủ đề này xuất hiện, dùng half_truth hoặc deflection"
                )

            parts.append("\n".join(char_parts))

        return "\n\n".join(parts)

    def format_for_prompt(self, guidance: str) -> str:
        """Định dạng hướng dẫn subtext để chèn vào ENHANCE_CHAPTER prompt."""
        if not guidance:
            return ""
        return (
            "\n\n=== HƯỚNG DẪN ĐỐI THOẠI SUBTEXT ===\n"
            "Áp dụng các lớp subtext sau cho đối thoại nhân vật:\n\n"
            f"{guidance}\n"
            "=== KẾT THÚC HƯỚNG DẪN ĐỐI THOẠI ==="
        )
