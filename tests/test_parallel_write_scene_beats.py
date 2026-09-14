"""The parallel write path crashed Layer 1 whenever scene beats were produced.

Found on a real run against a live provider, not in the suite:

    File "pipeline/layer1_story/parallel_write_context.py", line 165
        per_chapter_enhancement += scene_beats
    TypeError: can only concatenate str (not "list") to str

`generate_scene_beats` returns `list[SceneBeat]`, and the module ships a
`format_beats_for_prompt` renderer that the sequential write path has always
used. The parallel path — which is the default (`mode=parallel`) — concatenated
the raw list onto the prompt string.

It looked stable because beats are gated by pacing type and the generator
returns `[]` on failure, so the `if scene_beats:` guard usually skipped it. The
moment the generator actually succeeded, the whole story failed: not one
chapter, the entire Layer 1, because the exception propagated out of
asyncio.gather through _run_batch_async.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from pipeline.layer1_story.parallel_write_context import (
    assemble_parallel_write_inputs,
)


class _Beat:
    def __init__(self, n=1):
        self.scene_num = n
        self.setting = "Bát Tràng, chiều muộn"
        self.action = "Thanh tra tìm thấy chiếc bình men rạn"
        self.pov = "Lan"
        self.tension_level = 0.7
        self.emotional_goal = "nghi ngờ"
        self.characters = ["Lan", "Minh"]


def _outline(n=1):
    return SimpleNamespace(
        chapter_number=n,
        title=f"Chương {n}",
        summary="tóm tắt",
        pacing_type="rising",
        key_events=[],
    )


def _gen():
    gen = SimpleNamespace(_layer_model="cheap")
    return gen


def _frozen():
    """The frozen snapshot the parallel writer copies its context from."""
    return SimpleNamespace(recent_summaries=[], character_states=[], plot_events=[])


def _call(beats, *, decomposition=False, shared="bối cảnh sẵn có"):
    cfg = SimpleNamespace(
        pipeline=SimpleNamespace(
            enable_scene_decomposition=decomposition,
            enable_theme_premise=False,
            enable_voice_profiles=False,
        )
    )
    story_context = SimpleNamespace(
        open_threads=[],
        recent_summaries=[],
        character_states=[],
        plot_events=[],
        total_chapters=3,
    )
    with patch(
        "pipeline.layer1_story.scene_beat_generator.generate_scene_beats",
        return_value=beats,
    ):
        return assemble_parallel_write_inputs(
            _gen(),
            cfg,
            MagicMock(),
            outline=_outline(),
            characters=[SimpleNamespace(name="Lan"), SimpleNamespace(name="Minh")],
            world=SimpleNamespace(name="Hà Nội Ẩn Khúc", rules=[]),
            genre="Trinh thám",
            story_context=story_context,
            frozen=_frozen(),
            draft=SimpleNamespace(story_bible=None, characters=[]),
            frozen_threads=[],
            sibling_summaries="",
            shared_enhancement=shared,
            macro_arcs=[],
            conflict_web=[],
            foreshadowing_plan=[],
        )


class TestBeatsReachThePromptAsText:
    def test_beats_do_not_raise(self):
        """The defect: a list concatenated onto a string, killing all of L1."""
        _call([_Beat(1), _Beat(2)])

    def test_the_enhancement_stays_a_string(self):
        result = _call([_Beat(1)])
        assert isinstance(result.enhancement, str)

    def test_the_beat_structure_actually_lands_in_the_prompt(self):
        """Rendering must not be silently dropped — beats exist to steer writing."""
        result = _call([_Beat(1)])
        assert "CẤU TRÚC CẢNH" in result.enhancement
        assert "Bát Tràng" in result.enhancement

    def test_the_shared_context_is_preserved(self):
        result = _call([_Beat(1)], shared="bối cảnh sẵn có")
        assert result.enhancement.startswith("bối cảnh sẵn có")

    def test_no_beats_leaves_the_context_untouched(self):
        result = _call([])
        assert result.enhancement == "bối cảnh sẵn có"


class TestFailuresAreNonFatal:
    def test_a_beat_generator_failure_does_not_kill_the_chapter(self):
        """One flaky cheap call must not cost the whole story."""
        cfg = SimpleNamespace(
            pipeline=SimpleNamespace(
                enable_scene_decomposition=False,
                enable_theme_premise=False,
                enable_voice_profiles=False,
            )
        )
        story_context = SimpleNamespace(
            open_threads=[],
            recent_summaries=[],
            character_states=[],
            plot_events=[],
            total_chapters=3,
        )
        with patch(
            "pipeline.layer1_story.scene_beat_generator.generate_scene_beats",
            side_effect=RuntimeError("provider 503"),
        ):
            result = assemble_parallel_write_inputs(
                _gen(),
                cfg,
                MagicMock(),
                outline=_outline(),
                characters=[SimpleNamespace(name="Lan")],
                world=SimpleNamespace(name="W", rules=[]),
                genre="Trinh thám",
                story_context=story_context,
                frozen=_frozen(),
                draft=SimpleNamespace(story_bible=None, characters=[]),
                frozen_threads=[],
                sibling_summaries="",
                shared_enhancement="bối cảnh sẵn có",
                macro_arcs=[],
                conflict_web=[],
                foreshadowing_plan=[],
            )
        assert result.enhancement == "bối cảnh sẵn có"


class TestBothWritePathsRenderBeatsTheSameWay:
    def test_the_parallel_path_uses_the_shared_renderer(self):
        """Two paths formatting beats differently is how this drifted apart."""
        import inspect

        import pipeline.layer1_story.parallel_write_context as mod

        source = inspect.getsource(mod.assemble_parallel_write_inputs)
        assert "format_beats_for_prompt" in source

    @pytest.mark.parametrize("beats", [[_Beat(1)], [_Beat(1), _Beat(2)]])
    def test_rendered_output_matches_the_renderer_exactly(self, beats):
        from pipeline.layer1_story.scene_beat_generator import (
            format_beats_for_prompt,
        )

        result = _call(beats)
        assert result.enhancement.endswith(format_beats_for_prompt(beats))
