"""Integration: enhancer drama-contract validation + retry path."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from models.schemas import Chapter, SimulationResult
from pipeline.layer2_enhance.chapter_contract import DramaContract
from pipeline.layer2_enhance.enhancer import StoryEnhancer


@pytest.fixture
def enhancer():
    with patch("pipeline.layer2_enhance.enhancer.LLMClient"):
        e = StoryEnhancer()
        e.llm = MagicMock()
        return e


def _chapter(num: int = 1, content: str = "Enhanced text") -> Chapter:
    return Chapter(chapter_number=num, title=f"Ch{num}", content=content, word_count=2)


def _contract_dict(num: int = 1, target: float = 0.7) -> dict:
    return DramaContract(
        chapter_number=num, drama_target=target,
        required_escalations=["confrontation"],
    ).model_dump()


class TestContractValidationPath:
    def test_skips_when_no_contract(self, enhancer):
        """No contracts on sim_result → enhancement returns chapter unchanged."""
        sim = SimulationResult()
        orig = _chapter(1, "original")
        enhanced = _chapter(1, "enhanced")
        result = enhancer._apply_contract_validation(
            enhanced_chapter=enhanced, original=orig, sim_result=sim,
            genre="", draft=None, subtext_guidance="", thematic_guidance="",
            chapter_summary=None, thread_state=None, arc_context="",
            pacing_directive="", consistency_constraints="",
        )
        assert result is enhanced
        assert result.contract_validation is None

    def test_passes_no_retry(self, enhancer):
        sim = SimulationResult(chapter_contracts={1: _contract_dict(1, 0.7)})
        enhancer.llm.generate_json.return_value = {
            "drama_actual": 0.72,
            "missing_escalations": [],
            "missing_subtext": [],
            "missing_causal_refs": [],
            "violated_patterns": [],
            "reason": "good",
        }
        result = enhancer._apply_contract_validation(
            enhanced_chapter=_chapter(1, "x"), original=_chapter(1, "o"),
            sim_result=sim, genre="", draft=None, subtext_guidance="",
            thematic_guidance="", chapter_summary=None, thread_state=None,
            arc_context="", pacing_directive="", consistency_constraints="",
        )
        assert result.contract_validation is not None
        assert result.contract_validation["passed"] is True
        # Only 1 validation call, no retry
        assert enhancer.llm.generate_json.call_count == 1

    def test_fails_triggers_retry(self, enhancer):
        """Failed validation should trigger retry with injected hint."""
        sim = SimulationResult(chapter_contracts={1: _contract_dict(1, 0.8)})
        # First validation fails, retry validation succeeds
        enhancer.llm.generate_json.side_effect = [
            {
                "drama_actual": 0.3,
                "missing_escalations": ["confrontation"],
                "missing_subtext": [], "missing_causal_refs": [],
                "violated_patterns": [], "reason": "weak",
            },
            {
                "drama_actual": 0.82,
                "missing_escalations": [], "missing_subtext": [],
                "missing_causal_refs": [], "violated_patterns": [],
                "reason": "fixed",
            },
        ]

        retried_chapter = _chapter(1, "retried stronger")
        with patch("pipeline.layer2_enhance.scene_enhancer.SceneEnhancer") as MockSE2:
            instance = MockSE2.return_value
            instance.enhance_chapter_by_scenes.return_value = retried_chapter

            result = enhancer._apply_contract_validation(
                enhanced_chapter=_chapter(1, "weak"), original=_chapter(1, "o"),
                sim_result=sim, genre="", draft=None, subtext_guidance="base",
                thematic_guidance="", chapter_summary=None, thread_state=None,
                arc_context="", pacing_directive="", consistency_constraints="",
            )

        # Retry happened
        assert enhancer.llm.generate_json.call_count == 2
        # Retry hint injected into subtext_guidance
        call = instance.enhance_chapter_by_scenes.call_args
        assert "[RETRY HINT]" in call.kwargs["subtext_guidance"]
        # Result is the retried chapter with validation attached
        assert result.content == "retried stronger"
        assert result.contract_validation["passed"] is True
        assert result.contract_validation["retry_attempted"] is True

    def test_retry_worse_than_original_keeps_original(self, enhancer):
        """If retry compliance < original, keep original enhanced chapter."""
        sim = SimulationResult(chapter_contracts={1: _contract_dict(1, 0.8)})
        enhancer.llm.generate_json.side_effect = [
            {
                "drama_actual": 0.6,
                "missing_escalations": ["confrontation"],
                "missing_subtext": [], "missing_causal_refs": [],
                "violated_patterns": [], "reason": "partial",
            },
            {
                "drama_actual": 0.1,
                "missing_escalations": ["confrontation", "reveal"],
                "missing_subtext": ["subtext"], "missing_causal_refs": [],
                "violated_patterns": ["hero dies"], "reason": "worse",
            },
        ]
        with patch("pipeline.layer2_enhance.scene_enhancer.SceneEnhancer") as MockSE2:
            MockSE2.return_value.enhance_chapter_by_scenes.return_value = _chapter(1, "worse")
            first_enhanced = _chapter(1, "first")
            result = enhancer._apply_contract_validation(
                enhanced_chapter=first_enhanced, original=_chapter(1, "o"),
                sim_result=sim, genre="", draft=None, subtext_guidance="",
                thematic_guidance="", chapter_summary=None, thread_state=None,
                arc_context="", pacing_directive="", consistency_constraints="",
            )
        assert result.content == "first"  # retry was worse, kept original enhanced
