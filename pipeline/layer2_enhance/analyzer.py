"""Phân tích truyện - trích xuất mối quan hệ và xung đột."""

import logging
from models.schemas import StoryDraft, Relationship, RelationType
from services.llm_client import LLMClient
from services import prompts

logger = logging.getLogger(__name__)


class StoryAnalyzer:
    """Phân tích truyện để xây dựng đồ thị quan hệ nhân vật."""

    LAYER = 2

    def __init__(self):
        self.llm = LLMClient()
        self._layer_model = self.llm.model_for_layer(self.LAYER)

    def analyze(self, draft: StoryDraft) -> dict:
        """Phân tích truyện, trả về relationships, conflicts, untapped drama."""
        chars_text = "\n".join(
            f"- {c.name} ({c.role}): {c.personality}, Động lực: {c.motivation}"
            for c in draft.characters
        )
        synopsis = draft.synopsis
        if not synopsis and draft.chapters:
            # Fallback: kết hợp 300 ký tự đầu từ mỗi chương làm tóm tắt
            parts = []
            for ch in draft.chapters:
                # Ưu tiên summary nếu có, không thì lấy nội dung đầu
                text = ch.summary if ch.summary else ch.content[:300]
                if text:
                    parts.append(f"Chương {ch.chapter_number} ({ch.title}): {text.strip()}")
            synopsis = "\n".join(parts) or "Không có tóm tắt."

        result = self.llm.generate_json(
            system_prompt="Bạn là nhà phân tích truyện chuyên sâu. Trả về JSON.",
            user_prompt=prompts.ANALYZE_STORY.format(
                title=draft.title,
                genre=draft.genre,
                characters=chars_text,
                synopsis=synopsis,
            ),
            model_tier="cheap",
        )

        # Parse relationships
        relationships = []
        for r in result.get("relationships", []):
            try:
                rel_type = r.get("relation_type", "chưa_rõ")
                relationships.append(Relationship(
                    character_a=r["character_a"],
                    character_b=r["character_b"],
                    relation_type=RelationType(rel_type),
                    intensity=r.get("intensity", 0.5),
                    description=r.get("description", ""),
                    tension=r.get("tension", 0.0),
                ))
            except (ValueError, KeyError):
                continue

        return {
            "relationships": relationships,
            "conflict_points": result.get("conflict_points", []),
            "untapped_drama": result.get("untapped_drama", []),
            "character_weaknesses": result.get("character_weaknesses", {}),
        }

    def extract_conflict_graph(self, draft: StoryDraft) -> list[dict]:
        """Extract per-chapter narrative structure: goal, obstacle, conflict."""
        results = []
        for chapter in draft.chapters:
            try:
                graph = self.llm.generate_json(
                    system_prompt="Phân tích cấu trúc tường thuật. Trả về JSON.",
                    user_prompt=(
                        f"Chương {chapter.chapter_number}: {chapter.content[:1500]}\n\n"
                        "Trích xuất cấu trúc kịch tính:\n"
                        "- goal: nhân vật chính muốn gì\n"
                        "- obstacle: điều gì cản trở\n"
                        "- conflict: mâu thuẫn phát sinh\n"
                        "Trả về JSON: {\"goal\": \"...\", \"obstacle\": \"...\", \"conflict\": \"...\"}"
                    ),
                    temperature=0.2,
                    max_tokens=300,
                    model_tier="cheap",
                )
                graph["chapter"] = chapter.chapter_number
                graph["tension_score"] = self._calc_tension(graph, results)
                results.append(graph)
            except Exception as e:
                logger.debug(f"Conflict graph ch {chapter.chapter_number}: {e}")
                results.append({"chapter": chapter.chapter_number, "goal": "", "obstacle": "", "conflict": "", "tension_score": 0.0})
        return results

    @staticmethod
    def _calc_tension(current: dict, prior: list) -> float:
        """Calculate cumulative tension with exponential escalation for climax chapters."""
        base = 0.3 if current.get("conflict") else 0.0
        # Count unresolved conflicts in recent chapters
        unresolved = sum(1 for p in prior[-5:] if p.get("conflict") and p.get("tension_score", 0) > 0.3)
        # Exponential curve: tension builds faster as conflicts accumulate
        escalation = (1.0 - 0.7 ** unresolved) if unresolved > 0 else 0.0
        return min(1.0, base + escalation * 0.7)
