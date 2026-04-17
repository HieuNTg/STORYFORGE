"""Integration: enhancer voice-contract validation + graduated revert path."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from models.schemas import Chapter, SimulationResult
from pipeline.layer2_enhance.chapter_contract import VoiceContract
from pipeline.layer2_enhance.enhancer import StoryEnhancer


@pytest.fixture
def enhancer():
    with patch("pipeline.layer2_enhance.enhancer.LLMClient"):
        e = StoryEnhancer()
        e.llm = MagicMock()
        return e


def _chapter(num: int = 1, content: str = "Enhanced text") -> Chapter:
    return Chapter(chapter_number=num, title=f"Ch{num}", content=content, word_count=2)


def _voice_contract_dict(num: int = 1) -> dict:
    return VoiceContract(
        chapter_number=num,
        per_character={
            "Linh": {"vocabulary_level": "casual", "verbal_tics": ["ừ", "vậy đó"]},
        },
        min_compliance=0.75,
    ).model_dump()


class TestVoiceValidationPath:
    def test_skips_when_no_voice_contract(self, enhancer):
        sim = SimulationResult()
        orig = _chapter(1, "original")
        enhanced = _chapter(1, "enhanced")
        result = enhancer._apply_voice_validation(
            enhanced_chapter=enhanced, original=orig, sim_result=sim,
            genre="", draft=None, subtext_guidance="", thematic_guidance="",
            chapter_summary=None, thread_state=None, arc_context="",
            pacing_directive="", consistency_constraints="",
        )
        assert result is enhanced
        assert result.voice_validation is None

    def test_passes_no_retry(self, enhancer):
        sim = SimulationResult(voice_contracts={1: _voice_contract_dict(1)})
        enhancer.llm.generate_json.return_value = {
            "per_character": {
                "Linh": {"compliance_score": 0.9, "missing_tics": [], "tone_mismatch": ""},
            },
            "reason": "ok",
        }
        result = enhancer._apply_voice_validation(
            enhanced_chapter=_chapter(1, "x"), original=_chapter(1, "o"),
            sim_result=sim, genre="", draft=None, subtext_guidance="",
            thematic_guidance="", chapter_summary=None, thread_state=None,
            arc_context="", pacing_directive="", consistency_constraints="",
        )
        assert result.voice_validation is not None
        assert result.voice_validation["passed"] is True
        assert enhancer.llm.generate_json.call_count == 1

    def test_fails_triggers_refine_with_hint(self, enhancer):
        """Failed voice validation → refine via SceneEnhancer with [VOICE HINT]."""
        sim = SimulationResult(voice_contracts={1: _voice_contract_dict(1)})
        enhancer.llm.generate_json.side_effect = [
            {
                "per_character": {
                    "Linh": {"compliance_score": 0.4, "missing_tics": ["ừ", "vậy đó"], "tone_mismatch": "quá trịnh trọng"},
                },
                "reason": "drift",
            },
            {
                "per_character": {
                    "Linh": {"compliance_score": 0.85, "missing_tics": [], "tone_mismatch": ""},
                },
                "reason": "fixed",
            },
        ]

        refined_chapter = _chapter(1, "refined with voice hint")
        with patch("pipeline.layer2_enhance.scene_enhancer.SceneEnhancer") as MockSE:
            instance = MockSE.return_value
            instance.enhance_chapter_by_scenes.return_value = refined_chapter

            result = enhancer._apply_voice_validation(
                enhanced_chapter=_chapter(1, "drifted"), original=_chapter(1, "o"),
                sim_result=sim, genre="", draft=None, subtext_guidance="base",
                thematic_guidance="", chapter_summary=None, thread_state=None,
                arc_context="", pacing_directive="", consistency_constraints="",
            )

        assert enhancer.llm.generate_json.call_count == 2
        call = instance.enhance_chapter_by_scenes.call_args
        assert "[VOICE HINT]" in call.kwargs["subtext_guidance"]
        assert result.content == "refined with voice hint"
        assert result.voice_validation["passed"] is True
        assert result.voice_validation["retry_attempted"] is True

    def test_refine_worse_keeps_original_enhanced(self, enhancer):
        """If refine compliance < original enhanced, keep the original enhanced (no binary revert unless <floor)."""
        sim = SimulationResult(voice_contracts={1: _voice_contract_dict(1)})
        # original enhanced fails but above floor; refine makes it worse (still above floor)
        enhancer.llm.generate_json.side_effect = [
            {
                "per_character": {
                    "Linh": {"compliance_score": 0.6, "missing_tics": ["ừ"], "tone_mismatch": ""},
                },
                "reason": "partial",
            },
            {
                "per_character": {
                    "Linh": {"compliance_score": 0.55, "missing_tics": ["ừ", "vậy đó"], "tone_mismatch": "xa lạ"},
                },
                "reason": "worse",
            },
        ]
        with patch("pipeline.layer2_enhance.scene_enhancer.SceneEnhancer") as MockSE:
            MockSE.return_value.enhance_chapter_by_scenes.return_value = _chapter(1, "worse")
            first_enhanced = _chapter(1, "first")
            result = enhancer._apply_voice_validation(
                enhanced_chapter=first_enhanced, original=_chapter(1, "o"),
                sim_result=sim, genre="", draft=None, subtext_guidance="",
                thematic_guidance="", chapter_summary=None, thread_state=None,
                arc_context="", pacing_directive="", consistency_constraints="",
            )
        assert result.content == "first"

    def test_catastrophic_drift_triggers_binary_revert(self, enhancer):
        """compliance < voice_binary_revert_floor (0.5) after refine → binary revert via enforce_voice_preservation."""
        sim = SimulationResult(voice_contracts={1: _voice_contract_dict(1)})
        enhancer.llm.generate_json.side_effect = [
            {
                "per_character": {
                    "Linh": {"compliance_score": 0.2, "missing_tics": ["ừ", "vậy đó"], "tone_mismatch": "hoàn toàn khác"},
                },
                "reason": "catastrophic",
            },
            {
                "per_character": {
                    "Linh": {"compliance_score": 0.15, "missing_tics": ["ừ", "vậy đó"], "tone_mismatch": "tệ hơn"},
                },
                "reason": "worse",
            },
        ]

        # Mock draft with one character
        draft = MagicMock()
        char = MagicMock()
        char.name = "Linh"
        draft.characters = [char]
        draft.chapters = []
        draft.voice_profiles = []

        # Mock SceneEnhancer for refine
        with patch("pipeline.layer2_enhance.scene_enhancer.SceneEnhancer") as MockSE, \
             patch("pipeline.layer2_enhance.voice_fingerprint.VoiceFingerprintEngine") as MockEngine, \
             patch("pipeline.layer2_enhance.voice_fingerprint.enforce_voice_preservation") as mock_enforce:
            MockSE.return_value.enhance_chapter_by_scenes.return_value = _chapter(1, "still bad")

            vp_result = MagicMock()
            vp_result.reverted_count = 2
            mock_enforce.return_value = ("reverted content", vp_result)

            engine_instance = MockEngine.return_value
            engine_instance.build_from_draft.return_value = engine_instance

            result = enhancer._apply_voice_validation(
                enhanced_chapter=_chapter(1, "drifted"), original=_chapter(1, "original"),
                sim_result=sim, genre="", draft=draft, subtext_guidance="",
                thematic_guidance="", chapter_summary=None, thread_state=None,
                arc_context="", pacing_directive="", consistency_constraints="",
            )

        assert result.voice_validation["binary_reverted"] is True
        assert result.content == "reverted content"
        mock_enforce.assert_called_once()
