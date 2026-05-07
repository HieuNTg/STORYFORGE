"""Coverage tests for PipelineOrchestrator."""
from __future__ import annotations

import os
import sys
import threading
from typing import TYPE_CHECKING

import pytest
from unittest.mock import MagicMock, patch

if TYPE_CHECKING:
    from pipeline.orchestrator import PipelineOrchestrator

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _make_orchestrator(session_id: str = "test-session") -> PipelineOrchestrator:
    """Create a PipelineOrchestrator with all external deps mocked."""
    from pipeline.orchestrator import PipelineOrchestrator
    # Patch constructor-level heavy deps
    with patch("pipeline.orchestrator._make_redis_client", side_effect=RuntimeError("no redis")), \
         patch("pipeline.orchestrator.ConfigManager"), \
         patch("pipeline.orchestrator.StoryGenerator"), \
         patch("pipeline.orchestrator.StoryAnalyzer"), \
         patch("pipeline.orchestrator.DramaSimulator"), \
         patch("pipeline.orchestrator.StoryEnhancer"), \
         patch("pipeline.orchestrator.MediaProducer"), \
         patch("pipeline.orchestrator.PipelineExporter"), \
         patch("pipeline.orchestrator.CheckpointManager"), \
         patch("pipeline.orchestrator.StoryContinuation"):
        orch = PipelineOrchestrator(session_id=session_id)
    return orch


class TestPipelineOrchestratorInit:
    """PipelineOrchestrator construction."""

    def test_creates_with_given_session_id(self):
        orch = _make_orchestrator("my-session")
        assert orch.session_id == "my-session"

    def test_creates_with_auto_session_id(self):
        orch = _make_orchestrator("")
        assert orch.session_id  # not empty
        assert len(orch.session_id) > 8  # looks like a UUID

    def test_redis_unavailable_uses_memory_fallback(self):
        orch = _make_orchestrator()
        assert orch._redis is None  # no Redis connection

    def test_output_is_pipeline_output(self):
        from models.schemas import PipelineOutput
        orch = _make_orchestrator()
        assert isinstance(orch.output, PipelineOutput)

    def test_lock_is_reentrant(self):
        orch = _make_orchestrator()
        assert isinstance(orch._lock, type(threading.RLock()))

    def test_checkpoint_dir_class_attribute(self):
        from pipeline.orchestrator import PipelineOrchestrator, CHECKPOINT_DIR
        assert PipelineOrchestrator.CHECKPOINT_DIR == CHECKPOINT_DIR


class TestMemoryFallbackStore:
    """In-memory fallback for Redis ops."""

    def test_store_set_and_get(self):
        orch = _make_orchestrator("s1")
        orch._store_set("key1", "value1")
        assert orch._store_get("key1") == "value1"

    def test_store_get_missing_key_returns_none(self):
        orch = _make_orchestrator("s2")
        assert orch._store_get("no-such-key") is None

    def test_store_evicts_oldest_when_full(self):
        from pipeline.orchestrator import PipelineOrchestrator
        orch = _make_orchestrator("s3")
        # P2: memory store is now per-instance; reset via instance lock
        with orch._memory_store_lock:
            orch._memory_store.clear()
        # Fill store to max
        max_items = PipelineOrchestrator._MEMORY_STORE_MAX
        for i in range(max_items):
            orch._store_set(f"key_{i}", f"val_{i}")
        assert len(orch._memory_store) == max_items
        # One more should evict the oldest
        orch._store_set("overflow_key", "overflow_val")
        assert len(orch._memory_store) == max_items
        assert orch._store_get("overflow_key") == "overflow_val"
        # First inserted key should be evicted
        assert orch._store_get("key_0") is None


class TestOutputPersistence:
    """_save_output / _load_output using in-memory store."""

    def test_save_and_reload_output(self):
        orch = _make_orchestrator("persist-test")
        # Modify output using a valid field and save
        orch.output.status = "layer1_complete"
        orch._save_output()
        # Load should restore
        loaded = orch._load_output()
        assert loaded is not None
        assert loaded.status == "layer1_complete"

    def test_load_returns_none_when_nothing_stored(self):
        orch = _make_orchestrator("empty-persist")
        # Clear any accidental state
        key = orch._output_key()
        with orch._memory_store_lock:
            orch._memory_store.pop(key, None)
        result = orch._load_output()
        assert result is None

    def test_output_key_contains_session_id(self):
        orch = _make_orchestrator("key-check")
        assert "key-check" in orch._output_key()


class TestSnapshot:
    """snapshot() returns a deep copy."""

    def test_snapshot_returns_copy_not_reference(self):
        orch = _make_orchestrator("snap-test")
        orch.output.status = "original"
        snap = orch.snapshot()
        # Modifying snapshot doesn't affect orch.output
        snap.status = "mutated"
        assert orch.output.status == "original"


class TestSyncOutput:
    """_sync_output propagates output reference."""

    def test_sync_output_updates_sub_components(self):
        orch = _make_orchestrator("sync-test")
        new_output = MagicMock()
        orch.output = new_output
        # Mock _save_output to avoid serialization
        orch._save_output = MagicMock()
        orch._sync_output()
        assert orch.exporter.output is new_output
        assert orch.checkpoint.output is new_output
        assert orch.continuation.output is new_output
        orch._save_output.assert_called_once()


class TestSessionKey:
    """_session_key helper function."""

    def test_session_key_format(self):
        from pipeline.orchestrator import _session_key
        key = _session_key("abc123", "output")
        assert "abc123" in key
        assert "output" in key
        assert key.startswith("storyforge:")


class TestRedisRequired:
    """STORYFORGE_REDIS_REQUIRED env flag causes exception when Redis unavailable."""

    def test_redis_required_raises_on_missing(self):
        from pipeline.orchestrator import PipelineOrchestrator
        with pytest.raises(Exception), \
             patch("pipeline.orchestrator._make_redis_client",
                   side_effect=RuntimeError("no redis")), \
             patch("pipeline.orchestrator.ConfigManager"), \
             patch("pipeline.orchestrator.StoryGenerator"), \
             patch("pipeline.orchestrator.StoryAnalyzer"), \
             patch("pipeline.orchestrator.DramaSimulator"), \
             patch("pipeline.orchestrator.StoryEnhancer"), \
             patch("pipeline.orchestrator.MediaProducer"), \
             patch("pipeline.orchestrator.PipelineExporter"), \
             patch("pipeline.orchestrator.CheckpointManager"), \
             patch("pipeline.orchestrator.StoryContinuation"):
            os.environ["STORYFORGE_REDIS_REQUIRED"] = "true"
            try:
                PipelineOrchestrator(session_id="x")
            finally:
                os.environ.pop("STORYFORGE_REDIS_REQUIRED", None)
