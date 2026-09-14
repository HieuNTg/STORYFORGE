"""Sprint 2 — one chapter was split and scored up to four times.

`enhance_chapter_by_scenes` decomposes the chapter into scenes and scores each
one before it enhances anything: one decompose call plus one cheap call per
scene. A single chapter pipeline calls it four times — the first enhancement,
the contract retry, the voice retry, and the structural re-enhance — and the
retries run it against text they did not change, so every run after the first
re-derives a result already known.

Instance memoisation could not have helped: each retry constructs a *fresh*
SceneEnhancer, so the memo has to outlive the instance. It is keyed on the
chapter text, so a chapter that genuinely changed is prepared again.

The per-scene scoring itself was also strictly serial against independent
scenes, which set the floor on how fast any of this could be.
"""

import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from models.schemas import Chapter
from pipeline.layer2_enhance.scene_enhancer import (
    SceneEnhancer,
    reset_scene_prep_cache,
)


SCENES = [
    {"scene_number": 1, "content": "Cảnh một. " * 30},
    {"scene_number": 2, "content": "Cảnh hai. " * 30},
    {"scene_number": 3, "content": "Cảnh ba. " * 30},
]


@pytest.fixture(autouse=True)
def _clean_cache():
    reset_scene_prep_cache()
    yield
    reset_scene_prep_cache()


def _enhancer(score_delay: float = 0.0):
    with patch("pipeline.layer2_enhance.scene_enhancer.LLMClient"):
        se = SceneEnhancer()
    se.parallel_enabled = False
    llm = MagicMock()

    def _json(*a, **k):
        if score_delay:
            time.sleep(score_delay)
        return {"drama_score": 0.9, "weak_points": [], "strong_points": []}

    llm.generate_json.side_effect = _json
    se.llm = llm
    se.decompose_chapter_content = MagicMock(return_value=list(SCENES))
    return se


def _chapter(content="Nội dung chương. " * 50, number=1):
    return Chapter(
        chapter_number=number,
        title="Chương thử",
        content=content,
        word_count=len(content.split()),
    )


def _prepare(se, chapter, genre="trinh thám", min_drama=0.6):
    return se._prepare_scenes(chapter, None, genre, "Không có", min_drama)


class TestPreparationIsReusedAcrossEnhancerInstances:
    def test_a_second_preparation_of_the_same_text_costs_nothing(self):
        """The retries build their own enhancer; the memo must outlive it."""
        first = _enhancer()
        _prepare(first, _chapter())
        assert first.llm.generate_json.call_count == 3

        second = _enhancer()
        _prepare(second, _chapter())
        assert second.llm.generate_json.call_count == 0
        assert second.decompose_chapter_content.call_count == 0

    def test_the_reused_result_is_the_same(self):
        first = _enhancer()
        scenes_a, scores_a = _prepare(first, _chapter())
        scenes_b, scores_b = _prepare(_enhancer(), _chapter())

        assert [s["scene_number"] for s in scenes_b] == [
            s["scene_number"] for s in scenes_a
        ]
        assert [s.drama_score for s in scores_b] == [s.drama_score for s in scores_a]

    def test_changed_text_is_prepared_again(self):
        """Reusing a stale split would enhance scenes the chapter no longer has."""
        _prepare(_enhancer(), _chapter("Bản gốc. " * 40))
        second = _enhancer()
        _prepare(second, _chapter("Bản đã sửa hoàn toàn khác. " * 40))
        assert second.llm.generate_json.call_count == 3

    def test_a_different_threshold_is_prepared_again(self):
        """needs_enhancement is derived from the threshold, so it is part of the key."""
        _prepare(_enhancer(), _chapter(), min_drama=0.6)
        second = _enhancer()
        _prepare(second, _chapter(), min_drama=0.85)
        assert second.llm.generate_json.call_count == 3

    def test_the_caller_cannot_corrupt_the_cache(self):
        """Handing out the stored lists would let one caller mutate another's."""
        scenes, scores = _prepare(_enhancer(), _chapter())
        scenes.clear()
        scores.clear()

        scenes_again, scores_again = _prepare(_enhancer(), _chapter())
        assert len(scenes_again) == 3
        assert len(scores_again) == 3


class TestConcurrentCallersCollapse:
    def test_two_threads_on_one_chapter_prepare_it_once(self):
        se = _enhancer(score_delay=0.05)
        chapter = _chapter()
        barrier = threading.Barrier(2)

        def run():
            barrier.wait()
            _prepare(se, chapter)

        threads = [threading.Thread(target=run) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert se.decompose_chapter_content.call_count == 1
        assert se.llm.generate_json.call_count == 3


class TestScoringRunsConcurrently:
    def test_scenes_are_not_scored_one_after_another(self):
        se = _enhancer(score_delay=0.12)
        se._scene_score_workers = staticmethod(lambda: 3)

        started = time.monotonic()
        se.score_scenes(SCENES, "trinh thám")
        elapsed = time.monotonic() - started

        assert elapsed < 0.28, f"serial would take ~0.36s, took {elapsed:.2f}s"

    def test_scores_stay_in_scene_order(self):
        se = _enhancer()

        def _staggered(*a, **k):
            # Scene 1 is slowest, yet must still come back first.
            if "Cảnh một" in k.get("user_prompt", ""):
                time.sleep(0.12)
                return {"drama_score": 0.1}
            return {"drama_score": 0.9}

        se.llm.generate_json.side_effect = _staggered
        scores = se.score_scenes(SCENES, "trinh thám")

        assert [s.scene_number for s in scores] == [1, 2, 3]
        assert scores[0].drama_score == pytest.approx(0.1)

    def test_a_failed_scene_leaves_the_others_scored(self):
        se = _enhancer()

        def _flaky(*a, **k):
            if "Cảnh hai" in k.get("user_prompt", ""):
                raise RuntimeError("provider 503")
            return {"drama_score": 0.9}

        se.llm.generate_json.side_effect = _flaky
        scores = se.score_scenes(SCENES, "trinh thám")

        assert len(scores) == 3
        assert scores[1].needs_enhancement is False, "a judge failure must not"
        assert scores[0].drama_score == pytest.approx(0.9)

    def test_an_empty_scene_list_is_not_an_error(self):
        assert _enhancer().score_scenes([], "trinh thám") == []

    def test_worker_count_comes_from_config(self):
        cfg = SimpleNamespace(llm=SimpleNamespace(max_parallel_workers=7))
        with patch("config.ConfigManager", return_value=cfg):
            assert SceneEnhancer._scene_score_workers() == 7
