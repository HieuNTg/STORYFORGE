"""Sprint 2 — a chapter's panels are independent, but were generated in a queue.

`generate_story_images` walked its prompts one at a time, so a 20-panel chapter
paid 20 serial image round-trips before a single page could be composed. Each
panel is one provider call producing one file; nothing links them.

Order is the hazard. The page compositor slices this list *positionally*, and
completion order is not panel order, so results must land by index rather than
by append — the same class of bug as the earlier dropped-panel shift, which is
what `keep_positions` exists to prevent.
"""

import threading
import time
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from services.media.image_generator import ImageGenerator


def _prompt(n: int):
    return SimpleNamespace(
        dalle_prompt=f"panel {n}",
        sd_prompt=f"panel {n}",
        scene_description=f"scene {n}",
        target_size="1024x1024",
        characters_in_scene=[],
    )


def _generator(workers: int = 3, retries: int = 0):
    gen = ImageGenerator.__new__(ImageGenerator)
    gen.provider = "dalle"
    cfg = SimpleNamespace(
        pipeline=SimpleNamespace(
            panel_retry_attempts=retries, comic_panel_workers=workers
        )
    )
    return gen, patch("services.media.image_generator.ConfigManager", return_value=cfg)


class TestPanelsRunConcurrently:
    def test_ten_panels_do_not_take_ten_round_trips(self):
        gen, cfg = _generator(workers=5)
        gen.generate = lambda prompt, filename, size: (
            time.sleep(0.1) or f"/img/{filename}"
        )

        with cfg:
            started = time.monotonic()
            paths = gen.generate_story_images([_prompt(i) for i in range(10)])
            elapsed = time.monotonic() - started

        assert len(paths) == 10
        assert elapsed < 0.6, f"serial would take ~1.0s, took {elapsed:.2f}s"

    def test_worker_count_is_bounded_by_config(self):
        """Image endpoints rate-limit hard; an unbounded fan-out is a new bug."""
        live = 0
        peak = 0
        lock = threading.Lock()
        gen, cfg = _generator(workers=2)

        def _slow(prompt, filename, size):
            nonlocal live, peak
            with lock:
                live += 1
                peak = max(peak, live)
            time.sleep(0.05)
            with lock:
                live -= 1
            return f"/img/{filename}"

        gen.generate = _slow
        with cfg:
            gen.generate_story_images([_prompt(i) for i in range(8)])

        assert peak <= 2, f"{peak} panels ran at once against a limit of 2"

    def test_one_worker_still_works(self):
        """Operators must be able to put it back to fully serial."""
        gen, cfg = _generator(workers=1)
        gen.generate = lambda prompt, filename, size: f"/img/{filename}"
        with cfg:
            paths = gen.generate_story_images([_prompt(i) for i in range(3)])
        assert len(paths) == 3


class TestOrderSurvivesConcurrency:
    def _staggered(self, gen):
        """Panel 1 is slowest, so completion order is not panel order."""

        def _gen(prompt, filename, size):
            if "panel01" in filename:
                time.sleep(0.15)
            return f"/img/{filename}"

        gen.generate = _gen

    def test_results_are_in_panel_order_not_completion_order(self):
        gen, cfg = _generator(workers=4)
        self._staggered(gen)
        with cfg:
            paths = gen.generate_story_images([_prompt(i) for i in range(4)])
        assert paths == [f"/img/ch00_panel{i + 1:02d}.png" for i in range(4)]

    def test_keep_positions_holds_the_slot_of_a_failed_panel(self):
        gen, cfg = _generator(workers=4)
        gen.generate = lambda prompt, filename, size: (
            None if "panel02" in filename else f"/img/{filename}"
        )
        with cfg:
            paths = gen.generate_story_images(
                [_prompt(i) for i in range(4)], keep_positions=True
            )

        assert paths[1] is None
        assert paths[2] == "/img/ch00_panel03.png", "later panels must not shift"
        assert len(paths) == 4

    def test_without_keep_positions_failures_are_dropped(self):
        gen, cfg = _generator(workers=4)
        gen.generate = lambda prompt, filename, size: (
            None if "panel02" in filename else f"/img/{filename}"
        )
        with cfg:
            paths = gen.generate_story_images([_prompt(i) for i in range(4)])

        assert paths == [
            "/img/ch00_panel01.png",
            "/img/ch00_panel03.png",
            "/img/ch00_panel04.png",
        ]


class TestFailuresStayContained:
    def test_a_raising_panel_does_not_lose_the_others(self):
        gen, cfg = _generator(workers=4)

        def _gen(prompt, filename, size):
            if "panel02" in filename:
                raise RuntimeError("provider 500")
            return f"/img/{filename}"

        gen.generate = _gen
        with cfg:
            paths = gen.generate_story_images(
                [_prompt(i) for i in range(4)], keep_positions=True
            )

        assert paths[1] is None
        assert [p for p in paths if p] == [
            "/img/ch00_panel01.png",
            "/img/ch00_panel03.png",
            "/img/ch00_panel04.png",
        ]

    def test_retries_are_still_per_panel(self):
        gen, cfg = _generator(workers=4, retries=2)
        calls: list = []
        lock = threading.Lock()

        def _gen(prompt, filename, size):
            with lock:
                calls.append(filename)
            return None if "panel01" in filename else f"/img/{filename}"

        gen.generate = _gen
        with cfg:
            gen.generate_story_images([_prompt(i) for i in range(2)])

        assert calls.count("ch00_panel01.png") == 3, "1 attempt + 2 retries"
        assert calls.count("ch00_panel02.png") == 1

    def test_an_empty_prompt_list_is_not_an_error(self):
        gen, cfg = _generator()
        with cfg:
            assert gen.generate_story_images([]) == []


class TestConfigDefault:
    def test_the_worker_count_has_a_real_default(self):
        from config.defaults import PipelineConfig

        assert PipelineConfig().comic_panel_workers >= 1

    def test_it_is_conservative_enough_for_image_endpoints(self):
        from config.defaults import PipelineConfig

        assert PipelineConfig().comic_panel_workers <= 6


@pytest.mark.parametrize("workers", [1, 2, 5])
def test_output_is_identical_whatever_the_worker_count(workers):
    """Concurrency is a scheduling change; the artefact must not vary."""
    gen, cfg = _generator(workers=workers)
    gen.generate = lambda prompt, filename, size: f"/img/{filename}"
    with cfg:
        paths = gen.generate_story_images([_prompt(i) for i in range(6)])
    assert paths == [f"/img/ch00_panel{i + 1:02d}.png" for i in range(6)]
