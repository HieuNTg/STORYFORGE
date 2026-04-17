"""L1-A: Unified NarrativeContextBlock — consolidates scattered chapter-prompt injections.

Before: chapter_writer appended 6+ separate blocks in ad-hoc order (contract, scenes,
enhancement, dialogue, arc stages, arc progression). This module orders them into a
single coherent "DIRECTIVE TỔNG HỢP" section with deterministic priority so the LLM
sees stable structure and dedup happens in one place.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class NarrativeContextBlock:
    """Ordered container for non-core prompt context. Higher priority = rendered first."""
    chapter_contract: str = ""
    scenes_text: str = ""
    enhancement_context: str = ""
    dialogue_context: str = ""
    arc_stage_text: str = ""
    arc_progression_text: str = ""
    extra_sections: list[str] = field(default_factory=list)

    def render(self) -> str:
        """Render all non-empty sections separated by blank lines, in priority order.

        Priority: contract → scenes → enhancement → dialogue (if not in enhancement)
        → arc target stage → arc progression history → extras.
        Dedup: if dialogue_context marker 'PHONG CÁCH NÓI CHUYỆN' already appears in
        enhancement_context, skip dialogue_context to avoid repetition.
        """
        parts: list[str] = []
        if self.chapter_contract:
            parts.append(self.chapter_contract.strip())
        if self.scenes_text:
            parts.append(self.scenes_text.strip())
        if self.enhancement_context:
            parts.append(self.enhancement_context.strip())
        if self.dialogue_context and "PHONG CÁCH NÓI CHUYỆN" not in (self.enhancement_context or ""):
            parts.append(self.dialogue_context.strip())
        if self.arc_stage_text:
            parts.append(self.arc_stage_text.strip())
        if self.arc_progression_text:
            parts.append(self.arc_progression_text.strip())
        for extra in self.extra_sections:
            if extra:
                parts.append(extra.strip())
        return "\n\n".join(p for p in parts if p)


def build_narrative_block(
    *,
    characters: list,
    outline,
    context=None,
    chapter_contract: str = "",
    scenes: list[dict] | None = None,
    enhancement_context: str = "",
    dialogue_context: str = "",
) -> NarrativeContextBlock:
    """Assemble NarrativeContextBlock from chapter-writer inputs. Silent fallback on errors."""
    block = NarrativeContextBlock(
        chapter_contract=chapter_contract or "",
        enhancement_context=enhancement_context or "",
        dialogue_context=dialogue_context or "",
    )
    if scenes:
        try:
            from pipeline.layer1_story.scene_decomposer import format_scenes_for_prompt
            block.scenes_text = format_scenes_for_prompt(scenes) or ""
        except Exception as e:
            logger.debug("scene format failed: %s", e)
    try:
        from pipeline.layer1_story.arc_waypoint_generator import (
            format_arc_stages_for_prompt, format_arc_progression_for_prompt,
        )
        block.arc_stage_text = format_arc_stages_for_prompt(
            characters, outline.chapter_number,
        ) or ""
        if context is not None and getattr(context, "arc_progression_cache", None):
            block.arc_progression_text = format_arc_progression_for_prompt(
                context.arc_progression_cache, characters, outline.chapter_number,
            ) or ""
    except Exception as e:
        logger.debug("arc format failed: %s", e)
    return block
