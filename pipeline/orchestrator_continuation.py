"""Story continuation: load checkpoint, continue, edit characters, enhance chapters."""

import json
import logging
from typing import Optional

from models.schemas import EnhancedStory, PipelineOutput, StoryDraft
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
    ) -> StoryDraft:
        """Continue writing from current StoryDraft."""
        if not self.output.story_draft:
            raise ValueError("No story draft loaded. Load checkpoint first.")
        draft = self.story_gen.continue_story(
            draft=self.output.story_draft,
            additional_chapters=additional_chapters,
            word_count=word_count,
            style=style,
            progress_callback=progress_callback,
            stream_callback=stream_callback,
        )
        self.output.story_draft = draft
        self.checkpoint_manager.output = self.output
        self.checkpoint_manager.save(1)
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

            _log("Enhancing story with dramatic elements...")
            enhanced = self.enhancer.enhance_with_feedback(
                draft=draft, sim_result=sim_result,
                word_count=word_count,
                progress_callback=lambda m: _log(f"[L2] {m}"),
            )

            self.output.enhanced_story = enhanced
            self.checkpoint_manager.output = self.output
            self.checkpoint_manager.save(2)
            _log("Enhancement complete!")
            return enhanced

        except Exception as e:
            _log(f"Enhancement error: {e}")
            return None
