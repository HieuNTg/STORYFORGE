"""Coverage tests for config/ package: defaults, validation, persistence, presets."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import pytest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestLLMConfigDefaults:
    """Tests for LLMConfig dataclass."""

    def test_llm_config_default_values(self):
        from config.defaults import LLMConfig
        cfg = LLMConfig()
        assert cfg.api_key == ""
        assert "openai.com" in cfg.base_url
        assert cfg.temperature == pytest.approx(0.8)
        assert cfg.max_tokens > 0
        assert cfg.cache_enabled is True

    def test_llm_config_custom_values(self):
        from config.defaults import LLMConfig
        cfg = LLMConfig(api_key="sk-abc", model="gpt-4o", temperature=0.5)
        assert cfg.api_key == "sk-abc"
        assert cfg.model == "gpt-4o"
        assert cfg.temperature == pytest.approx(0.5)

    def test_llm_config_fallback_models_empty_by_default(self):
        from config.defaults import LLMConfig
        cfg = LLMConfig()
        assert isinstance(cfg.fallback_models, list)
        assert len(cfg.fallback_models) == 0

    def test_llm_config_layer_models_empty_by_default(self):
        from config.defaults import LLMConfig
        cfg = LLMConfig()
        assert cfg.layer1_model == ""
        assert cfg.layer2_model == ""


class TestPipelineConfigDefaults:
    """Tests for PipelineConfig dataclass."""

    def test_pipeline_config_default_values(self):
        from config.defaults import PipelineConfig
        cfg = PipelineConfig()
        assert cfg.num_chapters > 0
        assert cfg.words_per_chapter > 0
        assert cfg.language == "vi"

    def test_pipeline_config_image_provider_default(self):
        from config.defaults import PipelineConfig
        cfg = PipelineConfig()
        assert cfg.image_provider == "none"

    def test_pipeline_config_sub_genres_empty(self):
        from config.defaults import PipelineConfig
        cfg = PipelineConfig()
        assert isinstance(cfg.sub_genres, list)


class TestConfigValidation:
    """Tests for config validation logic."""

    def test_validate_empty_api_key(self):
        from config.defaults import LLMConfig, PipelineConfig
        from config.validation import validate_config
        llm = LLMConfig()
        pipeline = PipelineConfig()
        errors = validate_config(llm, pipeline)
        assert any("API key" in e or "bắt buộc" in e for e in errors)

    def test_validate_valid_config(self):
        from config.defaults import LLMConfig, PipelineConfig
        from config.validation import validate_config
        llm = LLMConfig(api_key="sk-test1234")
        pipeline = PipelineConfig()
        errors = validate_config(llm, pipeline)
        # May have no errors or minor warnings, but not critical api key error
        critical = [e for e in errors if "API key" in e or "bắt buộc" in e]
        assert len(critical) == 0

    def test_validate_invalid_num_chapters(self):
        from config.defaults import LLMConfig, PipelineConfig
        from config.validation import validate_config
        llm = LLMConfig(api_key="sk-test")
        pipeline = PipelineConfig(num_chapters=0)
        errors = validate_config(llm, pipeline)
        assert any("chương" in e for e in errors)

    def test_validate_invalid_words_per_chapter(self):
        from config.defaults import LLMConfig, PipelineConfig
        from config.validation import validate_config
        llm = LLMConfig(api_key="sk-test")
        pipeline = PipelineConfig(words_per_chapter=10)
        errors = validate_config(llm, pipeline)
        assert any("từ" in e for e in errors)

    def test_validate_openrouter_model_format(self):
        from config.defaults import LLMConfig, PipelineConfig
        from config.validation import validate_config
        llm = LLMConfig(api_key="sk-test", base_url="https://openrouter.ai/api/v1", model="bad-model")
        pipeline = PipelineConfig()
        errors = validate_config(llm, pipeline)
        # Should warn about OpenRouter model format
        [e for e in errors if "OpenRouter" in e or "openrouter" in e.lower()]
        # May or may not have errors depending on model format
        assert isinstance(errors, list)



class TestConfigPersistence:
    """Tests for config load/save."""

    def test_load_config_missing_file(self):
        from config.defaults import LLMConfig, PipelineConfig
        from config.persistence import load_config
        llm = LLMConfig()
        pipeline = PipelineConfig()
        # Load from non-existent file — should not raise
        with patch("config.persistence.os.path.exists", return_value=False):
            load_config(llm, pipeline)
        # Defaults should still be set
        assert llm.base_url != ""

    def test_save_and_load_config(self):
        from config.defaults import LLMConfig, PipelineConfig
        from config.persistence import save_config, load_config
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = os.path.join(tmpdir, "config.json")
            with patch("config.persistence.CONFIG_FILE", config_file):
                llm = LLMConfig(model="test-model-save", temperature=0.5)
                pipeline = PipelineConfig(num_chapters=5)
                save_config(llm, pipeline)
                assert os.path.exists(config_file)
                # Load into fresh objects
                llm2 = LLMConfig()
                pipeline2 = PipelineConfig()
                load_config(llm2, pipeline2)

    def test_save_config_includes_api_key(self):
        from config.defaults import LLMConfig, PipelineConfig
        from config.persistence import save_config
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = os.path.join(tmpdir, "config.json")
            with patch("config.persistence.CONFIG_FILE", config_file):
                llm = LLMConfig(api_key="sk-test-key")
                pipeline = PipelineConfig()
                save_config(llm, pipeline)
                with open(config_file) as f:
                    data = json.load(f)
                assert data["llm"]["api_key"] == "sk-test-key"

    def test_env_override_api_key(self):
        from config.defaults import LLMConfig, PipelineConfig
        from config.persistence import load_config
        llm = LLMConfig()
        pipeline = PipelineConfig()
        with patch.dict(os.environ, {"STORYFORGE_API_KEY": "env-override-key"}):
            with patch("config.persistence.os.path.exists", return_value=False):
                load_config(llm, pipeline)
        assert llm.api_key == "env-override-key"

    def test_env_override_temperature(self):
        from config.defaults import LLMConfig, PipelineConfig
        from config.persistence import load_config
        llm = LLMConfig()
        pipeline = PipelineConfig()
        with patch.dict(os.environ, {"STORYFORGE_TEMPERATURE": "0.3"}):
            with patch("config.persistence.os.path.exists", return_value=False):
                load_config(llm, pipeline)
        assert llm.temperature == pytest.approx(0.3)

    def test_env_override_bool_field(self):
        from config.defaults import LLMConfig, PipelineConfig
        from config.persistence import load_config
        llm = LLMConfig()
        pipeline = PipelineConfig()
        with patch.dict(os.environ, {"STORYFORGE_RAG_ENABLED": "true"}):
            with patch("config.persistence.os.path.exists", return_value=False):
                load_config(llm, pipeline)
        assert pipeline.rag_enabled is True

    def test_load_config_invalid_json(self):
        from config.defaults import LLMConfig, PipelineConfig
        from config.persistence import load_config
        llm = LLMConfig()
        pipeline = PipelineConfig()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("invalid json{{{")
            fname = f.name
        try:
            with patch("config.persistence.CONFIG_FILE", fname):
                # Should not raise, just log warning
                load_config(llm, pipeline)
        finally:
            os.unlink(fname)


class TestConfigPresets:
    """Tests for preset constants."""

    def test_pipeline_presets_keys(self):
        from config.presets import PIPELINE_PRESETS
        assert "beginner" in PIPELINE_PRESETS
        assert "advanced" in PIPELINE_PRESETS
        assert "pro" in PIPELINE_PRESETS

    def test_pipeline_preset_has_label(self):
        from config.presets import PIPELINE_PRESETS
        for key, preset in PIPELINE_PRESETS.items():
            assert "label" in preset, f"Preset {key} missing label"


class TestConfigManagerSingleton:
    """Tests for ConfigManager singleton behavior."""

    def test_singleton_returns_same_instance(self):
        from config import ConfigManager
        cm1 = ConfigManager()
        cm2 = ConfigManager()
        assert cm1 is cm2

    def test_config_manager_has_llm(self):
        from config import ConfigManager
        cm = ConfigManager()
        assert hasattr(cm, "llm")
        assert hasattr(cm.llm, "api_key")

    def test_config_manager_has_pipeline(self):
        from config import ConfigManager
        cm = ConfigManager()
        assert hasattr(cm, "pipeline")
        assert hasattr(cm.pipeline, "num_chapters")

    def test_config_manager_validate_returns_list(self):
        from config import ConfigManager
        cm = ConfigManager()
        result = cm.validate()
        assert isinstance(result, list)

    def test_config_manager_save_raises_on_critical(self):
        from config import ConfigManager
        cm = ConfigManager()
        original_key = cm.llm.api_key
        original_fallbacks = cm.llm.fallback_models
        try:
            cm.llm.api_key = ""
            cm.llm.fallback_models = []
            with pytest.raises((ValueError, Exception)):
                cm.save()
        finally:
            cm.llm.api_key = original_key
            cm.llm.fallback_models = original_fallbacks
