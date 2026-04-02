"""Tests for async video composition."""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock


class TestAsyncCompose:
    @pytest.mark.asyncio
    async def test_compose_async_no_panels(self):
        """Async compose returns None for empty panels."""
        from services.video_composer import VideoComposer
        composer = VideoComposer()
        result = await composer.compose_async(panels=[])
        assert result is None

    @pytest.mark.asyncio
    async def test_compose_async_no_valid_images(self):
        """Async compose returns None when no panel has valid image_path."""
        from services.video_composer import VideoComposer
        composer = VideoComposer()
        panels = [MagicMock(image_path="nonexistent.png")]
        with patch('os.path.exists', return_value=False):
            result = await composer.compose_async(panels=panels)
            assert result is None

    @pytest.mark.asyncio
    async def test_compose_async_process_killed_on_error(self):
        """Process is killed when general exception occurs."""
        from services.video_composer import VideoComposer
        composer = VideoComposer()

        mock_panel = MagicMock()
        mock_panel.image_path = "/tmp/test.png"
        mock_panel.duration_seconds = 5.0

        mock_process = AsyncMock()
        mock_process.returncode = None
        mock_process.stdout.readline = AsyncMock(side_effect=RuntimeError("boom"))
        mock_process.kill = MagicMock()
        mock_process.wait = AsyncMock()

        with patch('os.path.exists', return_value=True), \
             patch.object(composer, '_write_concat_file', return_value="/tmp/concat.txt"), \
             patch('asyncio.create_subprocess_exec', return_value=mock_process):
            result = await composer.compose_async(panels=[mock_panel])
            assert result is None
            mock_process.kill.assert_called_once()

    def test_timeout_scales_with_resolution(self):
        """FFmpeg timeout should increase for higher resolutions."""
        from services.video_composer import VideoComposer
        composer_1k = VideoComposer(resolution="1024x1024")
        composer_4k = VideoComposer(resolution="3840x2160")
        t_1k = composer_1k._calc_timeout(100)
        t_4k = composer_4k._calc_timeout(100)
        assert t_4k > t_1k

    def test_compose_returns_none_without_ffmpeg(self):
        """Compose returns None when FFmpeg is not installed."""
        from services.video_composer import VideoComposer
        composer = VideoComposer()
        mock_panel = MagicMock()
        mock_panel.image_path = "/tmp/test.png"
        mock_panel.duration_seconds = 5.0

        with patch('os.path.exists', return_value=True), \
             patch('subprocess.run', side_effect=FileNotFoundError("ffmpeg")):
            result = composer.compose(panels=[mock_panel])
            assert result is None
