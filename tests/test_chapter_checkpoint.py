"""Sprint 3 Task 2 — Per-chapter checkpoint.

Covers:
- save_chapter writes to output/checkpoints/per_chapter/{slug}_ch{N}_layer{L}.json
- list_chapter_checkpoints filters by slug / layer and parses regex
- resume_from_chapter derives next_chapter from enhanced or draft chapters
- Pruning keeps newest `keep_last` per (slug, layer) group
- Config flags default false, chapter_checkpoint_keep_last defaults to 5
"""
from __future__ import annotations

import os
import shutil
import time
import unittest
from unittest.mock import MagicMock

from models.schemas import Chapter, EnhancedStory, PipelineOutput, StoryDraft
from pipeline.orchestrator_checkpoint import (
    CHAPTER_CHECKPOINT_SUBDIR,
    CheckpointManager,
    _chapter_checkpoint_dir,
    _prune_chapter_checkpoints,
)


def _build_manager(title: str = "Test Story", chapters: list[Chapter] | None = None) -> CheckpointManager:
    draft = StoryDraft(title=title, genre="Test")
    if chapters:
        draft.chapters = list(chapters)
    output = PipelineOutput(story_draft=draft)
    return CheckpointManager(output=output, analyzer=MagicMock(), simulator=MagicMock(), enhancer=MagicMock())


class _CleanDirMixin:
    def setUp(self):
        self._dir = _chapter_checkpoint_dir()
        if os.path.exists(self._dir):
            shutil.rmtree(self._dir)

    def tearDown(self):
        if os.path.exists(self._dir):
            shutil.rmtree(self._dir)


class TestSaveChapter(_CleanDirMixin, unittest.TestCase):
    def test_save_chapter_writes_expected_filename(self):
        mgr = _build_manager(title="A Hero's Tale")
        path = mgr.save_chapter(chapter_number=3, layer=1, background=False)
        self.assertTrue(os.path.exists(path))
        self.assertIn("_ch3_layer1_", os.path.basename(path))
        self.assertTrue(path.endswith(".json"))
        self.assertIn(CHAPTER_CHECKPOINT_SUBDIR, path)

    def test_save_chapter_slug_sanitizes_title(self):
        mgr = _build_manager(title="Spaces / & Weird:*Chars")
        path = mgr.save_chapter(chapter_number=1, layer=1, background=False)
        fname = os.path.basename(path)
        self.assertNotIn("/", fname)
        self.assertNotIn(":", fname)
        self.assertNotIn("*", fname)

    def test_save_chapter_with_no_draft_uses_untitled(self):
        output = PipelineOutput()
        mgr = CheckpointManager(output=output, analyzer=MagicMock(), simulator=MagicMock(), enhancer=MagicMock())
        path = mgr.save_chapter(chapter_number=2, layer=1, background=False)
        fname = os.path.basename(path)
        self.assertTrue(fname.startswith("untitled_"))
        self.assertIn("_ch2_layer1_", fname)


class TestListChapterCheckpoints(_CleanDirMixin, unittest.TestCase):
    def test_returns_empty_when_dir_missing(self):
        # setUp already removed the dir
        self.assertEqual(CheckpointManager.list_chapter_checkpoints(), [])

    def test_filters_by_slug_and_layer(self):
        mgr_a = _build_manager(title="Alpha")
        mgr_b = _build_manager(title="Bravo")
        mgr_a.save_chapter(1, 1, background=False)
        mgr_a.save_chapter(2, 1, background=False)
        mgr_a.save_chapter(2, 2, background=False)
        mgr_b.save_chapter(1, 1, background=False)

        all_entries = CheckpointManager.list_chapter_checkpoints()
        self.assertEqual(len(all_entries), 4)

        alpha_only = CheckpointManager.list_chapter_checkpoints(slug="Alpha")
        self.assertEqual(len(alpha_only), 3)
        self.assertTrue(all(e["slug"] == "Alpha" for e in alpha_only))

        alpha_l1 = CheckpointManager.list_chapter_checkpoints(slug="Alpha", layer=1)
        self.assertEqual(len(alpha_l1), 2)
        self.assertTrue(all(e["layer"] == 1 for e in alpha_l1))

    def test_sort_order_layer_then_chapter_desc(self):
        mgr = _build_manager(title="S")
        for ch in (1, 2, 3):
            mgr.save_chapter(ch, 1, background=False)
        mgr.save_chapter(1, 2, background=False)

        entries = CheckpointManager.list_chapter_checkpoints(slug="S")
        self.assertEqual(entries[0]["layer"], 2)
        self.assertEqual(entries[1]["chapter"], 3)
        self.assertEqual(entries[-1]["chapter"], 1)


