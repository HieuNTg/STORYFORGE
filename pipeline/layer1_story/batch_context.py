"""Context snapshot + causal accumulator primitives for batch generation.

Extracted verbatim from ``batch_generator`` (structural split, no behavior
change). Re-exported by ``pipeline.layer1_story.batch_generator`` so existing
``from pipeline.layer1_story.batch_generator import FrozenContext`` /
``CausalAccumulator`` imports keep working unchanged.
"""

import threading
from dataclasses import dataclass, field

from models.schemas import StoryContext


@dataclass
class CausalAccumulator:
    """Thread-safe accumulator for causal events across parallel chapters.

    Used to sync causal graph updates after parallel batch completes.
    """

    events: list[dict] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def add_event(
        self,
        chapter_num: int,
        event_type: str,
        description: str,
        causes: list[int] = None,
        effects: list[int] = None,
    ):
        with self._lock:
            self.events.append(
                {
                    "chapter": chapter_num,
                    "type": event_type,
                    "description": description,
                    "causes": causes or [],
                    "effects": effects or [],
                }
            )

    def get_events_sorted(self) -> list[dict]:
        with self._lock:
            return sorted(self.events, key=lambda e: e["chapter"])

    def clear(self):
        with self._lock:
            self.events.clear()


class FrozenContext:
    """Immutable context snapshot taken at batch boundary."""

    __slots__ = ("recent_summaries", "character_states", "plot_events", "chapter_texts")

    def __init__(self, story_context: StoryContext, all_chapter_texts: list[str]):
        self.recent_summaries = list(story_context.recent_summaries)
        self.character_states = list(story_context.character_states)
        self.plot_events = list(story_context.plot_events)
        self.chapter_texts = list(all_chapter_texts)
