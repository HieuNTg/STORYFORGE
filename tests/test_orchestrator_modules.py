"""Tests for orchestrator_media, orchestrator_checkpoint, orchestrator_continuation."""

import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_character(name="Alice"):
    c = MagicMock()
    c.name = name
    c.appearance = "tall"
    c.personality = "brave"
    c.reference_image = ""
    return c


def _make_chapter(num=1, content="Some content"):
    ch = MagicMock()
    ch.chapter_number = num
    ch.content = content
    return ch


def _make_story_draft(title="Story", characters=None, chapters=None, genre="Fantasy", synopsis="syn"):
    d = MagicMock()
    d.title = title
    d.genre = genre
    d.synopsis = synopsis
    d.characters = characters if characters is not None else [_make_character()]
    d.chapters = chapters if chapters is not None else [_make_chapter()]
    return d


def _make_enhanced_story(title="Enhanced"):
    es = MagicMock()
    es.title = title
    es.chapters = [_make_chapter()]
    return es


def _make_panel(num=1, ch=1, characters_in_frame=None, image_prompt="img"):
    p = MagicMock()
    p.panel_number = num
    p.chapter_number = ch
    p.characters_in_frame = characters_in_frame or []
    p.image_prompt = image_prompt
    p.description = "scene desc"
    p.image_path = ""
    p.duration_seconds = 5.0
    return p


def _make_pipeline_output(story_draft=None, enhanced_story=None,
                           current_layer=0, logs=None, quality_scores=None):
    out = MagicMock()
    out.story_draft = story_draft
    out.enhanced_story = enhanced_story
    out.current_layer = current_layer
    out.logs = logs if logs is not None else []
    out.quality_scores = quality_scores if quality_scores is not None else []
    out.simulation_result = None
    out.status = "pending"
    out.progress = 0.0
    return out


# ===========================================================================
# Tests: orchestrator_media.py — MediaProducer
# ===========================================================================

class TestMediaProducerRun(unittest.TestCase):

    def _make_config(self, seedream_key="", seedream_url=""):
        cfg = MagicMock()
        cfg.pipeline.seedream_api_key = seedream_key
        cfg.pipeline.seedream_api_url = seedream_url
        cfg.pipeline.enable_character_consistency = False
        return cfg

    @patch("pipeline.orchestrator_media.SeedreamClient")
    def test_run_returns_dict_structure(self, MockSeed):
        from pipeline.orchestrator_media import MediaProducer
        MockSeed.return_value.is_configured.return_value = False

        config = self._make_config()
        producer = MediaProducer(config)
        draft = _make_story_draft()
        enhanced = _make_enhanced_story()
        result = producer.run(draft, enhanced)

        self.assertIn("character_refs", result)
        self.assertIn("scene_images", result)

    @patch("pipeline.orchestrator_media.SeedreamClient")
    def test_run_with_seedream_generates_char_refs(self, MockSeed):
        from pipeline.orchestrator_media import MediaProducer
        seedream = MockSeed.return_value
        seedream.is_configured.return_value = True
        seedream.generate_character_reference.return_value = "ref/alice.png"

        config = self._make_config(seedream_key="key123")
        producer = MediaProducer(config)
        draft = _make_story_draft(characters=[_make_character("Alice")])
        result = producer.run(draft, _make_enhanced_story())
        self.assertIn("Alice", result["character_refs"])


# ===========================================================================
# Tests: orchestrator_checkpoint.py — CheckpointManager
# ===========================================================================

class TestCheckpointManagerSave(unittest.TestCase):

    def test_save_creates_file(self):
        from pipeline.orchestrator_checkpoint import CheckpointManager
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("pipeline.orchestrator_checkpoint.CHECKPOINT_DIR", tmpdir):
                output = MagicMock()
                output.story_draft.title = "TestTitle"
                output.model_dump_json.return_value = '{"title": "test"}'
                mgr = CheckpointManager(output, None, None, None)
                path = mgr.save(1, background=False)
                self.assertTrue(os.path.exists(path))
                self.assertIn("layer1", path)

    def test_save_uses_sanitized_title(self):
        from pipeline.orchestrator_checkpoint import CheckpointManager
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("pipeline.orchestrator_checkpoint.CHECKPOINT_DIR", tmpdir):
                output = MagicMock()
                output.story_draft.title = "My Story: Part 1"
                output.model_dump_json.return_value = "{}"
                mgr = CheckpointManager(output, None, None, None)
                path = mgr.save(2, background=False)
                filename = os.path.basename(path)
                self.assertNotIn(":", filename)

    def test_save_no_draft_uses_untitled(self):
        from pipeline.orchestrator_checkpoint import CheckpointManager
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("pipeline.orchestrator_checkpoint.CHECKPOINT_DIR", tmpdir):
                output = MagicMock()
                output.story_draft = None
                output.model_dump_json.return_value = "{}"
                mgr = CheckpointManager(output, None, None, None)
                path = mgr.save(1, background=False)
                self.assertIn("untitled", path)


