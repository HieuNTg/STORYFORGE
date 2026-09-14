"""Everything one chapter's repair loop needs, in one object.

`finalize_chapter` builds this once and hands it to the collector, planner,
executor and verifier so none of them has to re-derive state from the pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class RepairContext:
    """Immutable-ish handle on the chapter under repair.

    `chapter` and `story_context` are live pipeline objects and ARE mutated —
    but only by the coordinator, and only after a candidate has passed verify.
    Collector and verifier must treat both as read-only.
    """

    pipeline_config: Any
    llm: Any
    chapter: Any
    outline: Any
    story_context: Any
    characters: list = field(default_factory=list)
    draft: Any = None
    foreshadowing_plan: list | None = None
    word_count: int = 0
    layer_model: str | None = None
    progress_callback: Callable | None = None

    # Location maps captured by `process_chapter_post_write`, needed to re-run
    # `validate_location_transitions` against a candidate rewrite.
    prev_locations: dict | None = None
    new_locations: dict | None = None

    @property
    def chapter_number(self) -> int:
        try:
            return int(getattr(self.outline, "chapter_number", 0) or 0)
        except (TypeError, ValueError):
            return 0

    @property
    def idea(self) -> str:
        if self.draft is None:
            return ""
        return getattr(self.draft, "original_idea", "") or ""

    @property
    def idea_summary(self) -> str:
        if self.draft is None:
            return ""
        return getattr(self.draft, "idea_summary_for_chapters", "") or ""

    def log(self, message: str) -> None:
        if self.progress_callback:
            try:
                self.progress_callback(message)
            except Exception:  # a progress callback must never break repair
                pass
