"""Sprint 2 — the Reader turned a story into a comic one chapter at a time.

`handle_generate_images` looped `target_chapters` sequentially, so asking the
Reader for a whole story's comic cost the sum of its chapters, while the
pipeline media stage had been fanning the same work out across chapters all
along. The two entry points call one shared `generate_chapter_comic`, so there
was no reason for them to differ.

Two things must survive the change: the returned paths stay in chapter order
(completion order is not chapter order, and a shuffled gallery is a
regression), and one chapter failing must not cost the others their art.
"""

import os
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import services.handlers as handlers_mod


def _chapter(n: int):
    return SimpleNamespace(
        chapter_number=n,
        title=f"ch{n}",
        content="nội dung " * 20,
        summary="",
        images=[],
    )


def _orch(n_chapters: int):
    story = SimpleNamespace(chapters=[_chapter(i + 1) for i in range(n_chapters)])
    return SimpleNamespace(
        session_id="sid-test",
        output=SimpleNamespace(
            enhanced_story=story,
            story_draft=SimpleNamespace(title="T", characters=[]),
        ),
    )


@pytest.fixture
def _stub_env(monkeypatch, tmp_path):
    """Neutralise everything the handler touches except the chapter loop."""
    from config import ConfigManager

    monkeypatch.setattr(
        ConfigManager().pipeline, "comic_shot_list_enabled", False, raising=False
    )
    monkeypatch.setattr(
        "services.media.image_prompt_generator.ImagePromptGenerator.generate_from_chapter",
        lambda self, *a, **kw: [SimpleNamespace(panel_number=1)],
        raising=False,
    )
    sub = os.path.join("output", "t_sid-test", "images")
    os.makedirs(sub, exist_ok=True)
    return sub


def _run(orch, comic_impl, workers=4):
    from config import ConfigManager

    cfg = ConfigManager().pipeline
    with patch.object(cfg, "comic_chapter_workers", workers, create=True), patch(
        "services.media.comic_chapter.generate_chapter_comic", comic_impl
    ):
        return handlers_mod.handle_generate_images(orch, provider="none")


class TestChaptersRunConcurrently:
    def test_six_chapters_do_not_take_six_round_trips(self, _stub_env):
        sub = _stub_env

        def _slow(ch, **kw):
            time.sleep(0.1)
            return [os.path.join(sub, f"ch{ch.chapter_number:02d}_panel01.png")]

        started = time.monotonic()
        paths, _ = _run(_orch(6), _slow, workers=4)
        elapsed = time.monotonic() - started

        assert len(paths) == 6
        assert elapsed < 0.45, f"serial would take ~0.6s, took {elapsed:.2f}s"

    def test_worker_count_is_bounded_by_config(self, _stub_env):
        sub = _stub_env
        live = 0
        peak = 0
        lock = threading.Lock()

        def _meter(ch, **kw):
            nonlocal live, peak
            with lock:
                live += 1
                peak = max(peak, live)
            time.sleep(0.05)
            with lock:
                live -= 1
            return [os.path.join(sub, f"ch{ch.chapter_number:02d}_panel01.png")]

        _run(_orch(8), _meter, workers=2)
        assert peak <= 2, f"{peak} chapters ran at once against a limit of 2"

    def test_one_worker_still_works(self, _stub_env):
        sub = _stub_env
        paths, _ = _run(
            _orch(3),
            lambda ch, **kw: [
                os.path.join(sub, f"ch{ch.chapter_number:02d}_panel01.png")
            ],
            workers=1,
        )
        assert len(paths) == 3


class TestOrderAndIsolation:
    def test_paths_come_back_in_chapter_order(self, _stub_env):
        """Chapter 1 is slowest, yet must still lead the gallery."""
        sub = _stub_env

        def _staggered(ch, **kw):
            if ch.chapter_number == 1:
                time.sleep(0.15)
            return [os.path.join(sub, f"ch{ch.chapter_number:02d}_panel01.png")]

        paths, _ = _run(_orch(4), _staggered, workers=4)
        assert [os.path.basename(p) for p in paths] == [
            f"ch{i + 1:02d}_panel01.png" for i in range(4)
        ]

    def test_each_chapter_gets_its_own_images(self, _stub_env):
        sub = _stub_env
        orch = _orch(3)
        _run(
            orch,
            lambda ch, **kw: [
                os.path.join(sub, f"ch{ch.chapter_number:02d}_panel01.png")
            ],
        )
        for ch in orch.output.enhanced_story.chapters:
            assert ch.images == [
                f"t_sid-test/images/ch{ch.chapter_number:02d}_panel01.png"
            ]

    def test_a_failing_chapter_does_not_cost_the_others(self, _stub_env):
        sub = _stub_env

        def _flaky(ch, **kw):
            if ch.chapter_number == 2:
                raise RuntimeError("provider 500")
            return [os.path.join(sub, f"ch{ch.chapter_number:02d}_panel01.png")]

        orch = _orch(4)
        paths, _ = _run(orch, _flaky, workers=4)

        assert len(paths) == 3
        assert orch.output.enhanced_story.chapters[1].images == []
        assert orch.output.enhanced_story.chapters[2].images == [
            "t_sid-test/images/ch03_panel01.png"
        ]

    def test_a_chapter_with_no_art_is_skipped_not_blanked(self, _stub_env):
        sub = _stub_env
        orch = _orch(2)
        orch.output.enhanced_story.chapters[0].images = ["kept/from/before.png"]

        def _empty_for_one(ch, **kw):
            if ch.chapter_number == 1:
                return []
            return [os.path.join(sub, "ch02_panel01.png")]

        _run(orch, _empty_for_one)
        assert orch.output.enhanced_story.chapters[0].images == [
            "kept/from/before.png"
        ]
