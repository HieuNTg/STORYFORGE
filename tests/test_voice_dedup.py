"""Sprint 2 Task 2 — L1↔L2 voice dedup: reuse L1 profiles, skip LLM extraction."""
from __future__ import annotations

from unittest.mock import MagicMock, patch


from models.schemas import Character, Chapter
from pipeline.layer2_enhance.voice_fingerprint import VoiceFingerprintEngine


def _mk_chars():
    return [Character(name="Linh", role="protagonist", personality="determined")]


def _mk_chapters_with_dialogue():
    return [
        Chapter(
            chapter_number=1,
            title="Ch1",
            content='Linh nói: "Thưa ngài, tôi không biết."\nAn đáp lại.',
            word_count=10,
        ),
    ]


def _l1_profile_dict():
    return {
        "name": "Linh",
        "vocabulary_level": "casual",
        "sentence_style": "short_punchy",
        "verbal_tics": ["ừ", "vậy đó"],
        "emotional_expression": {"anger": "im lặng"},
        "dialogue_example": ["Ừ, vậy đó."],
    }


class TestVoiceDedup:
    def test_l1_present_skips_extraction_llm(self):
        """With L1 voice_profiles present, extract_profile must NOT call LLM."""
        with patch("pipeline.layer2_enhance.voice_fingerprint.LLMClient") as MockLLM:
            mock_llm = MockLLM.return_value
            engine = VoiceFingerprintEngine()

            draft = MagicMock()
            draft.characters = _mk_chars()
            draft.chapters = _mk_chapters_with_dialogue()
            draft.voice_profiles = [_l1_profile_dict()]

            engine.build_from_draft(draft, dedup_l1=True)

            # Zero extraction-LLM calls
            assert mock_llm.generate_json.call_count == 0
            # Profile reused from L1
            assert "Linh" in engine.profiles
            p = engine.profiles["Linh"]
            assert p.vocabulary_level == "casual"
            assert "ừ" in p.verbal_tics
            assert engine.llm_calls_saved == 1

    def test_l1_absent_falls_back_to_extraction(self):
        """Without L1 profiles, extract_profile runs and calls LLM."""
        with patch("pipeline.layer2_enhance.voice_fingerprint.LLMClient") as MockLLM:
            mock_llm = MockLLM.return_value
            mock_llm.generate_json.return_value = {
                "vocabulary_level": "moderate",
                "formality": "neutral",
                "speech_quirks": ["à ừm"],
                "emotional_expression": "moderate",
                "accent_markers": [],
                "typical_topics": [],
            }
            engine = VoiceFingerprintEngine()

            draft = MagicMock()
            draft.characters = _mk_chars()
            draft.chapters = _mk_chapters_with_dialogue()
            draft.voice_profiles = []

            engine.build_from_draft(draft, dedup_l1=True)

            # LLM called for extraction (no L1 to reuse)
            assert mock_llm.generate_json.call_count >= 1
            assert engine.llm_calls_saved == 0

    def test_dedup_disabled_forces_extraction_even_with_l1(self):
        """dedup_l1=False → extract even when L1 profile exists."""
        with patch("pipeline.layer2_enhance.voice_fingerprint.LLMClient") as MockLLM:
            mock_llm = MockLLM.return_value
            mock_llm.generate_json.return_value = {
                "vocabulary_level": "simple",
                "formality": "casual",
                "speech_quirks": [],
                "emotional_expression": "reserved",
            }
            engine = VoiceFingerprintEngine()

            draft = MagicMock()
            draft.characters = _mk_chars()
            draft.chapters = _mk_chapters_with_dialogue()
            draft.voice_profiles = [_l1_profile_dict()]

            engine.build_from_draft(draft, dedup_l1=False)

            assert mock_llm.generate_json.call_count >= 1
            assert engine.llm_calls_saved == 0

    def test_reused_profile_supplemented_with_observed(self):
        """L1 reuse + dialogue samples → supplement_observed flips source to 'L1+L2'."""
        with patch("pipeline.layer2_enhance.voice_fingerprint.LLMClient"):
            engine = VoiceFingerprintEngine()
            draft = MagicMock()
            draft.characters = _mk_chars()
            draft.chapters = _mk_chapters_with_dialogue()
            draft.voice_profiles = [_l1_profile_dict()]

            engine.build_from_draft(draft, dedup_l1=True)
            p = engine.profiles["Linh"]
            # With dialogues extracted, source should flip
            if p.observed_samples:
                assert p.source == "L1+L2"
            else:
                assert p.source == "L1"

    def test_llm_calls_saved_counter(self):
        """llm_calls_saved equals number of chars with L1 match."""
        with patch("pipeline.layer2_enhance.voice_fingerprint.LLMClient"):
            engine = VoiceFingerprintEngine()
            draft = MagicMock()
            draft.characters = [
                Character(name="Linh", role="p", personality="x"),
                Character(name="An", role="a", personality="y"),
                Character(name="Unknown", role="e", personality="z"),
            ]
            draft.chapters = []
            draft.voice_profiles = [
                _l1_profile_dict(),
                {"name": "An", "vocabulary_level": "formal", "verbal_tics": ["kính thưa"]},
            ]

            engine.build_from_draft(draft, dedup_l1=True)
            # Linh + An matched → 2 saved; Unknown has no L1 → extraction attempted
            assert engine.llm_calls_saved == 2
            assert "Linh" in engine.profiles
            assert "An" in engine.profiles
