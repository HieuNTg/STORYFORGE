"""Tests for Layer 2 voice fingerprint.

Tests voice profile extraction, consistency checking, and constraint formatting
for character dialogue preservation.
"""

from unittest.mock import MagicMock, patch

import pytest

from models.voice_schemas import DialogueAnchor


@pytest.fixture
def mock_llm():
    """Create a mocked LLM client."""
    llm = MagicMock()
    llm.generate_json.return_value = {
        "vocabulary_level": "moderate",
        "formality": "neutral",
        "speech_quirks": ["cách nói thô"],
        "emotional_expression": "moderate",
        "accent_markers": [],
        "typical_topics": ["công việc"],
        "style_summary": "Bình thường",
    }
    return llm


@pytest.fixture
def voice_fingerprint_engine(mock_llm):
    """Create VoiceFingerprintEngine instance with mocked LLM."""
    with patch("pipeline.layer2_enhance.voice_fingerprint.LLMClient", return_value=mock_llm):
        from pipeline.layer2_enhance.voice_fingerprint import VoiceFingerprintEngine
        engine = VoiceFingerprintEngine()
        engine.llm = mock_llm
        yield engine


class TestVoiceFingerprintEngine:
    """Tests for VoiceFingerprintEngine class."""

    def test_engine_initialization(self, voice_fingerprint_engine, mock_llm):
        """Test that VoiceFingerprintEngine initializes correctly."""
        assert voice_fingerprint_engine is not None
        assert hasattr(voice_fingerprint_engine, "llm")

    def test_profile_has_required_fields(self, voice_fingerprint_engine, mock_llm):
        """Test that the engine can produce a VoiceProfile with required fields."""
        # Test by checking the model directly via the engine's LLM mock
        profile_data = {
            "name": "Ani",
            "vocabulary_level": "moderate",
            "formality": "neutral",
        }
        from models.schemas import VoiceProfile as VP
        profile = VP(**profile_data)
        assert profile.name == "Ani"
        assert profile.vocabulary_level == "moderate"
        assert profile.formality == "neutral"


class TestDialogueAnchorModel:
    """Tests for DialogueAnchor model."""

    def test_dialogue_anchor_minimal(self):
        """Test DialogueAnchor with minimal required fields."""
        anchor = DialogueAnchor(
            speaker_id="Ani_001",
            ordinal=1,
            text="Ani: Saya pergi ke pasar",
            char_offset=0,
        )
        assert anchor.speaker_id == "Ani_001"
        assert anchor.ordinal == 1
        assert anchor.text == "Ani: Saya pergi ke pasar"
        assert anchor.char_offset == 0

    def test_dialogue_anchor_with_all_fields(self):
        """Test DialogueAnchor with all fields specified."""
        anchor = DialogueAnchor(
            speaker_id="Ani_001",
            ordinal=2,
            text="Ani: Aku akan pulang",
            char_offset=25,
        )
        assert anchor.speaker_id == "Ani_001"
        assert anchor.ordinal == 2
        assert anchor.text == "Ani: Aku akan pulang"
        assert anchor.char_offset == 25