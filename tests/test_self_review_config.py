"""Tests for self-review config integration."""
import copy
import json
from config import ConfigManager, PipelineConfig


class TestSelfReviewConfig:
    def test_default_values(self):
        pc = PipelineConfig()
        assert pc.enable_self_review is False
        assert pc.self_review_threshold == 3.0

    def test_threshold_range(self):
        pc = PipelineConfig(self_review_threshold=4.5)
        assert pc.self_review_threshold == 4.5

    def test_config_save_includes_self_review(self, tmp_path):
        import config.persistence as persistence_module
        original_config_file = persistence_module.CONFIG_FILE
        config_file = str(tmp_path / "config.json")
        persistence_module.CONFIG_FILE = config_file
        try:
            cfg = ConfigManager.__new__(ConfigManager)
            cfg._initialized = False
            cfg.llm = copy.deepcopy(ConfigManager().llm)
            cfg.llm.api_key = "test-key"
            cfg.pipeline = PipelineConfig(enable_self_review=True, self_review_threshold=4.0)
            cfg.save()
            with open(config_file) as f:
                data = json.load(f)
            assert data["pipeline"]["enable_self_review"] is True
            assert data["pipeline"]["self_review_threshold"] == 4.0
        finally:
            persistence_module.CONFIG_FILE = original_config_file
