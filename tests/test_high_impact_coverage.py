"""High-impact coverage tests targeting modules with most uncovered statements."""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ============================================================
# services/story_analytics.py — 101 statements at 0%
# ============================================================


class TestStoryAnalytics:
    """Tests for StoryAnalytics."""

    def _make_chapter(
        self, number=1, content="Hello world. This is a test. More text here."
    ):
        from models.schemas import Chapter

        return Chapter(
            chapter_number=number, title=f"Chapter {number}", content=content
        )

    def _make_story_draft(self, chapters=None):
        from models.schemas import StoryDraft

        if chapters is None:
            chapters = [self._make_chapter(1, "Hello world. A test chapter.")]
        return StoryDraft(title="Test", genre="Fantasy", chapters=chapters)

    def test_analyze_empty_story(self):
        from services.story_analytics import StoryAnalytics
        from models.schemas import StoryDraft

        story = StoryDraft(title="Empty", genre="Fantasy")
        result = StoryAnalytics.analyze_story(story)
        assert "error" in result

    def test_analyze_single_chapter(self):
        from services.story_analytics import StoryAnalytics

        story = self._make_story_draft()
        result = StoryAnalytics.analyze_story(story)
        assert "total_words" in result
        assert result["total_chapters"] == 1

    def test_analyze_multiple_chapters(self):
        from services.story_analytics import StoryAnalytics

        story = self._make_story_draft(
            [
                self._make_chapter(1, "First chapter content here. More words."),
                self._make_chapter(2, "Second chapter. Even more content."),
            ]
        )
        result = StoryAnalytics.analyze_story(story)
        assert result["total_chapters"] == 2
        assert result["total_words"] > 0

    def test_analyze_chapter_word_count(self):
        from services.story_analytics import StoryAnalytics

        chapter = self._make_chapter(1, "one two three four five")
        stats = StoryAnalytics.analyze_chapter(chapter)
        assert stats["word_count"] == 5

    def test_analyze_chapter_sentence_count(self):
        from services.story_analytics import StoryAnalytics

        chapter = self._make_chapter(1, "First sentence. Second sentence! Third?")
        stats = StoryAnalytics.analyze_chapter(chapter)
        assert stats["sentence_count"] >= 1

    def test_analyze_chapter_dialogue_detection(self):
        from services.story_analytics import StoryAnalytics

        chapter = self._make_chapter(
            1, '"Hello," he said. "World," she replied. Normal text.'
        )
        stats = StoryAnalytics.analyze_chapter(chapter)
        assert "dialogue_ratio" in stats

    def test_reading_time_positive(self):
        from services.story_analytics import StoryAnalytics

        story = self._make_story_draft(
            [self._make_chapter(1, " ".join(["word"] * 500))]
        )
        result = StoryAnalytics.analyze_story(story)
        assert result["reading_time_minutes"] >= 1

    def test_analyze_story_returns_pacing_data(self):
        from services.story_analytics import StoryAnalytics

        story = self._make_story_draft()
        result = StoryAnalytics.analyze_story(story)
        assert "pacing_data" in result
        assert "chapter_numbers" in result["pacing_data"]


# ============================================================
# services/security/input_sanitizer.py
# ============================================================


class TestInputSanitizer:
    def test_blank_input_is_safe_and_returned_unchanged(self):
        from services.security.input_sanitizer import sanitize_input

        for text in ("", "   "):
            result = sanitize_input(text)
            assert result.is_safe is True
            assert result.cleaned_text == text
            assert result.threats_found == []


# ============================================================
# errors/exceptions.py
# ============================================================


class TestExceptions:
    @pytest.mark.parametrize(
        ("factory", "message", "code"),
        [
            (lambda e: e.StoryForgeError("boom"), "boom", "INTERNAL_ERROR"),
            (lambda e: e.ConfigError("bad"), "bad", "CONFIG_ERROR"),
            (lambda e: e.LLMError("down"), "down", "LLM_ERROR"),
            (lambda e: e.LLMQuotaExhausted(), "LLM quota exhausted", "LLM_QUOTA_EXHAUSTED"),
            (
                lambda e: e.LLMQuotaExhausted("openai"),
                "LLM quota exhausted (openai)",
                "LLM_QUOTA_EXHAUSTED",
            ),
            (lambda e: e.LLMModelNotFound("gpt-x"), "Model not found: gpt-x", "LLM_MODEL_NOT_FOUND"),
            (lambda e: e.PipelineError("stuck"), "stuck", "PIPELINE_ERROR"),
            (
                lambda e: e.InputSanitizationError(["sql", "xss"]),
                "Input blocked: sql, xss",
                "INPUT_BLOCKED",
            ),
            (lambda e: e.ExportError("no pdf"), "no pdf", "EXPORT_ERROR"),
            (lambda e: e.StorageError("disk"), "disk", "STORAGE_ERROR"),
        ],
    )
    def test_message_and_code(self, factory, message, code):
        import errors.exceptions as exc_mod

        err = factory(exc_mod)
        assert isinstance(err, exc_mod.StoryForgeError)
        assert (err.message, err.code, str(err)) == (message, code, message)

    def test_input_sanitization_error_keeps_the_threats(self):
        from errors.exceptions import InputSanitizationError

        assert InputSanitizationError(["sql"]).threats == ["sql"]


