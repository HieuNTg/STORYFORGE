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

    def analyze(self, draft: StoryDraft, conflict_web: list | None = None) -> dict:
        """Phân tích truyện, trả về relationships, conflicts, untapped drama.

        conflict_web: optional L1 ConflictEntry list; merged with LLM relationships
        (higher tension wins on duplicate pairs).
        """
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

        # Parse relationships from LLM
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

        # Merge L1 conflict_web into relationships (prefer higher tension on duplicates)
        if conflict_web:
            relationships = self._merge_conflict_web(relationships, conflict_web)

        return {
            "relationships": relationships,
            "conflict_points": result.get("conflict_points", []),
            "untapped_drama": result.get("untapped_drama", []),
            "character_weaknesses": result.get("character_weaknesses", {}),
        }

    @staticmethod
    def _merge_conflict_web(
        llm_rels: list[Relationship],
        conflict_web: list,
    ) -> list[Relationship]:
        """Merge L1 conflict_web entries into LLM relationships.

        Deduplicates by (character_a, character_b) pair (order-independent).
        On duplicates, the entry with the higher tension value wins.
        L1 entries without a matching pair in llm_rels are appended.
        """
        # Build lookup: frozenset pair → index in list
        merged: list[Relationship] = list(llm_rels)
        pair_index: dict[frozenset, int] = {
            frozenset([r.character_a, r.character_b]): i
            for i, r in enumerate(merged)
        }

        for entry in conflict_web:
            try:
                if hasattr(entry, "model_dump"):
                    entry = entry.model_dump()
                if not isinstance(entry, dict):
                    chars = list(getattr(entry, "characters", []) or [])
                    intensity_raw = int(getattr(entry, "intensity", 1))
                    description = str(getattr(entry, "description", ""))
                else:
                    chars = list(entry.get("characters") or [])
                    intensity_raw = int(entry.get("intensity", 1))
                    description = str(entry.get("description", ""))
                if len(chars) < 2:
                    continue
                # Map intensity 1-5 → tension 0.0-1.0
                l1_tension = min(1.0, intensity_raw / 5.0)
                pair_key = frozenset([chars[0], chars[1]])
                if pair_key in pair_index:
                    idx = pair_index[pair_key]
                    if l1_tension > merged[idx].tension:
                        merged[idx] = merged[idx].model_copy(update={"tension": l1_tension})
                else:
                    new_rel = Relationship(
                        character_a=chars[0],
                        character_b=chars[1],
                        relation_type=RelationType.RIVAL,
                        intensity=l1_tension,
                        description=description,
                        tension=l1_tension,
                    )
                    pair_index[pair_key] = len(merged)
                    merged.append(new_rel)
            except Exception as e:
                logger.debug(f"conflict_web merge skipped: {e}")
        return merged

