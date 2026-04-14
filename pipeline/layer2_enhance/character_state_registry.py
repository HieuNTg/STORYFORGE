"""Character State Registry — theo dõi trạng thái nhân vật xuyên chương.

Tracks: location, physical_state, emotional_state, inventory, relationships_changed.
Extracted before enhance, injected as constraints, validated after enhance.
"""

import logging
from pydantic import BaseModel, Field
from services.llm_client import LLMClient

logger = logging.getLogger(__name__)


class CharacterState(BaseModel):
    """Trạng thái nhân vật tại một thời điểm."""
    name: str
    chapter_number: int = 0
    location: str = ""
    physical_state: str = ""  # injuries, fatigue, appearance changes
    emotional_state: str = ""  # mood, mental state
    inventory: list[str] = Field(default_factory=list)  # items held/acquired
    companions: list[str] = Field(default_factory=list)  # who they're with
    goals_active: list[str] = Field(default_factory=list)  # immediate goals
    secrets_revealed: list[str] = Field(default_factory=list)  # secrets exposed this chapter


class CharacterStateRegistry:
    """Quản lý trạng thái nhân vật xuyên chương."""

    EXTRACT_STATE_PROMPT = """Phân tích đoạn văn và trích xuất trạng thái của nhân vật "{name}".

Nội dung chương {chapter_number}:
{content}

Trả về JSON với các trường:
{{
  "location": "vị trí hiện tại của nhân vật (rỗng nếu không rõ)",
  "physical_state": "trạng thái thể chất (bị thương, mệt mỏi, thay đổi ngoại hình...)",
  "emotional_state": "trạng thái cảm xúc (vui, buồn, tức giận, lo lắng...)",
  "inventory": ["danh sách vật phẩm đang mang"],
  "companions": ["danh sách người đi cùng"],
  "goals_active": ["mục tiêu đang theo đuổi"],
  "secrets_revealed": ["bí mật nào được tiết lộ trong chương này"]
}}

Chỉ ghi nhận thông tin CHẮC CHẮN xuất hiện trong văn bản. Nếu không rõ, để rỗng."""

    def __init__(self):
        self.states: dict[str, dict[int, CharacterState]] = {}  # name -> chapter -> state
        self.llm = LLMClient()

    def extract_states_from_chapter(
        self,
        chapter_content: str,
        chapter_number: int,
        character_names: list[str],
    ) -> list[CharacterState]:
        """Trích xuất trạng thái của tất cả nhân vật từ một chương."""
        results = []
        content_truncated = chapter_content[:5000]

        for name in character_names:
            # Skip if character not mentioned in chapter
            if name.lower() not in chapter_content.lower():
                continue

            try:
                result = self.llm.generate_json(
                    system_prompt="Trích xuất trạng thái nhân vật. Trả về JSON chính xác.",
                    user_prompt=self.EXTRACT_STATE_PROMPT.format(
                        name=name,
                        chapter_number=chapter_number,
                        content=content_truncated,
                    ),
                    temperature=0.1,
                    max_tokens=500,
                    model_tier="cheap",
                )

                state = CharacterState(
                    name=name,
                    chapter_number=chapter_number,
                    location=result.get("location", "") or "",
                    physical_state=result.get("physical_state", "") or "",
                    emotional_state=result.get("emotional_state", "") or "",
                    inventory=result.get("inventory", []) or [],
                    companions=result.get("companions", []) or [],
                    goals_active=result.get("goals_active", []) or [],
                    secrets_revealed=result.get("secrets_revealed", []) or [],
                )

                # Store in registry
                if name not in self.states:
                    self.states[name] = {}
                self.states[name][chapter_number] = state
                results.append(state)

                logger.debug(f"Extracted state for {name} ch{chapter_number}: loc={state.location}")

            except Exception as e:
                logger.warning(f"Failed to extract state for {name} ch{chapter_number}: {e}")

        return results

    def get_state(self, name: str, chapter_number: int) -> CharacterState | None:
        """Lấy trạng thái nhân vật tại chương cụ thể."""
        return self.states.get(name, {}).get(chapter_number)

    def get_last_known_state(self, name: str, before_chapter: int) -> CharacterState | None:
        """Lấy trạng thái gần nhất TRƯỚC chương hiện tại."""
        char_states = self.states.get(name, {})
        if not char_states:
            return None

        # Find most recent chapter before current
        valid_chapters = [ch for ch in char_states.keys() if ch < before_chapter]
        if not valid_chapters:
            return None

        latest = max(valid_chapters)
        return char_states[latest]

    def build_from_draft(self, draft, progress_callback=None) -> "CharacterStateRegistry":
        """Xây dựng registry từ toàn bộ draft."""
        characters = getattr(draft, "characters", []) or []
        char_names = [c.name for c in characters]
        chapters = getattr(draft, "chapters", []) or []

        for ch in chapters:
            content = getattr(ch, "content", "") or ""
            ch_num = getattr(ch, "chapter_number", 0)
            if content and ch_num:
                self.extract_states_from_chapter(content, ch_num, char_names)
                if progress_callback:
                    progress_callback(f"[StateRegistry] Extracted states for ch{ch_num}")

        logger.info(f"CharacterStateRegistry: {len(self.states)} characters tracked")
        return self

    def format_constraints_for_chapter(self, chapter_number: int) -> str:
        """Tạo text ràng buộc để inject vào enhance prompt."""
        lines = []
        for name, chapters in self.states.items():
            state = self.get_last_known_state(name, chapter_number)
            if state is None:
                continue

            parts = [f"**{name}** (Ch{state.chapter_number}):"]
            if state.location:
                parts.append(f"  - Vị trí: {state.location}")
            if state.physical_state:
                parts.append(f"  - Thể chất: {state.physical_state}")
            if state.emotional_state:
                parts.append(f"  - Cảm xúc: {state.emotional_state}")
            if state.companions:
                parts.append(f"  - Đang cùng: {', '.join(state.companions)}")
            if state.inventory:
                parts.append(f"  - Đồ vật: {', '.join(state.inventory[:3])}")

            if len(parts) > 1:
                lines.append("\n".join(parts))

        if not lines:
            return ""

        return "## Trạng thái nhân vật hiện tại\n" + "\n".join(lines)

    def validate_chapter_states(
        self,
        enhanced_content: str,
        chapter_number: int,
        character_names: list[str],
    ) -> list[dict]:
        """Kiểm tra enhanced content có vi phạm state constraints không."""
        violations = []

        for name in character_names:
            prev_state = self.get_last_known_state(name, chapter_number)
            if prev_state is None:
                continue

            # Check location continuity
            if prev_state.location and name.lower() in enhanced_content.lower():
                # Simple heuristic: if char was at location X, and suddenly at Y
                # without mention of travel, flag it
                try:
                    result = self.llm.generate_json(
                        system_prompt="Kiểm tra tính nhất quán vị trí. Trả về JSON.",
                        user_prompt=f"""Nhân vật "{name}" ở "{prev_state.location}" cuối chương trước.

Nội dung chương mới:
{enhanced_content[:3000]}

Trả về:
{{
  "current_location": "vị trí trong chương mới (rỗng nếu không đề cập)",
  "location_changed": true/false,
  "transition_explained": true/false,
  "violation": "mô tả vi phạm nếu có, rỗng nếu không"
}}""",
                        temperature=0.1,
                        max_tokens=200,
                        model_tier="cheap",
                    )

                    if result.get("location_changed") and not result.get("transition_explained"):
                        violation_msg = result.get("violation", "")
                        if violation_msg:
                            violations.append({
                                "type": "location_continuity",
                                "character": name,
                                "chapter": chapter_number,
                                "description": violation_msg,
                                "severity": "warning",
                            })

                except Exception as e:
                    logger.debug(f"Location validation failed for {name}: {e}")

            # Check physical state continuity
            if prev_state.physical_state:
                # If char was injured, check if still mentioned or healed
                injury_keywords = ["bị thương", "chấn thương", "máu", "đau"]
                had_injury = any(kw in prev_state.physical_state.lower() for kw in injury_keywords)
                if had_injury:
                    mentions_injury = any(kw in enhanced_content.lower() for kw in injury_keywords)
                    mentions_healing = any(kw in enhanced_content.lower() for kw in ["hồi phục", "lành", "chữa"])
                    if not mentions_injury and not mentions_healing and name.lower() in enhanced_content.lower():
                        violations.append({
                            "type": "physical_state_continuity",
                            "character": name,
                            "chapter": chapter_number,
                            "description": f"{name} bị thương ('{prev_state.physical_state}') nhưng chương mới không đề cập",
                            "severity": "warning",
                        })

        return violations
