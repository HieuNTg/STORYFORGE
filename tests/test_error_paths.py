"""Error path tests — retries exhausted, bad directories, corrupted checkpoints, invalid config."""
import json
import os
import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_llm_config(api_key="valid-key"):
    cfg = MagicMock()
    cfg.llm.api_key = api_key
    cfg.llm.base_url = "http://api.test"
    cfg.llm.model = "gpt-4"
    cfg.llm.cheap_model = ""
    cfg.llm.cheap_base_url = ""
    cfg.llm.fallback_models = []
    cfg.llm.temperature = 0.7
    cfg.llm.max_tokens = 2000
    cfg.llm.cache_enabled = False
    cfg.llm.cache_ttl_days = 7
    cfg.pipeline.language = "vi"
    cfg.pipeline.share_base_url = ""
    return cfg


def _reset_llm_singleton():
    from services import llm_client
    llm_client.LLMClient._instance = None


# ---------------------------------------------------------------------------
# 1. LLM client: all retries exhausted → RuntimeError
# ---------------------------------------------------------------------------

class TestLLMAllRetriesExhausted:

    def setup_method(self):
        _reset_llm_singleton()

    def teardown_method(self):
        _reset_llm_singleton()

    @patch("services.llm_client.ConfigManager")
    @patch("services.llm_client.LLMCache")
    def test_all_retries_exhausted_raises_runtime_error(self, MockCache, MockCM):
        """When single provider exhausts all 3 retries, RuntimeError is raised."""
        from services.llm_client import LLMClient
        cfg = _make_llm_config()
        MockCM.return_value = cfg
        MockCache.return_value.get.return_value = None

        client = LLMClient()

        failing = MagicMock()
        # Always raises transient error — _try_provider retries MAX_RETRIES times then re-raises
        failing.chat.completions.create.side_effect = Exception("timeout 503")
        client._build_fallback_chain = MagicMock(return_value=[
            {"client": failing, "model": "gpt-4", "label": "primary"},
        ])

        with patch("services.llm_client.time"):
            with patch("services.prompts.localize_prompt", side_effect=lambda p, lang: p):
                with pytest.raises(RuntimeError):
                    client.generate("system", "user prompt")

    @patch("services.llm_client.ConfigManager")
    @patch("services.llm_client.LLMCache")
    def test_three_attempts_made_before_exhaustion(self, MockCache, MockCM):
        """Provider is called MAX_RETRIES (3) times before giving up."""
        from services.llm_client import LLMClient, MAX_RETRIES
        cfg = _make_llm_config()
        MockCM.return_value = cfg
        MockCache.return_value.get.return_value = None

        client = LLMClient()

        failing = MagicMock()
        failing.chat.completions.create.side_effect = Exception("timeout")
        client._build_fallback_chain = MagicMock(return_value=[
            {"client": failing, "model": "gpt-4", "label": "primary"},
        ])

        with patch("services.llm_client.time"):
            with patch("services.prompts.localize_prompt", side_effect=lambda p, lang: p):
                with pytest.raises((RuntimeError, Exception)):
                    client.generate("system", "user")

        assert failing.chat.completions.create.call_count == MAX_RETRIES

    @patch("services.llm_client.ConfigManager")
    @patch("services.llm_client.LLMCache")
    def test_all_fallbacks_exhausted_raises_runtime_error(self, MockCache, MockCM):
        """When primary + all fallbacks fail, RuntimeError is raised."""
        from services.llm_client import LLMClient
        cfg = _make_llm_config()
        MockCM.return_value = cfg
        MockCache.return_value.get.return_value = None

        client = LLMClient()

        def _make_failing():
            m = MagicMock()
            m.chat.completions.create.side_effect = Exception("timeout")
            return m

        client._build_fallback_chain = MagicMock(return_value=[
            {"client": _make_failing(), "model": "gpt-4", "label": "primary"},
            {"client": _make_failing(), "model": "gpt-3.5", "label": "cheap"},
            {"client": _make_failing(), "model": "claude", "label": "fallback:claude"},
        ])

        with patch("services.llm_client.time"):
            with patch("services.prompts.localize_prompt", side_effect=lambda p, lang: p):
                with pytest.raises(RuntimeError):
                    client.generate("sys", "usr")


