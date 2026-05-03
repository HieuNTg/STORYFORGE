"""Story continuation: load checkpoint, continue, edit characters, enhance chapters."""

import json
import logging
from typing import Optional

from models.schemas import EnhancedStory, PipelineOutput, StoryDraft
from models.schemas import ChapterOutline
from pipeline.layer1_story.generator import StoryGenerator

logger = logging.getLogger(__name__)


class StoryContinuation:
    """Handles loading checkpoints and continuing/editing existing stories."""

    def __init__(self, output: PipelineOutput, story_gen, analyzer, simulator, enhancer, checkpoint_manager):
        self.output = output
        self.story_gen = story_gen
        self.analyzer = analyzer
        self.simulator = simulator
        self.enhancer = enhancer
        self.checkpoint_manager = checkpoint_manager

    def load_from_checkpoint(self, checkpoint_path: str) -> Optional[StoryDraft]:
        """Load StoryDraft from checkpoint for continuation/editing."""
        try:
            with open(checkpoint_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.output = PipelineOutput(**data)
            self.checkpoint_manager.output = self.output
            return self.output.story_draft
        except Exception as e:
            logger.error(f"Failed to load checkpoint {checkpoint_path}: {e}")
            return None

    def continue_story(
        self,
        additional_chapters: int = 5,
        word_count: int = 2000,
        style: str = "",
        progress_callback=None,
        stream_callback=None,
        arc_directives: list = None,
    ) -> StoryDraft:
        """Continue writing from current StoryDraft."""
        if not self.output.story_draft:
            raise ValueError("No story draft loaded. Load checkpoint first.")
        previous_count = len(self.output.story_draft.chapters)
        # Trace so usage_history can attribute the new chapters' LLM cost
        # back to the same checkpoint sidecar. No-op if a trace is already set.
        from services.trace_context import PipelineTrace, get_trace, set_trace
        if get_trace() is None:
            set_trace(PipelineTrace(title=self.output.story_draft.title or "", layer=1))
        draft = self.story_gen.continue_story(
            draft=self.output.story_draft,
            additional_chapters=additional_chapters,
            word_count=word_count,
            style=style,
            progress_callback=progress_callback,
            stream_callback=stream_callback,
            arc_directives=arc_directives or [],
        )
        self.output.story_draft = draft
        self.checkpoint_manager.output = self.output
        self.checkpoint_manager.save(1)
        # Advisory sidecar — never fail the continuation if this breaks.
        try:
            from services.continuation_history import record_continuation
            record_continuation(
                title=draft.title,
                previous_chapter_count=previous_count,
                new_chapter_count=len(draft.chapters),
                layer=1,
            )
        except Exception as e:
            logger.warning("Continuation history sidecar skipped: %s", e)
        return draft

    def remove_chapters(self, from_chapter: int, progress_callback=None) -> StoryDraft:
        """Remove chapters from a given position onward."""
        if not self.output.story_draft:
            raise ValueError("No story draft loaded.")
        draft = StoryGenerator.remove_chapters(self.output.story_draft, from_chapter)
        self.output.story_draft = draft
        self.output.enhanced_story = None
        self.checkpoint_manager.output = self.output
        self.checkpoint_manager.save(1)
        if progress_callback:
            progress_callback(
                f"Removed chapters from {from_chapter} onward. {len(draft.chapters)} chapters remain."
            )
        return draft

    def regenerate_chapter(
        self,
        chapter_number: int,
        word_count: int = 2000,
        style: str = "",
        preserve_outline: bool = True,
        progress_callback=None,
        stream_callback=None,
    ) -> StoryDraft:
        """Regenerate a specific chapter without affecting subsequent chapters."""
        if not self.output.story_draft:
            raise ValueError("No story draft loaded.")
        draft = self.output.story_draft
        if chapter_number < 1 or chapter_number > len(draft.chapters):
            raise ValueError(f"Invalid chapter_number {chapter_number}. Story has {len(draft.chapters)} chapters.")

        from pipeline.layer1_story.story_continuation import regenerate_chapter_impl
        draft = regenerate_chapter_impl(
            generator=self.story_gen,
            draft=draft,
            chapter_number=chapter_number,
            word_count=word_count,
            style=style,
            preserve_outline=preserve_outline,
            progress_callback=progress_callback,
            stream_callback=stream_callback,
        )
        self.output.story_draft = draft
        self.output.enhanced_story = None  # Invalidate L2 since chapter changed
        self.checkpoint_manager.output = self.output
        self.checkpoint_manager.save(1)
        return draft

    def generate_continuation_outlines(
        self,
        additional_chapters: int = 5,
        progress_callback=None,
        arc_directives: list = None,
    ) -> list[ChapterOutline]:
        """Generate outlines for continuation without writing chapters.

        Returns list of ChapterOutline objects for user review/editing.
        Use write_from_outlines() to write chapters from the (possibly edited) outlines.
        """
        if not self.output.story_draft:
            raise ValueError("No story draft loaded.")

        from pipeline.layer1_story.story_continuation import generate_continuation_outlines
        outlines = generate_continuation_outlines(
            generator=self.story_gen,
            draft=self.output.story_draft,
            additional_chapters=additional_chapters,
            progress_callback=progress_callback,
            arc_directives=arc_directives or [],
        )
        return outlines

    def write_from_outlines(
        self,
        outlines: list[ChapterOutline],
        word_count: int = 2000,
        style: str = "",
        progress_callback=None,
        stream_callback=None,
        arc_directives: list = None,
    ) -> StoryDraft:
        """Write chapters from pre-generated (possibly user-edited) outlines.

        This is the second step of the two-step continuation flow:
        1. generate_continuation_outlines() -> user edits -> 2. write_from_outlines()
        """
        if not self.output.story_draft:
            raise ValueError("No story draft loaded.")
        if not outlines:
            raise ValueError("No outlines provided.")

        previous_count = len(self.output.story_draft.chapters)
        from pipeline.layer1_story.story_continuation import write_from_outlines
        draft = write_from_outlines(
            generator=self.story_gen,
            draft=self.output.story_draft,
            outlines=outlines,
            word_count=word_count,
            style=style,
            progress_callback=progress_callback,
            stream_callback=stream_callback,
            arc_directives=arc_directives or [],
        )
        self.output.story_draft = draft
        self.checkpoint_manager.output = self.output
        self.checkpoint_manager.save(1)
        try:
            from services.continuation_history import record_continuation
            record_continuation(
                title=draft.title,
                previous_chapter_count=previous_count,
                new_chapter_count=len(draft.chapters),
                layer=1,
            )
        except Exception as e:
            logger.warning("Continuation history sidecar skipped: %s", e)
        return draft

    def generate_continuation_paths(
        self,
        additional_chapters: int = 5,
        num_paths: int = 3,
        progress_callback=None,
        arc_directives: list = None,
    ) -> list[dict]:
        """Generate multiple alternative continuation paths (outlines only).

        Each path represents a different narrative direction.
        Use write_from_outlines() with selected path's outlines to write chapters.
        """
        if not self.output.story_draft:
            raise ValueError("No story draft loaded.")

        from pipeline.layer1_story.story_continuation import generate_continuation_paths
        paths = generate_continuation_paths(
            generator=self.story_gen,
            draft=self.output.story_draft,
            additional_chapters=additional_chapters,
            num_paths=num_paths,
            progress_callback=progress_callback,
            arc_directives=arc_directives or [],
        )
        return paths

    def insert_chapter(
        self,
        insert_after: int,
        title: str = "",
        summary: str = "",
        word_count: int = 2000,
        style: str = "",
        progress_callback=None,
        stream_callback=None,
    ) -> StoryDraft:
        """Insert a new chapter after the specified position.

        Args:
            insert_after: Insert after this chapter number (0 = insert at beginning)
            title: Optional title for the new chapter
            summary: Optional summary/direction for the new chapter
            word_count: Target word count
            style: Writing style override
            progress_callback: Progress reporting function
            stream_callback: Streaming content callback
        """
        if not self.output.story_draft:
            raise ValueError("No story draft loaded.")

        from pipeline.layer1_story.story_continuation import insert_chapter_impl
        draft = insert_chapter_impl(
            generator=self.story_gen,
            draft=self.output.story_draft,
            insert_after=insert_after,
            title=title,
            summary=summary,
            word_count=word_count,
            style=style,
            progress_callback=progress_callback,
            stream_callback=stream_callback,
        )
        self.output.story_draft = draft
        self.output.enhanced_story = None  # Invalidate L2
        self.checkpoint_manager.output = self.output
        self.checkpoint_manager.save(1)
        return draft

    def update_character(
        self, char_name: str, updates: dict, progress_callback=None
    ) -> StoryDraft:
        """Update a character's attributes in the current draft."""
        if not self.output.story_draft:
            raise ValueError("No story draft loaded.")
        draft = self.output.story_draft
        for c in draft.characters:
            if c.name == char_name:
                for key, value in updates.items():
                    if hasattr(c, key) and value:
                        setattr(c, key, value)
                if progress_callback:
                    progress_callback(f"Updated character: {char_name}")
                self.checkpoint_manager.output = self.output
                self.checkpoint_manager.save(1)
                return draft
        if progress_callback:
            progress_callback(f"Character not found: {char_name}")
        return draft

    def enhance_chapters(
        self,
        num_sim_rounds: int = 3,
        word_count: int = 2000,
        progress_callback=None,
    ) -> Optional[EnhancedStory]:
        """Run Layer 2 enhancement on all chapters."""
        if not self.output.story_draft:
            raise ValueError("No story draft loaded.")

        draft = self.output.story_draft

        def _log(msg):
            logger.info(msg)
            if progress_callback:
                progress_callback(msg)

        try:
            _log("Analyzing story for enhancement...")
            analysis = self.analyzer.analyze(draft)

            _log("Running drama simulation...")
            sim_result = self.simulator.run_simulation(
                characters=draft.characters,
                relationships=analysis["relationships"],
                genre=draft.genre,
                num_rounds=num_sim_rounds,
                progress_callback=lambda m: _log(f"[L2] {m}"),
            )
            self.output.simulation_result = sim_result

            # P-C: Incremental publish — save checkpoint per chapter as L2
            # finishes each one, so clients can poll partial state instead of
            # waiting for the full enhancement pass. Mirrors L1 per-chapter
            # checkpoint flow gated by enable_chapter_checkpoint.
            from config import ConfigManager
            _incremental_publish = False
            try:
                _incremental_publish = bool(
                    getattr(ConfigManager().load().pipeline, "enable_incremental_publish", False)
                )
            except Exception:
                pass

            def _on_chapter_done(ch):
                if not _incremental_publish:
                    return
                try:
                    if self.output.enhanced_story is None:
                        self.output.enhanced_story = EnhancedStory(
                            title=draft.title, genre=draft.genre, chapters=[],
                        )
                    self.output.enhanced_story.chapters = [
                        c for c in self.output.enhanced_story.chapters
                        if c.chapter_number != ch.chapter_number
                    ] + [ch]
                    self.output.enhanced_story.chapters.sort(key=lambda c: c.chapter_number)
                    self.checkpoint_manager.output = self.output
                    self.checkpoint_manager.save_chapter(ch.chapter_number, layer=2)
                except Exception as _pub_e:
                    logger.debug(f"Incremental publish (ch {ch.chapter_number}) skipped: {_pub_e}")

            _log("Enhancing story with dramatic elements...")
            enhanced = self.enhancer.enhance_with_feedback(
                draft=draft, sim_result=sim_result,
                word_count=word_count,
                progress_callback=lambda m: _log(f"[L2] {m}"),
                chapter_done_callback=_on_chapter_done,
            )

            # P-A: L3 Sensory Polish (optional post-L2 enhancement)
            try:
                from config import ConfigManager
                cfg = ConfigManager().load().pipeline
                if getattr(cfg, "enable_sensory_polish", False):
                    from pipeline.layer2_enhance.sensory_polish import apply_sensory_polish
                    _log("Applying sensory polish (L3)...")
                    enhanced = apply_sensory_polish(
                        enhanced, enabled=True,
                        progress_callback=lambda m: _log(m),
                    )
            except Exception as _sp_e:
                logger.debug(f"Sensory polish skipped: {_sp_e}")

            # P-B: Reader Simulation (optional quality feedback)
            try:
                from config import ConfigManager
                cfg = ConfigManager().load().pipeline
                if getattr(cfg, "enable_reader_simulation", False):
                    from pipeline.agents.reader_simulator import run_reader_simulation
                    _log("Running reader simulation...")
                    feedbacks = run_reader_simulation(
                        enhanced, enabled=True,
                        progress_callback=lambda m: _log(m),
                    )
                    if feedbacks:
                        weak = [f.chapter_number for f in feedbacks if f.engagement_score < 0.5]
                        if weak:
                            _log(f"Reader flagged weak chapters: {weak}")
                        enhanced._reader_feedbacks = feedbacks
            except Exception as _rs_e:
                logger.debug(f"Reader simulation skipped: {_rs_e}")

            self.output.enhanced_story = enhanced
            self.checkpoint_manager.output = self.output
            self.checkpoint_manager.save(2)
            _log("Enhancement complete!")
            return enhanced

        except Exception as e:
            _log(f"Enhancement error: {e}")
            return None

    def polish_chapter(
        self,
        chapter_number: int,
        user_text: str,
        title: str = "",
        polish_level: str = "light",
        progress_callback=None,
    ) -> StoryDraft:
        """Polish user-written chapter while preserving their voice.

        Args:
            chapter_number: Which chapter this is (1-indexed)
            user_text: User's raw chapter text
            title: Optional chapter title
            polish_level: 'light', 'medium', or 'heavy'
        """
        if not self.output.story_draft:
            raise ValueError("No story draft loaded.")

        from pipeline.layer1_story.story_continuation import polish_chapter_impl
        draft = polish_chapter_impl(
            generator=self.story_gen,
            draft=self.output.story_draft,
            chapter_number=chapter_number,
            user_text=user_text,
            title=title,
            polish_level=polish_level,
            progress_callback=progress_callback,
        )
        self.output.story_draft = draft
        self.output.enhanced_story = None  # Invalidate L2
        self.checkpoint_manager.output = self.output
        self.checkpoint_manager.save(1)
        return draft

    def check_consistency(
        self,
        chapter_numbers: list[int] = None,
        progress_callback=None,
    ):
        """Check story for consistency issues.

        Args:
            chapter_numbers: Specific chapters to check against previous content.
                           If None, checks entire story.
            progress_callback: Progress reporting function

        Returns:
            ConsistencyReport with detected issues
        """
        if not self.output.story_draft:
            raise ValueError("No story draft loaded.")

        from pipeline.layer1_story.consistency_checker import ConsistencyChecker

        checker = ConsistencyChecker(self.story_gen.llm if self.story_gen else None)

        if chapter_numbers:
            return checker.check_chapters(
                self.output.story_draft,
                chapter_numbers,
                progress_callback,
            )
        else:
            return checker.check_full_story(
                self.output.story_draft,
                progress_callback,
            )
