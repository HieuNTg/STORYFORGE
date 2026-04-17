"""Sprint 2 Task 2 — VoiceContract unit tests."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from models.schemas import ChapterOutline, Character, VoiceProfile
from pipeline.layer2_enhance.chapter_contract import (
    VoiceContract,
    VoiceValidation,
    aggregate_voice_stats,
    build_voice_contracts,
    build_voice_retry_hint,
    validate_chapter_voice,
)


def _mk_outline(ch=1, summary="Linh gặp An.", chars=None):
    return ChapterOutline(
        chapter_number=ch,
        title=f"Ch{ch}",
        summary=summary,
        key_events=["event"],
        characters_involved=chars or ["Linh", "An"],
        emotional_arc="tension",
    )


def _mk_chars():
    return [
        Character(name="Linh", role="protagonist", personality="determined"),
        Character(name="An", role="antagonist", personality="mysterious"),
    ]


def _mk_l1_profiles():
    return [
        {
            "name": "Linh",
            "vocabulary_level": "casual",
            "sentence_style": "short_punchy",
            "verbal_tics": ["thật ra là", "vậy đó"],
            "emotional_expression": {"anger": "im lặng", "joy": "cười nhẹ"},
            "dialogue_example": ["Thật ra là tôi không biết.", "Vậy đó, kết thúc rồi."],
        },
        {
            "name": "An",
            "vocabulary_level": "formal",
            "sentence_style": "long_flowing",
            "verbal_tics": ["kính thưa"],
            "emotional_expression": {"anger": "lạnh lùng"},
            "dialogue_example": ["Kính thưa, tôi nghĩ khác."],
        },
    ]


class TestVoiceContractRoundtrip:
    def test_serialize_roundtrip(self):
        v = VoiceContract(
            chapter_number=5,
            per_character={"Linh": {"vocabulary_level": "casual"}},
            min_compliance=0.8,
        )
        d = v.model_dump()
        v2 = VoiceContract(**d)
        assert v2.chapter_number == 5
        assert v2.min_compliance == 0.8
        assert "Linh" in v2.per_character

    def test_validation_roundtrip(self):
        v = VoiceValidation(
            chapter_number=3,
            per_character_scores={"Linh": 0.9},
            overall_compliance=0.85,
            passed=True,
        )
        d = v.model_dump()
        v2 = VoiceValidation(**d)
        assert v2.passed
        assert v2.overall_compliance == 0.85


class TestBuildVoiceContracts:
    def test_maps_speakers_to_profiles(self):
        outlines = [_mk_outline(ch=1), _mk_outline(ch=2)]
        contracts = build_voice_contracts(
            _mk_l1_profiles(), outlines, characters=_mk_chars(),
        )
        assert 1 in contracts and 2 in contracts
        c1 = contracts[1]
        assert set(c1.per_character.keys()) == {"Linh", "An"}
        assert c1.per_character["Linh"]["vocabulary_level"] == "casual"
        assert "thật ra là" in c1.per_character["Linh"]["verbal_tics"]
        # dialogue_example → dialogue_examples mapping works
        assert c1.per_character["Linh"]["dialogue_examples"][0].startswith("Thật ra")

    def test_skips_chapters_without_matching_profiles(self):
        outlines = [_mk_outline(ch=1, chars=["Unknown"])]
        contracts = build_voice_contracts(
            _mk_l1_profiles(), outlines, characters=[Character(name="Unknown", role="extra", personality="x")],
        )
        assert contracts == {}

    def test_accepts_dict_profile_map(self):
        vp_map = {p["name"]: p for p in _mk_l1_profiles()}
        outlines = [_mk_outline(ch=1)]
        contracts = build_voice_contracts(vp_map, outlines, characters=_mk_chars())
        assert 1 in contracts

    def test_accepts_unified_VoiceProfile_models(self):
        vp_map = {"Linh": VoiceProfile(name="Linh", vocabulary_level="casual", verbal_tics=["ừ"])}
        outlines = [_mk_outline(ch=1, chars=["Linh"])]
        contracts = build_voice_contracts(vp_map, outlines, characters=[Character(name="Linh", role="p", personality="x")])
        assert 1 in contracts
        assert contracts[1].per_character["Linh"]["vocabulary_level"] == "casual"


class TestValidateChapterVoice:
    def test_empty_contract_passes(self):
        llm = MagicMock()
        v = validate_chapter_voice(llm, "content", VoiceContract(chapter_number=1, per_character={}))
        assert v.passed
        assert v.reason == "no_speakers"
        llm.generate_json.assert_not_called()

    def test_all_pass(self):
        llm = MagicMock()
        llm.generate_json.return_value = {
            "per_character": {
                "Linh": {"compliance_score": 0.9, "missing_tics": [], "tone_mismatch": ""},
                "An": {"compliance_score": 0.85, "missing_tics": [], "tone_mismatch": ""},
            },
            "reason": "ok",
        }
        contract = VoiceContract(
            chapter_number=1,
            per_character={"Linh": {"verbal_tics": ["ừ"]}, "An": {"verbal_tics": ["kính thưa"]}},
        )
        v = validate_chapter_voice(llm, 'Some "dialogue" here.', contract)
        assert v.passed
        assert v.overall_compliance == pytest.approx(0.875)
        assert v.drifted_characters == []

    def test_drift_detected(self):
        llm = MagicMock()
        llm.generate_json.return_value = {
            "per_character": {
                "Linh": {"compliance_score": 0.5, "missing_tics": ["ừ", "vậy đó"], "tone_mismatch": "quá trịnh trọng"},
            },
            "reason": "drift",
        }
        contract = VoiceContract(chapter_number=1, per_character={"Linh": {"verbal_tics": ["ừ", "vậy đó"]}})
        v = validate_chapter_voice(llm, "content", contract)
        assert not v.passed
        assert "Linh" in v.drifted_characters
        assert v.missing_tics.get("Linh") == ["ừ", "vậy đó"]
        assert v.tone_mismatches.get("Linh") == "quá trịnh trọng"

    def test_llm_error_returns_failed(self):
        llm = MagicMock()
        llm.generate_json.side_effect = RuntimeError("boom")
        contract = VoiceContract(chapter_number=2, per_character={"Linh": {}})
        v = validate_chapter_voice(llm, "content", contract)
        assert not v.passed
        assert "voice_llm_error" in v.reason

    def test_malformed_response(self):
        llm = MagicMock()
        llm.generate_json.return_value = "not a dict"
        contract = VoiceContract(chapter_number=3, per_character={"Linh": {}})
        v = validate_chapter_voice(llm, "content", contract)
        assert not v.passed
        assert v.reason == "malformed"

    def test_tolerance_missing_tics(self):
        """tolerance_missing_tics=1 → 1 missing OK, 2 missing fails."""
        llm = MagicMock()
        llm.generate_json.return_value = {
            "per_character": {
                "Linh": {"compliance_score": 0.9, "missing_tics": ["x"], "tone_mismatch": ""},
            },
            "reason": "",
        }
        contract = VoiceContract(
            chapter_number=1, per_character={"Linh": {}}, tolerance_missing_tics=1,
        )
        v = validate_chapter_voice(llm, "content", contract)
        assert "Linh" not in v.missing_tics  # within tolerance


class TestRetryHint:
    def test_hint_includes_drift_and_tics(self):
        v = VoiceValidation(
            chapter_number=1,
            drifted_characters=["Linh"],
            missing_tics={"Linh": ["thật ra là"]},
            tone_mismatches={"An": "quá giận dữ"},
        )
        hint = build_voice_retry_hint(v)
        assert "Linh" in hint
        assert "thật ra là" in hint
        assert "An" in hint
        assert "quá giận dữ" in hint


class TestAggregateVoiceStats:
    def test_empty(self):
        s = aggregate_voice_stats([], llm_calls_saved=0)
        assert s["total_chapters"] == 0
        assert s["l2_llm_calls_saved"] == 0

    def test_counts_retry_revert(self):
        vs = [
            VoiceValidation(chapter_number=1, passed=True, overall_compliance=0.9),
            VoiceValidation(chapter_number=2, passed=True, overall_compliance=0.8, retry_attempted=True),
            VoiceValidation(chapter_number=3, passed=False, overall_compliance=0.4, retry_attempted=True, binary_reverted=True, drifted_characters=["Linh"]),
        ]
        s = aggregate_voice_stats(vs, llm_calls_saved=50)
        assert s["total_chapters"] == 3
        assert s["passed_first_try"] == 1
        assert s["passed_after_retry"] == 1
        assert s["failed_after_retry"] == 1
        assert s["binary_reverts"] == 1
        assert s["chars_drifted_total"] == 1
        assert s["l2_llm_calls_saved"] == 50


class TestSupplementObserved:
    def test_zero_llm_stats(self):
        from pipeline.layer2_enhance.voice_fingerprint import supplement_observed

        profile = VoiceProfile(name="Linh", verbal_tics=["ừ"])
        samples = ["Thưa ngài, tôi đồng ý.", "Kính chào."]  # formal particles
        out = supplement_observed(profile, samples)
        assert out.source == "L1+L2"
        assert out.observed_avg_sentence_length > 0
        assert out.observed_formality == "formal"
        assert len(out.observed_samples) == 2

    def test_empty_samples_noop(self):
        from pipeline.layer2_enhance.voice_fingerprint import supplement_observed

        p = VoiceProfile(name="Linh")
        out = supplement_observed(p, [])
        assert out.source == "L1"
        assert out.observed_avg_sentence_length == 0.0

    def test_casual_detected(self):
        from pipeline.layer2_enhance.voice_fingerprint import supplement_observed

        p = VoiceProfile(name="Linh")
        out = supplement_observed(p, ["Ừ nhé, mày đi đi.", "Ờ vậy đó."])
        assert out.observed_formality == "casual"