# ---------------------------------------------------------------------------
# 2. Export to non-existent directory → graceful error (not crash)
# ---------------------------------------------------------------------------

class TestExportToNonExistentDirectory:

    def test_html_export_creates_parent_dirs_automatically(self, tmp_path):
        """HTMLExporter creates missing parent dirs — should not raise."""
        from models.schemas import StoryDraft, Chapter
        from services.html_exporter import HTMLExporter

        story = StoryDraft(
            title="Test",
            genre="test",
            chapters=[Chapter(chapter_number=1, title="Ch1", content="Content")],
        )
        output_path = str(tmp_path / "deep" / "nested" / "output.html")
        result = HTMLExporter.export(story, output_path)
        assert result == output_path
        assert os.path.exists(output_path)

    def test_epub_export_creates_parent_dirs_automatically(self, tmp_path):
        """EPUBExporter creates missing parent dirs — should not raise."""
        pytest.importorskip("ebooklib")
        from models.schemas import StoryDraft, Chapter
        from services.epub_exporter import EPUBExporter

        story = StoryDraft(
            title="Test",
            genre="test",
            chapters=[Chapter(chapter_number=1, title="Ch1", content="Hello world")],
        )
        output_path = str(tmp_path / "subdir" / "story.epub")
        result = EPUBExporter.export(story, output_path)
        assert result == output_path
        assert os.path.exists(output_path)

    def test_epub_export_missing_ebooklib_returns_empty_string(self):
        """EPUBExporter returns '' gracefully when ebooklib is not installed."""
        from models.schemas import StoryDraft, Chapter
        from services.epub_exporter import EPUBExporter

        story = StoryDraft(
            title="Test",
            genre="test",
            chapters=[Chapter(chapter_number=1, title="Ch1", content="Content")],
        )
        with patch.dict("sys.modules", {"ebooklib": None, "ebooklib.epub": None}):
            result = EPUBExporter.export(story, "/nonexistent/path/story.epub")
        assert result == ""

    def test_share_manager_html_fallback_on_export_error(self, tmp_path, monkeypatch):
        """ShareManager gracefully falls back to basic HTML if export raises."""
        from models.schemas import StoryDraft, Chapter
        from services.share_manager import ShareManager

        monkeypatch.setattr(ShareManager, "SHARES_DIR", str(tmp_path / "shares"))
        monkeypatch.setattr(ShareManager, "SHARES_INDEX", str(tmp_path / "shares" / "index.json"))

        mgr = ShareManager()
        story = StoryDraft(
            title="My <Story>",
            genre="test",
            chapters=[Chapter(chapter_number=1, title="Ch1", content="Content")],
        )

        with patch("services.html_exporter.HTMLExporter.export", side_effect=Exception("export failed")):
            share = mgr.create_share(story)

        assert share.share_id != ""
        assert os.path.exists(share.html_path)
        with open(share.html_path, encoding="utf-8") as f:
            content = f.read()
        # Title should be HTML-escaped in fallback
        assert "<script>" not in content


# ---------------------------------------------------------------------------
# 3. Checkpoint load with corrupted JSON → ValueError raised, not crash
# ---------------------------------------------------------------------------

