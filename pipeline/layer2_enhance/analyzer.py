"""Phân tích truyện - trích xuất mối quan hệ và xung đột."""

import logging
from models.schemas import StoryDraft, Relationship, RelationType
from services.llm_client import LLMClient
from services import prompts

logger = logging.getLogger(__name__)


class StoryAnalyzer:
    """Phân tích truyện để xây dựng đồ thị quan hệ nhân vật."""

    def __init__(self):
        self.llm = LLMClient()

    def analyze(self, draft: StoryDraft) -> dict:
        """Phân tích truyện, trả về relationships, conflicts, untapped drama."""
        chars_text = "\n".join(
            f"- {c.name} ({c.role}): {c.personality}, Động lực: {c.motivation}"
            for c in draft.characters
        )
        synopsis = draft.synopsis
        if not synopsis and draft.chapters:
            synopsis = "\n".join(
                f"Chương {ch.chapter_number}: {ch.content[:200]}..."
                for ch in draft.chapters[:5]
            )

        result = self.llm.generate_json(
            system_prompt="Bạn là nhà phân tích truyện chuyên sâu. Trả về JSON.",
            user_prompt=prompts.ANALYZE_STORY.format(
                title=draft.title,
                genre=draft.genre,
                characters=chars_text,
                synopsis=synopsis,
            ),
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
