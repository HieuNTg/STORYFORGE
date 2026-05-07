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
import os
import threading
import uuid
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

_SESSION_TTL = 86400  # 24 hours


def _session_key(session_id: str, namespace: str) -> str:
    return f"storyforge:session:{session_id}:{namespace}"


def _make_redis_client():
    """Create Redis client from REDIS_URL. Raises RuntimeError if unavailable."""
    redis_url = os.environ.get("REDIS_URL", "").strip()
    if not redis_url:
        raise RuntimeError(
            "REDIS_URL is not set. Redis is required for session state. "
            "Start Redis via docker-compose and set REDIS_URL."
        )
    try:
        import redis as _redis_lib
    except ImportError as exc:
        raise RuntimeError(
            "redis package is not installed. Run: pip install redis"
        ) from exc
    client = _redis_lib.from_url(redis_url, decode_responses=True)
    client.ping()
    return client


class PipelineOrchestrator:
    """Điều phối toàn bộ pipeline từ input đến output.

    Responsibilities:
    - Instantiate and wire sub-components on construction.
    - Keep sub-components pointing at the current self.output via _sync_output.
    - Delegate all heavy work to orchestrator_layers / sub-component modules.
    - Expose a stable public API so callers never need to import sub-modules.
    - Persist pipeline output in Redis under session-scoped keys (24h TTL).
    """

    CHECKPOINT_DIR = CHECKPOINT_DIR

    # P2: per-instance memory store — class-level was shared across orchestrators
    # (cross-session leakage). Defaults preserved for legacy tests that read the
    # class attribute directly; instance overrides them in __init__.
    _memory_store: dict[str, str] = {}
    _memory_store_lock = threading.Lock()
    _MEMORY_STORE_MAX = 100

    def __init__(self, session_id: str = ""):
        self.config = ConfigManager()
        self.story_gen = StoryGenerator()
        self.analyzer = StoryAnalyzer()
        self.simulator = DramaSimulator()
        self.enhancer = StoryEnhancer()
        self._lock = threading.RLock()
        self.session_id = session_id or str(uuid.uuid4())
        # P2: per-instance fallback store + lock so concurrent sessions cannot
        # see each other's keys when Redis is unavailable.
        self._memory_store = {}
        self._memory_store_lock = threading.Lock()

        self._redis = None
        try:
            self._redis = _make_redis_client()
            logger.debug("PipelineOrchestrator: Redis connected for session %s", self.session_id)
        except Exception as exc:
            if os.environ.get("STORYFORGE_REDIS_REQUIRED", "").lower() in ("1", "true"):
                raise
            logger.warning(
                "PipelineOrchestrator: Redis unavailable, using in-memory fallback "
                "(session state will not survive restarts): %s", exc
            )

        # Load persisted output or start fresh
        self.output = self._load_output() or PipelineOutput()

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

    # ── Redis output persistence ─────────────────────────────────────────────

    def _output_key(self) -> str:
        return _session_key(self.session_id, "output")

    def _store_set(self, key: str, value: str, ttl: int = _SESSION_TTL) -> None:
        """Store a value in Redis or in-memory fallback."""
        if self._redis:
            try:
                self._redis.set(key, value)
                self._redis.expire(key, ttl)
                return
            except Exception as exc:
                logger.warning("Redis store_set failed, using memory: %s", exc)
        with self._memory_store_lock:
            if len(self._memory_store) >= self._MEMORY_STORE_MAX:
                oldest = next(iter(self._memory_store))
                del self._memory_store[oldest]
            self._memory_store[key] = value

    def _store_get(self, key: str) -> Optional[str]:
        """Get a value from Redis or in-memory fallback."""
        if self._redis:
            try:
                val = self._redis.get(key)
                if val is not None:
                    self._redis.expire(key, _SESSION_TTL)
                return val
            except Exception as exc:
                logger.warning("Redis store_get failed, using memory: %s", exc)
        with self._memory_store_lock:
            return self._memory_store.get(key)

    def _save_output(self) -> None:
        """Persist self.output to Redis or in-memory fallback."""
        try:
            self._store_set(self._output_key(), self.output.model_dump_json())
        except Exception as exc:
            logger.warning("PipelineOrchestrator: save output error: %s", exc)

    def _load_output(self) -> Optional[PipelineOutput]:
        """Load output from Redis or in-memory fallback."""
        try:
            raw = self._store_get(self._output_key())
            if raw is None:
                return None
            return PipelineOutput.model_validate_json(raw)
        except Exception as exc:
            logger.warning("PipelineOrchestrator: load output error: %s", exc)
            return None

    # ── Standard orchestrator API ─────────────────────────────────────────────

    def snapshot(self) -> "PipelineOutput":
        """Thread-safe deep copy of current output."""
        with self._lock:
            return self.output.model_copy(deep=True)

    def _sync_output(self):
        """Propagate the current self.output reference to all sub-components.

        Called after any operation that replaces self.output so that
        exporter, checkpoint, and continuation stay consistent.
        Also persists the updated output to Redis.
        """
        self.exporter.output = self.output
        self.checkpoint.output = self.output
        self.continuation.output = self.output
        self.continuation.checkpoint_manager.output = self.output
        self._save_output()

    # ── Layer execution (implemented in orchestrator_layers.py) ─────────────

    async def run_full_pipeline(
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
        """Chạy toàn bộ pipeline 2 lớp (async — blocking LLM calls run in thread pool)."""
        return await _run_full_pipeline(
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

    def generate_continuation_outlines(
        self,
        additional_chapters: int = 5,
        progress_callback=None,
        arc_directives: list = None,
    ) -> list:
        """Generate outlines for continuation without writing chapters."""
        self._sync_output()
        return self.continuation.generate_continuation_outlines(
            additional_chapters=additional_chapters,
            progress_callback=progress_callback,
            arc_directives=arc_directives,
        )

    def write_from_outlines(
        self,
        outlines: list,
        word_count: int = 2000,
        style: str = "",
        progress_callback=None,
        stream_callback=None,
        arc_directives: list = None,
    ) -> Optional[StoryDraft]:
        """Write chapters from pre-generated outlines."""
        self._sync_output()
        result = self.continuation.write_from_outlines(
            outlines=outlines,
            word_count=word_count,
            style=style,
            progress_callback=progress_callback,
            stream_callback=stream_callback,
            arc_directives=arc_directives,
        )
        self.output = self.continuation.output
        self._sync_output()
        return result