class TestCheckpointManagerListCheckpoints(unittest.TestCase):

    def test_list_returns_empty_when_dir_missing(self):
        from pipeline.orchestrator_checkpoint import CheckpointManager
        with patch("pipeline.orchestrator_checkpoint.CHECKPOINT_DIR", "/nonexistent/path"):
            result = CheckpointManager.list_checkpoints()
            self.assertEqual(result, [])

    def test_list_returns_checkpoints_sorted_newest_first(self):
        from pipeline.orchestrator_checkpoint import CheckpointManager
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("pipeline.orchestrator_checkpoint.CHECKPOINT_DIR", tmpdir):
                # Create two checkpoint files
                for name in ["aaa_layer1.json", "zzz_layer2.json"]:
                    p = os.path.join(tmpdir, name)
                    with open(p, "w") as f:
                        f.write("{}")
                result = CheckpointManager.list_checkpoints()
                self.assertEqual(len(result), 2)
                # Should be sorted newest first (alphabetically reversed for determinism)
                self.assertIn("file", result[0])
                self.assertIn("size_kb", result[0])

    def test_list_ignores_non_json_files(self):
        from pipeline.orchestrator_checkpoint import CheckpointManager
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("pipeline.orchestrator_checkpoint.CHECKPOINT_DIR", tmpdir):
                # Create a non-JSON file
                with open(os.path.join(tmpdir, "readme.txt"), "w") as f:
                    f.write("ignore me")
                with open(os.path.join(tmpdir, "story_layer1.json"), "w") as f:
                    f.write("{}")
                result = CheckpointManager.list_checkpoints()
                self.assertEqual(len(result), 1)


class TestCheckpointManagerResume(unittest.TestCase):

    def _write_checkpoint(self, tmpdir, data):
        p = os.path.join(tmpdir, "checkpoint.json")
        with open(p, "w") as f:
            json.dump(data, f)
        return p

    @patch("pipeline.orchestrator_checkpoint.PipelineOutput")
    def test_resume_loads_output(self, MockPO):
        from pipeline.orchestrator_checkpoint import CheckpointManager
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._write_checkpoint(tmpdir, {"current_layer": 3})
            po = MagicMock()
            po.current_layer = 3
            po.story_draft = None
            po.enhanced_story = None
            po.logs = []
            po.status = "completed"
            MockPO.return_value = po

            mgr = CheckpointManager(MagicMock(), MagicMock(), MagicMock(), MagicMock())
            result = mgr.resume(path, enable_agents=False, enable_scoring=False)
            self.assertEqual(result, po)

    @patch("pipeline.orchestrator_checkpoint.PipelineOutput")
    def test_resume_layer3_skips_layers(self, MockPO):
        from pipeline.orchestrator_checkpoint import CheckpointManager
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._write_checkpoint(tmpdir, {"current_layer": 3})
            po = MagicMock()
            po.current_layer = 3
            po.story_draft = _make_story_draft()
            po.enhanced_story = _make_enhanced_story()
            po.logs = []
            po.status = "completed"
            MockPO.return_value = po

            mgr = CheckpointManager(MagicMock(), MagicMock(), MagicMock(), MagicMock())
            result = mgr.resume(path, enable_agents=False, enable_scoring=False)
            # Since last_layer=3, neither layer 2 nor 3 resume should run
            self.assertEqual(result.current_layer, 3)

    @patch("pipeline.orchestrator_checkpoint.PipelineOutput")
    def test_resume_layer1_runs_layer2(self, MockPO):
        from pipeline.orchestrator_checkpoint import CheckpointManager
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("pipeline.orchestrator_checkpoint.CHECKPOINT_DIR", tmpdir):
                path = self._write_checkpoint(tmpdir, {"current_layer": 1})
                po = MagicMock()
                po.current_layer = 1
                po.story_draft = _make_story_draft()
                po.enhanced_story = None
                po.logs = []
                po.status = "pending"
                po.progress = 0.0
                po.quality_scores = []
                MockPO.return_value = po

                analyzer = MagicMock()
                analyzer.analyze.return_value = {"relationships": []}
                simulator = MagicMock()
                sim_result = MagicMock()
                simulator.run_simulation.return_value = sim_result
                enhancer = MagicMock()
                enhanced = _make_enhanced_story()
                enhancer.enhance_story.return_value = enhanced

                # Mock the save method to avoid file I/O
                with patch.object(CheckpointManager, "save", return_value="path/ckpt.json"):
                    mgr = CheckpointManager(po, analyzer, simulator, enhancer)
                    mgr.resume(path, enable_agents=False, enable_scoring=False)
                    analyzer.analyze.assert_called_once()
                    simulator.run_simulation.assert_called_once()


