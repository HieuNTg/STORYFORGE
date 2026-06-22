"""Per-chapter parallel-write helpers for BatchChapterGenerator.

Extracted verbatim from ``batch_generator`` (structural split, no behavior
change). Provides ``ParallelWriteMixin``, mixed into ``BatchChapterGenerator``
so all ``self._write_chapter_parallel`` / ``self._extract_causal_events`` /
``self._sync_causal_events`` / ``self._build_sibling_context`` calls resolve
exactly as before.
"""

import logging

from models.schemas import StoryContext, ChapterOutline, Chapter
from pipeline.layer1_story.chapter_contract_setup import build_contract_for_chapter
from pipeline.layer1_story.parallel_write_context import (
    assemble_parallel_write_inputs,
)

from pipeline.layer1_story.batch_context import CausalAccumulator, FrozenContext

logger = logging.getLogger(__name__)


class ParallelWriteMixin:
    """Single-chapter parallel write + causal-event helpers."""

    def _write_chapter_parallel(
        self,
        outline: ChapterOutline,
        frozen: FrozenContext,
        draft,
        story_context: StoryContext,
        frozen_threads: list,
        sibling_summaries: str,
        shared_enhancement: str,
        title: str,
        genre: str,
        style: str,
        characters: list,
        world,
        word_count: int,
        macro_arcs,
        conflict_web,
        foreshadowing_plan,
        progress_callback,
        causal_acc: CausalAccumulator | None,
        idea: str = "",
        idea_summary: str = "",
        override_contract=None,
    ) -> tuple[Chapter, dict | None]:
        """Write a single chapter for parallel execution. Returns (chapter, contract)."""
        try:
            from services.trace_context import set_chapter, set_module

            set_chapter(outline.chapter_number)
            set_module("chapter_writer")
        except Exception:
            pass
        (
            bible_ctx,
            frozen_ctx,
            active_conflicts,
            seeds,
            payoffs,
            pacing,
            arc_context,
            per_chapter_enhancement,
        ) = assemble_parallel_write_inputs(
            self.gen,
            self.config,
            self.llm,
            outline=outline,
            frozen=frozen,
            draft=draft,
            story_context=story_context,
            frozen_threads=frozen_threads,
            sibling_summaries=sibling_summaries,
            shared_enhancement=shared_enhancement,
            characters=characters,
            world=world,
            genre=genre,
            macro_arcs=macro_arcs,
            conflict_web=conflict_web,
            foreshadowing_plan=foreshadowing_plan,
        )

        # Contract
        p_contract, p_contract_text = build_contract_for_chapter(
            self.config,
            outline,
            threads=frozen_threads,
            macro_arcs=macro_arcs,
            conflicts=conflict_web,
            foreshadowing_plan=foreshadowing_plan,
            characters=characters,
            override_contract=override_contract,
        )

        if progress_callback:
            progress_callback(
                f"Đang viết chương {outline.chapter_number}: {outline.title}..."
            )

        _p_negotiated = p_contract.to_negotiated() if p_contract is not None else None
        ch_result = self.gen._write_chapter_with_long_context(
            title,
            genre,
            style,
            characters,
            world,
            outline,
            word_count,
            frozen_ctx,
            list(frozen.chapter_texts),
            bible_ctx,
            open_threads=frozen_threads,
            active_conflicts=active_conflicts,
            foreshadowing_to_plant=seeds,
            foreshadowing_to_payoff=payoffs,
            pacing_type=pacing,
            enhancement_context=per_chapter_enhancement,
            current_arc_context=arc_context,
            chapter_contract=p_contract_text,
            negotiated_contract=_p_negotiated,
            idea=idea,
            idea_summary=idea_summary,
        )

        if p_contract is not None:
            try:
                ch_result.contract = p_contract
                object.__setattr__(
                    ch_result, "negotiated_contract", p_contract.to_negotiated()
                )
            except Exception:
                pass

        # Causal event extraction (#3 improvement)
        if causal_acc:
            self._extract_causal_events(ch_result, outline, causal_acc)

        return ch_result, p_contract

    def _extract_causal_events(
        self,
        chapter: Chapter,
        outline: ChapterOutline,
        causal_acc: CausalAccumulator,
    ):
        """Extract causal events from chapter for cross-batch sync."""
        try:
            # Simple heuristic: extract key plot points from content
            # More sophisticated: use LLM to identify cause-effect chains
            keywords = ["vì thế", "do đó", "kết quả", "dẫn đến", "bởi vì", "nên"]
            content_lower = chapter.content.lower()
            for kw in keywords:
                if kw in content_lower:
                    causal_acc.add_event(
                        chapter_num=outline.chapter_number,
                        event_type="causal_marker",
                        description=f"Chapter {outline.chapter_number} contains causal keyword: {kw}",
                    )
                    break
        except Exception as e:
            logger.debug(
                "Causal extraction failed for ch%d: %s", outline.chapter_number, e
            )

    def _sync_causal_events(
        self,
        causal_acc: CausalAccumulator,
        story_context: StoryContext,
        progress_callback,
    ):
        """Sync accumulated causal events back to story_context."""
        events = causal_acc.get_events_sorted()
        if not events:
            return

        # Merge into story_context.plot_events or a dedicated causal_graph
        causal_graph = getattr(story_context, "causal_graph", None)
        if causal_graph and hasattr(causal_graph, "add_event"):
            for ev in events:
                try:
                    causal_graph.add_event(
                        chapter=ev["chapter"],
                        event_type=ev["type"],
                        description=ev["description"],
                    )
                except Exception:
                    pass

        if progress_callback and events:
            progress_callback(
                f"[CAUSAL] Synced {len(events)} causal events from parallel batch"
            )

    @staticmethod
    def _build_sibling_context(batch: list[ChapterOutline]) -> str:
        """Build sibling outline context for parallel chapters to avoid duplication."""
        if len(batch) <= 1:
            return ""
        lines = []
        for o in batch:
            lines.append(f"- Ch{o.chapter_number}: {o.title} — {o.summary}")
        return "\n".join(lines)