class TestResumeFromChapter(_CleanDirMixin, unittest.TestCase):
    def test_next_ch_from_draft_when_no_enhanced(self):
        chapters = [Chapter(chapter_number=i, title=f"T{i}", content="x") for i in (1, 2, 3)]
        mgr = _build_manager(title="Run", chapters=chapters)
        path = mgr.save_chapter(3, 1, background=False)

        fresh = CheckpointManager(
            output=PipelineOutput(), analyzer=MagicMock(),
            simulator=MagicMock(), enhancer=MagicMock(),
        )
        output, next_ch = fresh.resume_from_chapter(path)
        self.assertEqual(next_ch, 4)
        self.assertEqual(len(output.story_draft.chapters), 3)

    def test_next_ch_from_enhanced_when_present(self):
        draft_chapters = [Chapter(chapter_number=i, title=f"T{i}", content="x") for i in (1, 2, 3)]
        enhanced_chapters = [Chapter(chapter_number=i, title=f"E{i}", content="y") for i in (1, 2, 3, 4, 5)]
        mgr = _build_manager(title="Run2", chapters=draft_chapters)
        mgr.output.enhanced_story = EnhancedStory(
            title="Run2", genre="Test", chapters=enhanced_chapters,
            enhancement_notes=[], drama_score=0.0,
        )
        path = mgr.save_chapter(5, 2, background=False)

        fresh = CheckpointManager(
            output=PipelineOutput(), analyzer=MagicMock(),
            simulator=MagicMock(), enhancer=MagicMock(),
        )
        output, next_ch = fresh.resume_from_chapter(path)
        self.assertEqual(next_ch, 6)

    def test_next_ch_is_1_when_no_chapters(self):
        mgr = _build_manager(title="Empty")
        path = mgr.save_chapter(0, 1, background=False)
        fresh = CheckpointManager(
            output=PipelineOutput(), analyzer=MagicMock(),
            simulator=MagicMock(), enhancer=MagicMock(),
        )
        _, next_ch = fresh.resume_from_chapter(path)
        self.assertEqual(next_ch, 1)

    def test_corrupted_checkpoint_raises(self):
        os.makedirs(_chapter_checkpoint_dir(), exist_ok=True)
        bad_path = os.path.join(_chapter_checkpoint_dir(), "bad_ch1_layer1.json")
        with open(bad_path, "w", encoding="utf-8") as f:
            f.write("{not valid json")
        mgr = _build_manager(title="X")
        with self.assertRaises(ValueError):
            mgr.resume_from_chapter(bad_path)


class TestPrune(_CleanDirMixin, unittest.TestCase):
    def test_prune_keeps_newest_n(self):
        out_dir = _chapter_checkpoint_dir()
        os.makedirs(out_dir, exist_ok=True)
        # Create 7 files with increasing mtime
        for i in range(7):
            path = os.path.join(out_dir, f"Story_ch{i}_layer1.json")
            with open(path, "w") as f:
                f.write("{}")
            os.utime(path, (time.time() + i, time.time() + i))

        _prune_chapter_checkpoints(out_dir, "Story", 1, keep_last=3)

        remaining = sorted(os.listdir(out_dir))
        self.assertEqual(len(remaining), 3)
        # Newest three are ch4, ch5, ch6
        self.assertEqual(remaining, ["Story_ch4_layer1.json",
                                     "Story_ch5_layer1.json",
                                     "Story_ch6_layer1.json"])

    def test_prune_ignores_other_slugs_and_layers(self):
        out_dir = _chapter_checkpoint_dir()
        os.makedirs(out_dir, exist_ok=True)
        for fname in ("A_ch1_layer1.json", "A_ch2_layer1.json",
                      "B_ch1_layer1.json", "A_ch1_layer2.json"):
            with open(os.path.join(out_dir, fname), "w") as f:
                f.write("{}")

        _prune_chapter_checkpoints(out_dir, "A", 1, keep_last=1)
        remaining = set(os.listdir(out_dir))
        # A/layer1 pruned to 1, others untouched
        self.assertEqual(remaining,
                         {"A_ch2_layer1.json", "B_ch1_layer1.json", "A_ch1_layer2.json"})

    def test_prune_noop_when_keep_last_zero(self):
        out_dir = _chapter_checkpoint_dir()
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, "X_ch1_layer1.json")
        with open(path, "w") as f:
            f.write("{}")
        _prune_chapter_checkpoints(out_dir, "X", 1, keep_last=0)
        self.assertTrue(os.path.exists(path))

    def test_save_chapter_triggers_prune(self):
        mgr = _build_manager(title="Pruner")
        mgr._chapter_keep_last = 2
        for ch in (1, 2, 3, 4):
            mgr.save_chapter(ch, 1, background=False)
        # After 4 writes with keep_last=2, only 2 files remain for (Pruner, layer=1)
        entries = CheckpointManager.list_chapter_checkpoints(slug="Pruner", layer=1)
        self.assertEqual(len(entries), 2)
        chapters = sorted(e["chapter"] for e in entries)
        self.assertEqual(chapters, [3, 4])


class TestConfigDefaults(unittest.TestCase):
    def test_enable_chapter_checkpoint_default_false(self):
        from config.defaults import PipelineConfig
        cfg = PipelineConfig()
        self.assertFalse(cfg.enable_chapter_checkpoint)

    def test_chapter_checkpoint_keep_last_default(self):
        from config.defaults import PipelineConfig
        cfg = PipelineConfig()
        self.assertEqual(cfg.chapter_checkpoint_keep_last, 5)
        self.assertEqual(cfg.chapter_checkpoint_every_n_batches, 1)


if __name__ == "__main__":
    unittest.main()
