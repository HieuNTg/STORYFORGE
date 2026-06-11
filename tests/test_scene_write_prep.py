"""Unit tests for pipeline.layer1_story.scene_write_prep.

Covers the sequential-path scene prep extracted from batch_generator:
beat appending to the enhancement context, decomposition gating, per-beat
writing success, and the fall-back-to-normal-write failure path.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from pipeline.layer1_story.scene_write_prep import (
    prepare_scene_context_and_beat_chapter,
)


def _batch_gen(decomposition: bool = False, beat_writing: bool = False):
    return SimpleNamespace(
        llm=object(),
        config=SimpleNamespace(
            pipeline=SimpleNamespace(
                enable_scene_decomposition=decomposition,
                enable_scene_beat_writing=beat_writing,
            )
        ),
        gen=SimpleNamespace(_layer_model="cheap"),
    )


def _outline(num: int = 3) -> SimpleNamespace:
    return SimpleNamespace(chapter_number=num, title=f"Chương {num}")


def _story_context() -> SimpleNamespace:
    return SimpleNamespace(recent_summaries=["tóm tắt 1", "tóm tắt 2"])


def _call(batch_gen, **overrides):
    kwargs = dict(
        outline=_outline(),
        characters=[],
        world=None,
        genre="tiên hiệp",
        title="Kiếm Đạo",
        style="cổ trang",
        word_count=1000,
        story_context=_story_context(),
        enhancement_context="bối cảnh sẵn có",
        stream_callback=None,
    )
    kwargs.update(overrides)
    return prepare_scene_context_and_beat_chapter(batch_gen, **kwargs)


class TestSceneBeats:
    def test_no_beats_leaves_context_unchanged(self):
        with patch(
            "pipeline.layer1_story.scene_beat_generator.generate_scene_beats",
            return_value=[],
        ):
            ctx, scenes, beat_chapter = _call(_batch_gen())
        assert ctx == "bối cảnh sẵn có"
        assert scenes == []
        assert beat_chapter is None

    def test_beats_appended_to_enhancement_context(self):
        with (
            patch(
                "pipeline.layer1_story.scene_beat_generator.generate_scene_beats",
                return_value=[{"beat": "mở màn"}],
            ),
            patch(
                "pipeline.layer1_story.scene_beat_generator.format_beats_for_prompt",
                return_value="NHỊP CẢNH",
            ),
        ):
            ctx, _, _ = _call(_batch_gen())
        assert ctx == "bối cảnh sẵn có\n\nNHỊP CẢNH"


class TestSceneDecomposition:
    def test_decomposition_failure_is_non_fatal(self, caplog):
        with (
            patch(
                "pipeline.layer1_story.scene_beat_generator.generate_scene_beats",
                return_value=[],
            ),
            patch(
                "pipeline.layer1_story.scene_decomposer.decompose_chapter_scenes",
                side_effect=RuntimeError("boom"),
            ),
        ):
            _, scenes, _ = _call(_batch_gen(decomposition=True))
        assert scenes == []
        assert any("non-fatal" in r.message for r in caplog.records)


class TestBeatWriting:
    def test_successful_beat_writing_returns_chapter(self):
        with (
            patch(
                "pipeline.layer1_story.scene_beat_generator.generate_scene_beats",
                return_value=[{"beat": "mở màn"}],
            ),
            patch(
                "pipeline.layer1_story.scene_beat_generator.format_beats_for_prompt",
                return_value="NHỊP CẢNH",
            ),
            patch(
                "pipeline.layer1_story.chapter_writer.write_chapter_by_beats",
                return_value="Nội dung chương viết theo nhịp.",
            ),
        ):
            _, _, beat_chapter = _call(_batch_gen(beat_writing=True))
        assert beat_chapter is not None
        assert beat_chapter.chapter_number == 3
        assert beat_chapter.content == "Nội dung chương viết theo nhịp."

    def test_beat_writing_failure_falls_back(self, caplog):
        with (
            patch(
                "pipeline.layer1_story.scene_beat_generator.generate_scene_beats",
                return_value=[{"beat": "mở màn"}],
            ),
            patch(
                "pipeline.layer1_story.scene_beat_generator.format_beats_for_prompt",
                return_value="NHỊP CẢNH",
            ),
            patch(
                "pipeline.layer1_story.chapter_writer.write_chapter_by_beats",
                side_effect=RuntimeError("boom"),
            ),
        ):
            _, _, beat_chapter = _call(_batch_gen(beat_writing=True))
        assert beat_chapter is None
        assert any("falling back" in r.message for r in caplog.records)

    def test_stream_mode_disables_beat_writing(self):
        with (
            patch(
                "pipeline.layer1_story.scene_beat_generator.generate_scene_beats",
                return_value=[{"beat": "mở màn"}],
            ),
            patch(
                "pipeline.layer1_story.scene_beat_generator.format_beats_for_prompt",
                return_value="NHỊP CẢNH",
            ),
            patch(
                "pipeline.layer1_story.chapter_writer.write_chapter_by_beats"
            ) as mock_write,
        ):
            _, _, beat_chapter = _call(
                _batch_gen(beat_writing=True), stream_callback=lambda *_: None
            )
            mock_write.assert_not_called()
        assert beat_chapter is None
