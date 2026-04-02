"""Tests for media producer error recovery paths."""
from unittest.mock import MagicMock, patch


class TestMediaProducerErrorRecovery:
    def test_image_generation_failure_continues(self):
        """Pipeline continues when image generation fails for some panels."""
        from pipeline.orchestrator_media import MediaProducer
        from config import ConfigManager

        config = ConfigManager()
        producer = MediaProducer(config)

        mock_draft = MagicMock()
        mock_draft.characters = []
        mock_enhanced = MagicMock()
        mock_enhanced.chapters = []
        mock_script = MagicMock()
        mock_script.panels = [MagicMock(image_prompt="test", image_path="")]

        with patch.object(producer, 'config') as mock_cfg:
            mock_cfg.pipeline.seedream_api_key = ""
            mock_cfg.pipeline.seedream_api_url = ""
            mock_cfg.pipeline.enable_character_consistency = False
            # With no seedream configured, should skip image gen gracefully
            result = producer.run(mock_draft, mock_enhanced, mock_script)
            assert isinstance(result, dict)
            assert "character_refs" in result

    def test_empty_panels(self):
        """Media producer handles empty panel list."""
        from pipeline.orchestrator_media import MediaProducer
        from config import ConfigManager

        config = ConfigManager()
        producer = MediaProducer(config)

        mock_draft = MagicMock()
        mock_draft.characters = []
        mock_enhanced = MagicMock()
        mock_enhanced.chapters = []
        mock_script = MagicMock()
        mock_script.panels = []

        result = producer.run(mock_draft, mock_enhanced, mock_script,
                             progress_callback=lambda m: None)
        assert isinstance(result, dict)
        assert result["scene_images"] == []
        assert result["video_path"] == ""

    def test_returns_all_expected_keys(self):
        """Result dict contains all expected keys."""
        from pipeline.orchestrator_media import MediaProducer
        from config import ConfigManager

        config = ConfigManager()
        producer = MediaProducer(config)

        mock_draft = MagicMock()
        mock_draft.characters = []
        mock_enhanced = MagicMock()
        mock_enhanced.chapters = []
        mock_script = MagicMock()
        mock_script.panels = []

        result = producer.run(mock_draft, mock_enhanced, mock_script)
        for key in ["character_refs", "scene_images", "audio_paths", "video_path"]:
            assert key in result
