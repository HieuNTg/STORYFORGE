"""Điều phối pipeline 2 lớp: Tạo truyện -> Mô phỏng kịch tính.

This module exposes PipelineOrchestrator — the single public entry point
for all pipeline operations.  Heavy layer-execution logic lives in:

  - orchestrator_layers.py       — run_full_pipeline / run_layer1_only / run_layer2_only
  - orchestrator_checkpoint.py   — CheckpointManager (save / list / resume)
  - orchestrator_continuation.py — StoryContinuation (continue / edit story)
  - orchestrator_export.py       — PipelineExporter (markdown / HTML / zip)
  - orchestrator_media.py        — MediaProducer (images)
"""

import logging
import threading
from typing import Optional

from models.schemas import EnhancedStory, PipelineOutput, StoryDraft
from pipeline.layer1_story.generator import StoryGenerator
from pipeline.layer2_enhance.analyzer import StoryAnalyzer
from pipeline.layer2_enhance.simulator import DramaSimulator
from pipeline.layer2_enhance.enhancer import StoryEnhancer
from config import ConfigManager
from pipeline.orchestrator_media import MediaProducer
from pipeline.orchestrator_export import PipelineExporter
from pipeline.orchestrator_checkpoint import CheckpointManager, CHECKPOINT_DIR
from pipeline.orchestrator_continuation import StoryContinuation

# Import layer-execution functions (bound as methods below)
from pipeline.orchestrator_layers import (
    run_full_pipeline as _run_full_pipeline,
    run_layer1_only as _run_layer1_only,
    run_layer2_only as _run_layer2_only,
)

logger = logging.getLogger(__name__)