# ============================================================
# services/prompt_registry.py
# ============================================================


class TestPromptRegistry:
    @pytest.fixture
    def prompts_dir(self, tmp_path, monkeypatch):
        import services.prompt_registry as reg

        files = {
            "agent_prompts.yaml": [
                "_meta:",
                "  version: '2.1'",
                "  updated_at: '2026-01-01'",
                "  description: current",
                "  changelog: [first]",
                "critic: 'Review {content}'",
                "editor: 'Edit {content}'",
            ],
            "old.yaml": ["_meta:", "  version: '1.0'", "critic: 'Old {content}'"],
            "no_meta.yaml": ["critic: 'x'"],
        }
        for name, lines in files.items():
            (tmp_path / name).write_text("\n".join(lines) + "\n", encoding="utf-8")
        monkeypatch.setattr(reg, "_PROMPTS_DIR", tmp_path)
        monkeypatch.delenv("STORYFORGE_PROMPTS_FILE", raising=False)
        return tmp_path

    def test_get_prompt_version_reads_meta(self, prompts_dir):
        from services.prompt_registry import get_prompt_version

        assert get_prompt_version() == {
            "version": "2.1",
            "updated_at": "2026-01-01",
            "description": "current",
            "changelog": ["first"],
            "file": str(prompts_dir / "agent_prompts.yaml"),
        }

    def test_get_prompt_version_without_a_file_is_unknown(self, tmp_path, monkeypatch):
        import services.prompt_registry as reg

        monkeypatch.setattr(reg, "_PROMPTS_DIR", tmp_path)
        assert reg.get_prompt_version()["version"] == "unknown"

    def test_list_prompt_versions_skips_files_without_meta(self, prompts_dir):
        from services.prompt_registry import list_prompt_versions

        versions = {v["file"]: v for v in list_prompt_versions()}

        assert set(versions) == {"agent_prompts.yaml", "old.yaml"}
        assert versions["agent_prompts.yaml"]["is_active"] is True
        assert versions["agent_prompts.yaml"]["prompt_count"] == 2
        assert versions["old.yaml"]["is_active"] is False
        assert versions["old.yaml"]["version"] == "1.0"

    def test_get_active_prompts_excludes_meta(self, prompts_dir):
        from services.prompt_registry import get_active_prompts

        assert get_active_prompts() == {
            "critic": "Review {content}",
            "editor": "Edit {content}",
        }


# ============================================================
# pipeline/agents/base_agent.py — 55 statements at 0%
# ============================================================


class TestBaseAgent:
    """Tests for base agent."""

    def test_base_agent_is_abstract(self):
        import inspect
        from pipeline.agents.base_agent import BaseAgent

        assert inspect.isabstract(BaseAgent)


# ============================================================
# config/presets.py - additional tests
# ============================================================


class TestMorePresets:
    """Additional preset tests."""

    def test_provider_presets_structure(self):
        # Single source of truth for the Settings "Quick provider" cards.
        # The frontend renders these verbatim, so every entry must carry the
        # full shape (name/label/base_url/model/models[]/placeholder).
        from config import PROVIDER_PRESETS

        assert isinstance(PROVIDER_PRESETS, list)
        assert len(PROVIDER_PRESETS) > 0
        required = {"name", "label", "base_url", "model", "models", "placeholder"}
        for preset in PROVIDER_PRESETS:
            missing = required - preset.keys()
            assert not missing, (
                f"Provider preset {preset.get('name')} missing {missing}"
            )
            assert isinstance(preset["models"], list)
            # The free-form card (`custom: True`) is the one entry with no fixed
            # provider and therefore no model dropdown — the user types both.
            # Every other card must still offer models, or its dropdown renders
            # empty in Settings.
            if not preset.get("custom"):
                assert preset["models"], (
                    f"Provider preset {preset['name']} has no models"
                )
            for m in preset["models"]:
                assert "id" in m and "label" in m, (
                    f"Model entry in {preset['name']} missing id/label"
                )

    def test_no_preset_prefills_a_key(self):
        # `default_key` used to prefill the Settings key box for a local web
        # bridge with a shared token. No preset may ship a key in the repo.
        from config import PROVIDER_PRESETS

        for preset in PROVIDER_PRESETS:
            assert "default_key" not in preset, (
                f"Provider preset {preset['name']} prefills a key"
            )
