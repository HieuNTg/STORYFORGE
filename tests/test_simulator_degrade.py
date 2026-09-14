"""Regression tests: a late LLM failure must not discard the whole L2 layer.

`evaluate_drama` and `_generate_suggestions` were awaited unguarded. A provider
error on either — call ~91 of ~100 in a typical run — propagated out of
`run_simulation_async` into the layer-wide handler, which threw away every
successful round and shipped the raw L1 draft with `drama_score=0.0`.
"""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from models.schemas import Character, Relationship
from pipeline.layer2_enhance.simulator import DramaSimulator


def _characters():
    return [
        Character(name="Lan", role="protagonist", personality="quyết đoán"),
        Character(name="Minh", role="antagonist", personality="lạnh lùng"),
    ]


def _relationships():
    return [Relationship(character_a="Lan", character_b="Minh", relation_type="đối_thủ")]


def _simulator():
    with patch("pipeline.layer2_enhance.simulator.LLMClient"):
        sim = DramaSimulator()
    sim.llm = MagicMock()
    return sim


def _run(sim, **kwargs):
    return asyncio.run(
        sim.run_simulation_async(
            characters=_characters(),
            relationships=_relationships(),
            genre="hiện đại",
            num_rounds=2,
            **kwargs,
        )
    )


class TestDramaEvaluationFailure:
    def test_provider_error_does_not_abort_the_simulation(self):
        sim = _simulator()
        with patch.object(
            DramaSimulator, "simulate_round_async", new=_stub_round
        ), patch.object(
            DramaSimulator, "evaluate_drama", side_effect=RuntimeError("provider 503")
        ), patch.object(
            DramaSimulator, "_generate_suggestions", return_value={}
        ), patch.object(
            DramaSimulator, "_extract_all_psychology_async", new=_stub_noop
        ):
            result = _run(sim)

        assert result is not None, "the whole simulation was discarded"

    def test_non_dict_evaluation_is_tolerated(self):
        """The evaluator occasionally returns a list; `.get` used to raise."""
        sim = _simulator()
        with patch.object(
            DramaSimulator, "simulate_round_async", new=_stub_round
        ), patch.object(
            DramaSimulator, "evaluate_drama", return_value=["not", "a", "dict"]
        ), patch.object(
            DramaSimulator, "_generate_suggestions", return_value={}
        ), patch.object(
            DramaSimulator, "_extract_all_psychology_async", new=_stub_noop
        ):
            result = _run(sim)

        assert result is not None


class TestSuggestionFailure:
    def test_suggestion_error_keeps_the_simulated_rounds(self):
        sim = _simulator()
        with patch.object(
            DramaSimulator, "simulate_round_async", new=_stub_round
        ), patch.object(
            DramaSimulator, "evaluate_drama", return_value={"overall_drama_score": 0.7}
        ), patch.object(
            DramaSimulator,
            "_generate_suggestions",
            side_effect=RuntimeError("rate limited"),
        ), patch.object(
            DramaSimulator, "_extract_all_psychology_async", new=_stub_noop
        ):
            result = _run(sim)

        assert result is not None, "suggestions are advisory; rounds must survive"

    def test_non_dict_suggestions_are_tolerated(self):
        sim = _simulator()
        with patch.object(
            DramaSimulator, "simulate_round_async", new=_stub_round
        ), patch.object(
            DramaSimulator, "evaluate_drama", return_value={"overall_drama_score": 0.7}
        ), patch.object(
            DramaSimulator, "_generate_suggestions", return_value="oops"
        ), patch.object(
            DramaSimulator, "_extract_all_psychology_async", new=_stub_noop
        ):
            result = _run(sim)

        assert result is not None


async def _stub_round(self, round_num, genre, num_rounds, progress_callback=None):
    """One cheap synthetic round, no LLM traffic."""
    return []


async def _stub_noop(self, *args, **kwargs):
    return None


@pytest.mark.parametrize("failing", ["evaluate_drama", "_generate_suggestions"])
def test_failure_is_reported_on_the_progress_channel(failing):
    """Degradation must be visible, not silent."""
    sim = _simulator()
    messages: list[str] = []

    patches = {
        "evaluate_drama": {"return_value": {"overall_drama_score": 0.7}},
        "_generate_suggestions": {"return_value": {}},
    }
    patches[failing] = {"side_effect": RuntimeError("boom")}

    with patch.object(
        DramaSimulator, "simulate_round_async", new=_stub_round
    ), patch.object(
        DramaSimulator, "_extract_all_psychology_async", new=_stub_noop
    ), patch.object(
        DramaSimulator, "evaluate_drama", **patches["evaluate_drama"]
    ), patch.object(
        DramaSimulator, "_generate_suggestions", **patches["_generate_suggestions"]
    ):
        _run(sim, progress_callback=messages.append)

    assert any("[SIM] WARN" in m for m in messages), messages