class PipelineOrchestrator:
    """Điều phối toàn bộ pipeline từ input đến output.

    Responsibilities:
    - Instantiate and wire sub-components on construction.
    - Keep sub-components pointing at the current self.output via _sync_output.
    - Delegate all heavy work to orchestrator_layers / sub-component modules.
    - Expose a stable public API so callers never need to import sub-modules.
    """

    CHECKPOINT_DIR = CHECKPOINT_DIR

    def __init__(self):
        self.config = ConfigManager()
        self.story_gen = StoryGenerator()
        self.analyzer = StoryAnalyzer()
        self.simulator = DramaSimulator()
        self.enhancer = StoryEnhancer()
        self._lock = threading.RLock()
        self.output = PipelineOutput()

        self.media_producer = MediaProducer(self.config)
        self.exporter = PipelineExporter(self.output)
        self.checkpoint = CheckpointManager(
            self.output, self.analyzer, self.simulator,
            self.enhancer,
        )
        self.continuation = StoryContinuation(
            self.output, self.story_gen, self.analyzer,
            self.simulator, self.enhancer, self.checkpoint,
        )

    def snapshot(self) -> "PipelineOutput":
        """Thread-safe deep copy of current output."""
        with self._lock:
            return self.output.model_copy(deep=True)

    def _sync_output(self):
        """Propagate the current self.output reference to all sub-components.

        Called after any operation that replaces self.output so that
        exporter, checkpoint, and continuation stay consistent.
        """
        self.exporter.output = self.output
        self.checkpoint.output = self.output
        self.continuation.output = self.output
        self.continuation.checkpoint_manager.output = self.output

    # ── Layer execution (implemented in orchestrator_layers.py) ─────────────

    def run_full_pipeline(
        self,
        title: str,
        genre: str,
        idea: str,
        style: str = "Miêu tả chi tiết",
        num_chapters: int = 10,
        num_characters: int = 5,
        word_count: int = 2000,
        num_sim_rounds: int = 5,
        progress_callback=None,
        stream_callback=None,
        enable_agents: bool = True,
        enable_scoring: bool = True,
        enable_media: bool = False,
    ) -> PipelineOutput:
        """Chạy toàn bộ pipeline 2 lớp."""
        return _run_full_pipeline(
            self, title=title, genre=genre, idea=idea, style=style,
            num_chapters=num_chapters, num_characters=num_characters,
            word_count=word_count, num_sim_rounds=num_sim_rounds,
            progress_callback=progress_callback, stream_callback=stream_callback,
            enable_agents=enable_agents, enable_scoring=enable_scoring,
            enable_media=enable_media,
        )

    def run_layer1_only(
        self,
        title: str,
        genre: str,
        idea: str,
        style: str,
        num_chapters: int,
        num_characters: int,
        word_count: int,
        progress_callback=None,
    ) -> StoryDraft:
        """Chỉ chạy Layer 1."""
        return _run_layer1_only(
            self, title=title, genre=genre, idea=idea, style=style,
            num_chapters=num_chapters, num_characters=num_characters,
            word_count=word_count, progress_callback=progress_callback,
        )

    def run_layer2_only(
        self,
        draft: StoryDraft,
        num_sim_rounds: int = 5,
        word_count: int = 2000,
        progress_callback=None,
    ) -> EnhancedStory:
        """Chỉ chạy Layer 2 trên bản thảo có sẵn."""
        return _run_layer2_only(
            self, draft=draft, num_sim_rounds=num_sim_rounds,
            word_count=word_count, progress_callback=progress_callback,
        )

    # ── Export wrappers (delegate to PipelineExporter) ───────────────────────

    def export_output(self, output_dir: str = "output", formats: list[str] | None = None) -> list[str]:
        self._sync_output()
        return self.exporter.export_output(output_dir, formats)

    def export_zip(self, output_dir: str = "output", formats: list[str] | None = None) -> str:
        self._sync_output()
        return self.exporter.export_zip(output_dir, formats)

    def _export_html(self, output_dir: str, timestamp: str) -> Optional[str]:
        self._sync_output()
        return self.exporter._export_html(output_dir, timestamp)

    def _export_markdown(self, output_dir: str, timestamp: str) -> Optional[str]:
        self._sync_output()
        return self.exporter._export_markdown(output_dir, timestamp)

    # ── Checkpoint wrappers (delegate to CheckpointManager) ─────────────────

    def _save_checkpoint(self, layer: int) -> str:
        self._sync_output()
        return self.checkpoint.save(layer)

    @classmethod
    def list_checkpoints(cls) -> list:
        """List available checkpoints sorted newest-first."""
        return CheckpointManager.list_checkpoints()

    def resume_from_checkpoint(
        self,
        checkpoint_path: str,
        progress_callback=None,
        enable_agents: bool = True,
        enable_scoring: bool = True,
        **kwargs,
    ) -> PipelineOutput:
        self._sync_output()
        result = self.checkpoint.resume(checkpoint_path, progress_callback, enable_agents, enable_scoring, **kwargs)
        self.output = result
        self._sync_output()
        return result

    # ── Continuation wrappers (delegate to StoryContinuation) ────────────────

    def load_from_checkpoint(self, checkpoint_path: str) -> Optional[StoryDraft]:
        self._sync_output()
        draft = self.continuation.load_from_checkpoint(checkpoint_path)
        self.output = self.continuation.output
        self._sync_output()
        return draft

    def continue_story(
        self,
        additional_chapters: int = 5,
        word_count: int = 2000,
        style: str = "",
        progress_callback=None,
        stream_callback=None,
    ) -> StoryDraft:
        self._sync_output()
        result = self.continuation.continue_story(
            additional_chapters, word_count, style, progress_callback, stream_callback
        )
        self.output = self.continuation.output
        self._sync_output()
        return result

    def remove_chapters(self, from_chapter: int, progress_callback=None) -> StoryDraft:
        self._sync_output()
        result = self.continuation.remove_chapters(from_chapter, progress_callback)
        self.output = self.continuation.output
        self._sync_output()
        return result

    def update_character(self, char_name: str, updates: dict, progress_callback=None) -> StoryDraft:
        self._sync_output()
        result = self.continuation.update_character(char_name, updates, progress_callback)
        self.output = self.continuation.output
        self._sync_output()
        return result

    def enhance_chapters(
        self,
        num_sim_rounds: int = 3,
        word_count: int = 2000,
        progress_callback=None,
    ) -> Optional[EnhancedStory]:
        self._sync_output()
        result = self.continuation.enhance_chapters(num_sim_rounds, word_count, progress_callback)
        self.output = self.continuation.output
        self._sync_output()
        return result