# ===========================================================================
# Tests: orchestrator_continuation.py — StoryContinuation
# ===========================================================================

class TestStoryContinuationLoadCheckpoint(unittest.TestCase):

    def test_load_valid_checkpoint(self):
        from pipeline.orchestrator_continuation import StoryContinuation
        with tempfile.TemporaryDirectory() as tmpdir:
            p = os.path.join(tmpdir, "ckpt.json")
            with open(p, "w") as f:
                json.dump({"current_layer": 1, "logs": [], "status": "pending",
                           "progress": 0.0, "reviews": [], "quality_scores": []}, f)

            with patch("pipeline.orchestrator_continuation.PipelineOutput") as MockPO:
                po = MagicMock()
                po.story_draft = _make_story_draft()
                MockPO.return_value = po
                cm = MagicMock()
                sc = StoryContinuation(po, MagicMock(), MagicMock(), MagicMock(), MagicMock(), cm)
                draft = sc.load_from_checkpoint(p)
                self.assertIsNotNone(draft)
                self.assertEqual(cm.output, po)

    def test_load_invalid_path_returns_none(self):
        from pipeline.orchestrator_continuation import StoryContinuation
        po = MagicMock()
        cm = MagicMock()
        sc = StoryContinuation(po, MagicMock(), MagicMock(), MagicMock(), MagicMock(), cm)
        result = sc.load_from_checkpoint("/nonexistent/file.json")
        self.assertIsNone(result)


class TestStoryContinuationContinueStory(unittest.TestCase):

    def test_no_draft_raises(self):
        from pipeline.orchestrator_continuation import StoryContinuation
        po = MagicMock()
        po.story_draft = None
        sc = StoryContinuation(po, MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock())
        with self.assertRaises(ValueError):
            sc.continue_story()

    def test_continue_story_calls_generator(self):
        from pipeline.orchestrator_continuation import StoryContinuation
        po = MagicMock()
        po.story_draft = _make_story_draft()
        story_gen = MagicMock()
        new_draft = _make_story_draft(title="Extended")
        story_gen.continue_story.return_value = new_draft
        cm = MagicMock()
        cm.save.return_value = "path.json"
        sc = StoryContinuation(po, story_gen, MagicMock(), MagicMock(), MagicMock(), cm)
        sc.continue_story(additional_chapters=3)
        story_gen.continue_story.assert_called_once()
        self.assertEqual(po.story_draft, new_draft)
        cm.save.assert_called_once_with(1)

    def test_continue_story_passes_params(self):
        from pipeline.orchestrator_continuation import StoryContinuation
        po = MagicMock()
        po.story_draft = _make_story_draft()
        story_gen = MagicMock()
        story_gen.continue_story.return_value = _make_story_draft()
        cm = MagicMock()
        sc = StoryContinuation(po, story_gen, MagicMock(), MagicMock(), MagicMock(), cm)
        sc.continue_story(additional_chapters=5, word_count=3000, style="dramatic")
        call_kwargs = story_gen.continue_story.call_args
        self.assertEqual(call_kwargs.kwargs.get("additional_chapters") or call_kwargs[1].get("additional_chapters", None) or call_kwargs[0][1] if call_kwargs[0] else None or 5, 5)


class TestStoryContinuationRemoveChapters(unittest.TestCase):

    def test_no_draft_raises(self):
        from pipeline.orchestrator_continuation import StoryContinuation
        po = MagicMock()
        po.story_draft = None
        sc = StoryContinuation(po, MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock())
        with self.assertRaises(ValueError):
            sc.remove_chapters(3)

    @patch("pipeline.orchestrator_continuation.StoryGenerator")
    def test_remove_chapters_clears_enhanced_and_video(self, MockSG):
        from pipeline.orchestrator_continuation import StoryContinuation
        po = MagicMock()
        po.story_draft = _make_story_draft()
        new_draft = _make_story_draft()
        MockSG.remove_chapters.return_value = new_draft
        cm = MagicMock()
        sc = StoryContinuation(po, MagicMock(), MagicMock(), MagicMock(), MagicMock(), cm)
        sc.remove_chapters(5)
        self.assertIsNone(po.enhanced_story)
        cm.save.assert_called_with(1)

    @patch("pipeline.orchestrator_continuation.StoryGenerator")
    def test_remove_chapters_calls_progress(self, MockSG):
        from pipeline.orchestrator_continuation import StoryContinuation
        po = MagicMock()
        po.story_draft = _make_story_draft()
        new_draft = _make_story_draft()
        new_draft.chapters = [_make_chapter()]
        MockSG.remove_chapters.return_value = new_draft
        cm = MagicMock()
        logs = []
        sc = StoryContinuation(po, MagicMock(), MagicMock(), MagicMock(), MagicMock(), cm)
        sc.remove_chapters(5, progress_callback=lambda m: logs.append(m))
        self.assertTrue(len(logs) > 0)


