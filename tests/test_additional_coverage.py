"""Additional coverage tests for secret_manager, token_counter, story_analytics."""

from __future__ import annotations

import os
import sys
import pytest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ============================================================
# services/secret_manager.py — 82 statements, 18%
# ============================================================


from cryptography.fernet import Fernet as _Fernet  # noqa: E402

_FK = _Fernet.generate_key().decode()


class TestSecretManager:
    """Tests for secret manager encryption/decryption."""

    def test_is_sensitive_api_key(self):
        from services.secret_manager import _is_sensitive

        assert _is_sensitive("api_key") is True
        assert _is_sensitive("API_KEY") is True

    def test_is_sensitive_token(self):
        from services.secret_manager import _is_sensitive

        assert _is_sensitive("hf_token") is True
        assert _is_sensitive("access_token") is True

    def test_is_sensitive_password(self):
        from services.secret_manager import _is_sensitive

        assert _is_sensitive("password") is True
        assert _is_sensitive("db_password") is True

    def test_is_sensitive_non_sensitive(self):
        from services.secret_manager import _is_sensitive

        assert _is_sensitive("model") is False
        assert _is_sensitive("base_url") is False
        assert _is_sensitive("temperature") is False

    def test_encrypt_value_no_env_key_still_encrypts(self):
        """Without STORYFORGE_SECRET_KEY the auto-generated key is used."""
        from services.secret_manager import encrypt_value

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("STORYFORGE_SECRET_KEY", None)
            result = encrypt_value("my-secret")
        assert result.startswith("ENC:")

    def test_encrypt_value_empty_string(self):
        from services.secret_manager import encrypt_value

        result = encrypt_value("")
        assert result == ""

    def test_encrypt_decrypt_roundtrip(self):
        from services.secret_manager import encrypt_value, decrypt_value

        with patch.dict(os.environ, {"STORYFORGE_SECRET_KEY": _FK}):
            encrypted = encrypt_value("my-secret-value")
            assert encrypted.startswith("ENC:")
            decrypted = decrypt_value(encrypted)
            assert decrypted == "my-secret-value"

    def test_decrypt_plaintext_passthrough(self):
        """decrypt_value returns plaintext unchanged if not ENC: prefixed."""
        from services.secret_manager import decrypt_value

        result = decrypt_value("plain-text-value")
        assert result == "plain-text-value"

    def test_encrypt_sensitive_fields(self):
        from services.secret_manager import encrypt_sensitive_fields

        with patch.dict(os.environ, {"STORYFORGE_SECRET_KEY": _FK}):
            data = {"api_key": "sk-test", "model": "gpt-4o", "token": "hf-token"}
            result = encrypt_sensitive_fields(data)
            assert result["api_key"].startswith("ENC:")
            assert result["token"].startswith("ENC:")
            assert result["model"] == "gpt-4o"  # non-sensitive unchanged

    def test_decrypt_sensitive_fields(self):
        from services.secret_manager import (
            encrypt_sensitive_fields,
            decrypt_sensitive_fields,
        )

        with patch.dict(os.environ, {"STORYFORGE_SECRET_KEY": _FK}):
            original = {"api_key": "sk-test-123", "model": "gpt-4o"}
            encrypted = encrypt_sensitive_fields(original)
            decrypted = decrypt_sensitive_fields(encrypted)
            assert decrypted["api_key"] == "sk-test-123"
            assert decrypted["model"] == "gpt-4o"


# ============================================================
# services/token_counter.py — 38 statements, 46%
# ============================================================


class TestTokenCounter:
    """Tests for token counter utility."""

    def test_detect_script_ratio_pure_latin(self):
        from services.token_counter import _detect_script_ratio

        ratio = _detect_script_ratio("Hello world")
        assert ratio == pytest.approx(0.0)

    def test_detect_script_ratio_vietnamese(self):
        from services.token_counter import _detect_script_ratio

        ratio = _detect_script_ratio("Xin chào thế giới")
        assert ratio > 0.0

    def test_detect_script_ratio_empty(self):
        from services.token_counter import _detect_script_ratio

        ratio = _detect_script_ratio("")
        assert ratio == pytest.approx(0.0)

    def test_detect_script_ratio_spaces_only(self):
        from services.token_counter import _detect_script_ratio

        ratio = _detect_script_ratio("   ")
        assert ratio == pytest.approx(0.0)

    def test_is_vietnamese_or_cjk_ascii(self):
        from services.token_counter import _is_vietnamese_or_cjk

        assert _is_vietnamese_or_cjk("a") is False
        assert _is_vietnamese_or_cjk("Z") is False
        assert _is_vietnamese_or_cjk("5") is False

    def test_is_vietnamese_or_cjk_vietnamese(self):
        from services.token_counter import _is_vietnamese_or_cjk

        # Vietnamese characters are non-ASCII
        assert _is_vietnamese_or_cjk("à") is True
        assert _is_vietnamese_or_cjk("ê") is True

    def test_estimate_tokens_english(self):
        from services.token_counter import estimate_tokens

        count = estimate_tokens("Hello world this is a test")
        assert count > 0
        assert count <= 20  # reasonable for 6 words

    def test_estimate_tokens_empty(self):
        from services.token_counter import estimate_tokens

        count = estimate_tokens("")
        assert count == 0

    def test_estimate_tokens_long_text(self):
        from services.token_counter import estimate_tokens

        text = "word " * 100
        count = estimate_tokens(text)
        assert count > 50  # reasonable estimate

    def test_estimate_tokens_vietnamese(self):
        from services.token_counter import estimate_tokens

        # Vietnamese text should have higher token count per character
        text = "Xin chào thế giới"
        count = estimate_tokens(text)
        assert count > 0

    def test_fits_in_context_short_texts(self):
        from services.token_counter import fits_in_context

        texts = ["Hello", "World"]
        result = fits_in_context(texts, max_tokens=10000)
        assert result is True

    def test_fits_in_context_too_long(self):
        from services.token_counter import fits_in_context

        texts = ["A " * 5000]  # very long text
        result = fits_in_context(texts, max_tokens=100)
        assert result is False


