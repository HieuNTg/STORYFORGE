"""Sprint 2 — image work fans out at two levels, and nothing bounded the total.

The pipeline media stage already ran chapters concurrently; panels within a
chapter now do too. Neither worker count bounds the other, so they multiply: 4
chapters x 3 panels is 12 provider calls in flight, not 4, and no setting said
how many requests the provider was actually being asked to serve. Image
endpoints rate-limit far harder than text ones, so that number has to exist.

`pipeline.image_max_concurrent_requests` is it — one process-wide semaphore
held around the provider call itself, so workers above it queue instead of
piling onto the provider.

The Reader path, meanwhile, still looped chapters one at a time, so asking it
for a whole story's comic cost the sum of its chapters.
"""

import threading
import time
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from services.media.image_generator import (
    ImageGenerator,
    reset_image_request_semaphore,
)


@pytest.fixture(autouse=True)
def _clean_semaphore():
    reset_image_request_semaphore()
    yield
    reset_image_request_semaphore()


def _prompt(n: int):
    return SimpleNamespace(
        dalle_prompt=f"panel {n}",
        sd_prompt=f"panel {n}",
        scene_description=f"scene {n}",
        target_size="1024x1024",
        characters_in_scene=[],
    )


def _generator(panel_workers=8, ceiling=2, retries=0):
    gen = ImageGenerator.__new__(ImageGenerator)
    gen.provider = "dalle"
    cfg = SimpleNamespace(
        pipeline=SimpleNamespace(
            panel_retry_attempts=retries,
            comic_panel_workers=panel_workers,
            image_max_concurrent_requests=ceiling,
        )
    )
    return gen, patch("services.media.image_generator.ConfigManager", return_value=cfg)


class _Meter:
    def __init__(self, delay=0.04):
        self.delay = delay
        self.live = 0
        self.peak = 0
        self.lock = threading.Lock()

    def __call__(self, prompt, filename, size):
        with self.lock:
            self.live += 1
            self.peak = max(self.peak, self.live)
        time.sleep(self.delay)
        with self.lock:
            self.live -= 1
        return f"/img/{filename}"


class TestTheCeilingHolds:
    def test_more_workers_than_the_ceiling_still_respect_it(self):
        """8 panel workers, ceiling 2 — the provider must see 2."""
        gen, cfg = _generator(panel_workers=8, ceiling=2)
        meter = _Meter()
        gen.generate = meter
        with cfg:
            gen.generate_story_images([_prompt(i) for i in range(8)])
        assert meter.peak <= 2, f"{meter.peak} requests in flight against a ceiling of 2"

    def test_the_work_still_all_completes(self):
        gen, cfg = _generator(panel_workers=8, ceiling=2)
        gen.generate = _Meter()
        with cfg:
            paths = gen.generate_story_images([_prompt(i) for i in range(8)])
        assert len(paths) == 8

    def test_zero_disables_the_ceiling(self):
        """Operators must be able to opt out explicitly."""
        gen, cfg = _generator(panel_workers=6, ceiling=0)
        meter = _Meter()
        gen.generate = meter
        with cfg:
            gen.generate_story_images([_prompt(i) for i in range(6)])
        assert meter.peak > 2, "with no ceiling the worker count should govern"

    def test_it_is_shared_across_generators_not_per_instance(self):
        """Two chapters mean two callers; a per-instance limit would not bound them."""
        gen_a, cfg = _generator(panel_workers=4, ceiling=2)
        gen_b, _ = _generator(panel_workers=4, ceiling=2)
        meter = _Meter()
        gen_a.generate = meter
        gen_b.generate = meter

        with cfg:
            threads = [
                threading.Thread(
                    target=g.generate_story_images,
                    args=([_prompt(i) for i in range(4)],),
                )
                for g in (gen_a, gen_b)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        assert meter.peak <= 2, f"{meter.peak} in flight from two generators"

    def test_a_changed_setting_takes_effect_without_a_restart(self):
        gen, cfg = _generator(panel_workers=6, ceiling=1)
        meter = _Meter()
        gen.generate = meter
        with cfg:
            gen.generate_story_images([_prompt(i) for i in range(4)])
        assert meter.peak == 1

        gen2, cfg2 = _generator(panel_workers=6, ceiling=3)
        meter2 = _Meter()
        gen2.generate = meter2
        with cfg2:
            gen2.generate_story_images([_prompt(i) for i in range(6)])
        assert meter2.peak > 1, "the new, larger ceiling was not picked up"

    def test_a_retrying_panel_does_not_hold_a_slot_across_its_backoff(self):
        """Holding capacity while not calling the provider would starve siblings."""
        gen, cfg = _generator(panel_workers=4, ceiling=4, retries=2)
        calls: list = []
        lock = threading.Lock()

        def _gen(prompt, filename, size):
            with lock:
                calls.append(filename)
            return None if "panel01" in filename else f"/img/{filename}"

        gen.generate = _gen
        with cfg:
            gen.generate_story_images([_prompt(i) for i in range(2)])

        assert calls.count("ch00_panel01.png") == 3, "retries must still happen"


class TestConfigDefaults:
    def test_the_ceiling_has_a_real_default(self):
        from config.defaults import PipelineConfig

        assert PipelineConfig().image_max_concurrent_requests >= 1

    def test_chapter_workers_have_a_real_default(self):
        from config.defaults import PipelineConfig

        assert PipelineConfig().comic_chapter_workers >= 1

    def test_the_ceiling_is_not_larger_than_the_two_fan_outs_multiplied(self):
        """If it were, it would not be a ceiling at all."""
        from config.defaults import PipelineConfig

        cfg = PipelineConfig()
        assert (
            cfg.image_max_concurrent_requests
            <= cfg.comic_chapter_workers * cfg.comic_panel_workers
        )


class TestTheDeadPoolManagerIsGone:
    """It declared three named pools with caps and had no production caller."""

    def test_the_module_no_longer_exists(self):
        with pytest.raises(ImportError):
            import services.thread_pool_manager  # noqa: F401

    def test_the_implementation_no_longer_exists(self):
        with pytest.raises(ImportError):
            import services._thread_pool_impl  # noqa: F401