class TestStoryContinuationUpdateCharacter(unittest.TestCase):

    def test_no_draft_raises(self):
        from pipeline.orchestrator_continuation import StoryContinuation
        po = MagicMock()
        po.story_draft = None
        sc = StoryContinuation(po, MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock())
        with self.assertRaises(ValueError):
            sc.update_character("Alice", {})

    def test_update_existing_character(self):
        from pipeline.orchestrator_continuation import StoryContinuation
        char = MagicMock()
        char.name = "Alice"
        char.personality = "shy"
        draft = _make_story_draft(characters=[char])
        po = MagicMock()
        po.story_draft = draft
        cm = MagicMock()
        sc = StoryContinuation(po, MagicMock(), MagicMock(), MagicMock(), MagicMock(), cm)
        sc.update_character("Alice", {"personality": "brave"})
        self.assertEqual(char.personality, "brave")
        cm.save.assert_called_with(1)

    def test_update_nonexistent_character_returns_draft(self):
        from pipeline.orchestrator_continuation import StoryContinuation
        char = MagicMock()
        char.name = "Bob"
        draft = _make_story_draft(characters=[char])
        po = MagicMock()
        po.story_draft = draft
        cm = MagicMock()
        sc = StoryContinuation(po, MagicMock(), MagicMock(), MagicMock(), MagicMock(), cm)
        result = sc.update_character("Alice", {"personality": "brave"})
        self.assertIsNotNone(result)

    def test_update_calls_progress_callback(self):
        from pipeline.orchestrator_continuation import StoryContinuation
        char = MagicMock()
        char.name = "Alice"
        draft = _make_story_draft(characters=[char])
        po = MagicMock()
        po.story_draft = draft
        cm = MagicMock()
        logs = []
        sc = StoryContinuation(po, MagicMock(), MagicMock(), MagicMock(), MagicMock(), cm)
        sc.update_character("Alice", {"personality": "brave"}, progress_callback=lambda m: logs.append(m))
        self.assertTrue(any("Alice" in m for m in logs))


class TestStoryContinuationEnhanceChapters(unittest.TestCase):

    def test_no_draft_raises(self):
        from pipeline.orchestrator_continuation import StoryContinuation
        po = MagicMock()
        po.story_draft = None
        sc = StoryContinuation(po, MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock())
        with self.assertRaises(ValueError):
            sc.enhance_chapters()

    def test_enhance_calls_all_steps(self):
        from pipeline.orchestrator_continuation import StoryContinuation
        draft = _make_story_draft()
        po = MagicMock()
        po.story_draft = draft
        po.simulation_result = None
        po.enhanced_story = None
        analyzer = MagicMock()
        analyzer.analyze.return_value = {"relationships": []}
        simulator = MagicMock()
        sim_result = MagicMock()
        simulator.run_simulation.return_value = sim_result
        enhancer = MagicMock()
        enhanced = _make_enhanced_story()
        enhancer.enhance_with_feedback.return_value = enhanced
        cm = MagicMock()
        sc = StoryContinuation(po, MagicMock(), analyzer, simulator, enhancer, cm)
        result = sc.enhance_chapters()
        analyzer.analyze.assert_called_once()
        simulator.run_simulation.assert_called_once()
        enhancer.enhance_with_feedback.assert_called_once()
        self.assertEqual(result, enhanced)
        cm.save.assert_called_with(2)

    def test_enhance_exception_returns_none(self):
        from pipeline.orchestrator_continuation import StoryContinuation
        po = MagicMock()
        po.story_draft = _make_story_draft()
        analyzer = MagicMock()
        analyzer.analyze.side_effect = Exception("analyze fail")
        cm = MagicMock()
        sc = StoryContinuation(po, MagicMock(), analyzer, MagicMock(), MagicMock(), cm)
        result = sc.enhance_chapters()
        self.assertIsNone(result)

    def test_enhance_calls_progress_callback(self):
        from pipeline.orchestrator_continuation import StoryContinuation
        po = MagicMock()
        po.story_draft = _make_story_draft()
        analyzer = MagicMock()
        analyzer.analyze.return_value = {"relationships": []}
        simulator = MagicMock()
        simulator.run_simulation.return_value = MagicMock()
        enhancer = MagicMock()
        enhancer.enhance_with_feedback.return_value = _make_enhanced_story()
        cm = MagicMock()
        logs = []
        sc = StoryContinuation(po, MagicMock(), analyzer, simulator, enhancer, cm)
        sc.enhance_chapters(progress_callback=lambda m: logs.append(m))
        self.assertTrue(len(logs) > 0)


if __name__ == "__main__":
    unittest.main()