# ============================================================
# services/story_analytics.py — remaining uncovered lines 157-227
# ============================================================


class TestStoryAnalyticsExtended:
    """Additional tests for story analytics to cover remaining lines."""

    def _make_enhanced_story(self, chapters=None):
        from models.schemas import EnhancedStory, Chapter

        if chapters is None:
            chapters = [Chapter(chapter_number=1, title="Ch1", content="Content")]
        return EnhancedStory(title="Test", genre="Fantasy", chapters=chapters)

    def test_analyze_enhanced_story(self):
        from services.story_analytics import StoryAnalytics

        story = self._make_enhanced_story()
        result = StoryAnalytics.analyze_story(story)
        assert "total_words" in result

    def test_paragraph_count(self):
        from services.story_analytics import StoryAnalytics
        from models.schemas import Chapter

        content = "Para 1.\n\nPara 2.\n\nPara 3."
        chapter = Chapter(chapter_number=1, title="Ch1", content=content)
        stats = StoryAnalytics.analyze_chapter(chapter)
        assert stats.get("paragraph_count", 0) >= 1

    def test_analyze_story_with_multiple_chapters(self):
        from services.story_analytics import StoryAnalytics
        from models.schemas import StoryDraft, Chapter

        chapters = [
            Chapter(
                chapter_number=i, title=f"Ch{i}", content=f"Chapter {i} content. " * 10
            )
            for i in range(1, 5)
        ]
        story = StoryDraft(title="Multi", genre="Fantasy", chapters=chapters)
        result = StoryAnalytics.analyze_story(story)
        assert result["total_chapters"] == 4
        assert result["avg_words_per_chapter"] > 0

    def test_pacing_data_structure(self):
        from services.story_analytics import StoryAnalytics
        from models.schemas import StoryDraft, Chapter

        chapters = [
            Chapter(chapter_number=1, title="Ch1", content="Short content"),
            Chapter(
                chapter_number=2,
                title="Ch2",
                content="Longer content here with more words",
            ),
        ]
        story = StoryDraft(title="Test", genre="Fantasy", chapters=chapters)
        result = StoryAnalytics.analyze_story(story)
        pacing = result["pacing_data"]
        assert len(pacing["chapter_numbers"]) == 2
        assert len(pacing["word_counts"]) == 2


# ============================================================
# services/tts/voice_manager.py — 61 statements, 16%
# ============================================================


class TestVoiceManager:
    """Tests for TTS voice manager mixin — removed after product pivot (video/TTS dropped)."""

    def test_tts_removed(self):
        """TTS module was removed in sprint 8 product pivot."""
        import importlib

        assert importlib.util.find_spec("services.tts") is None


# ============================================================
# services/pipeline/branch_narrative.py — 80 statements, 27%
# ============================================================


class TestBranchNarrative:
    """Tests for branch narrative service."""

    def test_public_node_helper(self):
        from services.pipeline.branch_narrative import _public_node

        node = {
            "id": "node-1",
            "text": "Chapter text",
            "choices": [],
            "parent": None,
            "children": {},
        }
        result = _public_node(node)
        assert isinstance(result, dict)
        assert result["id"] == "node-1"

    def test_depth_helper_root(self):
        from services.pipeline.branch_narrative import _depth

        node = {"id": "root", "parent": None, "children": {}}
        depth = _depth(node)
        assert depth == 0

    def test_depth_helper_child(self):
        from services.pipeline.branch_narrative import _depth

        node = {"id": "child", "parent": "root-id", "children": {}}
        depth = _depth(node)
        assert depth == 1
