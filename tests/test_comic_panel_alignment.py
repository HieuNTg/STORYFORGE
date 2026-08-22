"""Regression tests: one failed panel must not corrupt the rest of the chapter.

`generate_story_images` appended only successful paths, so a failure shortened
the list. `compose_chapter` slices that list positionally, `len(page.panels)` at
a time — so a single failed panel shifted every later panel into the wrong cell
and onto the wrong page, putting speech balloons over the wrong art for the rest
of the chapter. Nothing reported it.
"""

from unittest.mock import MagicMock, patch

from models.schemas import ImagePrompt
from services.media.image_generator import ImageGenerator


def _generator():
    gen = ImageGenerator.__new__(ImageGenerator)
    gen.provider = "dalle"
    gen.api_key = "k"
    gen.output_dir = "output/images"
    return gen


def _prompts(n):
    return [ImagePrompt(scene_description=f"cảnh {i}") for i in range(n)]


class TestPositionPreservingGeneration:
    def test_failed_panel_holds_its_slot(self):
        gen = _generator()
        # Panel 3 of 5 fails on every attempt.
        results = ["p1.png", "p2.png", None, "p4.png", "p5.png"]
        calls = iter(results)

        def fake_generate(prompt, filename, size=None):
            try:
                return next(calls)
            except StopIteration:
                return None

        with patch.object(ImageGenerator, "generate", side_effect=fake_generate):
            with patch(
                "services.media.image_generator.ConfigManager"
            ) as cfg:
                cfg.return_value.pipeline.panel_retry_attempts = 0
                paths = gen.generate_story_images(
                    _prompts(5), chapter_number=1, keep_positions=True
                )

        assert len(paths) == 5, "a hole was closed up, shifting later panels"
        assert paths[2] is None
        assert paths[3] == "p4.png", "panel 4 must stay at index 3"

    def test_default_contract_still_drops_failures(self):
        """Callers that only want URLs keep the old behaviour."""
        gen = _generator()
        calls = iter(["p1.png", None, "p3.png"])

        def fake_generate(prompt, filename, size=None):
            try:
                return next(calls)
            except StopIteration:
                return None

        with patch.object(ImageGenerator, "generate", side_effect=fake_generate):
            with patch(
                "services.media.image_generator.ConfigManager"
            ) as cfg:
                cfg.return_value.pipeline.panel_retry_attempts = 0
                paths = gen.generate_story_images(_prompts(3), chapter_number=1)

        assert paths == ["p1.png", "p3.png"]
        assert None not in paths


class TestCompositorHandlesHoles:
    def test_missing_panel_draws_a_placeholder_and_keeps_alignment(self, tmp_path):
        from PIL import Image
        from services.media.page_compositor import _place_panel

        canvas = Image.new("RGB", (200, 200), (255, 255, 255))
        draw = MagicMock()

        # Must not raise, and must not need a real file.
        _place_panel(canvas, draw, None, (0, 0, 100, 100), 2)

        assert draw.rectangle.called

    def test_page_of_only_missing_panels_is_skipped(self):
        from services.media.page_compositor import compose_chapter

        page = MagicMock()
        page.panels = [MagicMock(), MagicMock()]
        page.page = 1

        with patch(
            "services.media.page_compositor._coerce_pages", return_value=[page]
        ), patch("services.media.page_compositor.compose_page") as compose_page:
            out = compose_chapter(MagicMock(), [None, None], "out", chapter_number=1)

        assert out == []
        compose_page.assert_not_called()

    def test_page_with_one_missing_panel_is_still_composed(self):
        from services.media.page_compositor import compose_chapter

        page = MagicMock()
        page.panels = [MagicMock(), MagicMock()]
        page.page = 1

        with patch(
            "services.media.page_compositor._coerce_pages", return_value=[page]
        ), patch("services.media.page_compositor.compose_page") as compose_page:
            compose_chapter(MagicMock(), ["a.png", None], "out", chapter_number=1)

        compose_page.assert_called_once()
        # The hole is passed through so the second cell stays the second cell.
        assert compose_page.call_args[0][1] == ["a.png", None]
