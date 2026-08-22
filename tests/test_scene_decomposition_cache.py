"""Sprint 2 — a chapter must not be decomposed into scenes twice.

Both the sequential write path (`scene_write_prep`) and the enhancement-context
builder call `decompose_chapter_scenes` for the same chapter, gated on the same
`enable_scene_decomposition` flag. Every chapter therefore paid for two
identical LLM calls whenever the flag was on.
"""

import threading
from unittest.mock import MagicMock

from models.schemas import Character, ChapterOutline, WorldSetting
from pipeline.layer1_story.scene_decomposer import decompose_chapter_scenes


def _outline(n=1):
    return ChapterOutline(chapter_number=n, title=f"Chương {n}", summary="tóm tắt")


def _world():
    return WorldSetting(name="Hà Nội", description="thành phố mưa")


def _characters():
    return [Character(name="Lan", role="protagonist", personality="quyết đoán")]


def _llm(scenes=None):
    llm = MagicMock()
    llm.generate_json.return_value = {
        "scenes": scenes if scenes is not None else [{"scene_number": 1}]
    }
    return llm


def _call(llm, outline, genre="hiện đại", model=None):
    return decompose_chapter_scenes(
        llm, outline, _characters(), _world(), genre, model=model
    )


class TestDecompositionIsMemoised:
    def test_second_call_for_the_same_chapter_makes_no_llm_call(self):
        llm, outline = _llm(), _outline()

        first = _call(llm, outline)
        second = _call(llm, outline)

        assert llm.generate_json.call_count == 1, "the chapter was decomposed twice"
        assert first == second

    def test_a_failed_decomposition_is_not_retried(self):
        """A failure is a result: retrying doubles the cost of a bad chapter."""
        llm = MagicMock()
        llm.generate_json.side_effect = RuntimeError("provider down")
        outline = _outline()

        assert _call(llm, outline) == []
        assert _call(llm, outline) == []

        assert llm.generate_json.call_count == 1

    def test_malformed_output_is_also_memoised(self):
        llm = MagicMock()
        llm.generate_json.return_value = {"scenes": "not a list"}
        outline = _outline()

        assert _call(llm, outline) == []
        assert _call(llm, outline) == []
        assert llm.generate_json.call_count == 1

    def test_different_chapters_are_decomposed_separately(self):
        llm = _llm()

        _call(llm, _outline(1))
        _call(llm, _outline(2))

        assert llm.generate_json.call_count == 2

    def test_a_different_model_is_a_different_result(self):
        """Layer routing can send the same chapter to a different model."""
        llm = _llm()
        outline = _outline()

        _call(llm, outline, model="layer1-model")
        _call(llm, outline, model="layer2-model")

        assert llm.generate_json.call_count == 2

    def test_concurrent_callers_do_not_both_decompose(self):
        outline = _outline()
        calls = []

        llm = MagicMock()

        def slow(*a, **k):
            calls.append(1)
            threading.Event().wait(0.02)
            return {"scenes": [{"scene_number": 1}]}

        llm.generate_json.side_effect = slow

        threads = [
            threading.Thread(target=lambda: _call(llm, outline)) for _ in range(6)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Callers for the same chapter serialise on that outline's own lock,
        # so exactly one of them decomposes.
        assert len(calls) == 1, f"{len(calls)} of 6 callers each decomposed"

    def test_result_is_still_clamped_to_five_scenes(self):
        llm = _llm(scenes=[{"scene_number": i} for i in range(9)])
        assert len(_call(llm, _outline())) == 5