class TestCheckpointCorruptedJSON:

    def _make_minimal_output(self):
        """Build a minimal PipelineOutput for CheckpointManager init."""
        from models.schemas import PipelineOutput, StoryDraft
        draft = StoryDraft(title="Test", genre="test", chapters=[])
        return PipelineOutput(story_draft=draft)

    def _make_checkpoint_manager(self):
        from pipeline.orchestrator_checkpoint import CheckpointManager
        output = self._make_minimal_output()
        analyzer = MagicMock()
        simulator = MagicMock()
        enhancer = MagicMock()
        return CheckpointManager(output, analyzer, simulator, enhancer)

    def test_corrupted_json_raises_value_error(self, tmp_path):
        """Checkpoint with broken JSON raises ValueError, not a bare crash."""
        mgr = self._make_checkpoint_manager()
        bad_file = tmp_path / "corrupt.json"
        bad_file.write_text("{not valid json:::}", encoding="utf-8")

        with pytest.raises(ValueError, match="Checkpoint corrupted"):
            mgr.resume(str(bad_file))

    def test_empty_file_raises_value_error(self, tmp_path):
        """Empty checkpoint file raises ValueError gracefully."""
        mgr = self._make_checkpoint_manager()
        empty_file = tmp_path / "empty.json"
        empty_file.write_text("", encoding="utf-8")

        with pytest.raises(ValueError):
            mgr.resume(str(empty_file))

    def test_truncated_json_raises_value_error(self, tmp_path):
        """Truncated JSON (partial write) raises ValueError."""
        mgr = self._make_checkpoint_manager()
        truncated_file = tmp_path / "truncated.json"
        truncated_file.write_text('{"story_draft": {"title": "Test"', encoding="utf-8")

        with pytest.raises(ValueError):
            mgr.resume(str(truncated_file))

    def test_list_checkpoints_no_dir_returns_empty(self):
        """list_checkpoints() returns [] gracefully when dir doesn't exist."""
        from pipeline.orchestrator_checkpoint import CheckpointManager
        with patch("pipeline.orchestrator_checkpoint.CHECKPOINT_DIR", "/no/such/dir"):
            result = CheckpointManager.list_checkpoints()
        assert result == []

    def test_save_checkpoint_creates_file(self, tmp_path):
        """Save checkpoint writes a readable JSON file without crashing."""
        mgr = self._make_checkpoint_manager()
        with patch("pipeline.orchestrator_checkpoint.CHECKPOINT_DIR", str(tmp_path)):
            path = mgr.save(layer=1, background=False)
        assert os.path.exists(path)
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        assert "story_draft" in data


# ---------------------------------------------------------------------------
# 4. Pipeline with invalid config (empty API key) → proper error message
# ---------------------------------------------------------------------------

class TestPipelineInvalidConfig:

    def setup_method(self):
        _reset_llm_singleton()

    def teardown_method(self):
        _reset_llm_singleton()

    @patch("services.llm_client.ConfigManager")
    @patch("services.llm_client.LLMCache")
    def test_empty_api_key_check_connection_returns_false(self, MockCache, MockCM):
        """check_connection returns (False, error_msg) when API key is empty."""
        from services.llm_client import LLMClient
        cfg = _make_llm_config(api_key="")
        MockCM.return_value = cfg
        client = LLMClient()

        mock_openai = MagicMock()
        mock_openai.chat.completions.create.side_effect = Exception("401 unauthorized invalid api key")
        client._get_client = MagicMock(return_value=mock_openai)

        ok, msg = client.check_connection()
        assert ok is False
        assert isinstance(msg, str)
        assert len(msg) > 0

    @patch("services.llm_client.ConfigManager")
    @patch("services.llm_client.LLMCache")
    def test_generate_with_401_does_not_retry_fallbacks(self, MockCache, MockCM):
        """Non-transient 401 auth error stops immediately without trying fallbacks."""
        from services.llm_client import LLMClient
        cfg = _make_llm_config(api_key="bad-key")
        MockCM.return_value = cfg
        MockCache.return_value.get.return_value = None

        client = LLMClient()

        primary = MagicMock()
        primary.chat.completions.create.side_effect = Exception("401 unauthorized")
        fallback = MagicMock()
        resp = MagicMock()
        resp.choices[0].message.content = "Should not reach here"
        fallback.chat.completions.create.return_value = resp

        client._build_fallback_chain = MagicMock(return_value=[
            {"client": primary, "model": "gpt-4", "label": "primary"},
            {"client": fallback, "model": "gpt-3.5", "label": "cheap"},
        ])

        with patch("services.prompts.localize_prompt", side_effect=lambda p, lang: p):
            with pytest.raises(Exception):
                client.generate("sys", "usr")

        fallback.chat.completions.create.assert_not_called()
