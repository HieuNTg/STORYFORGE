"""Regression tests: a failed judge call is not a failed chapter.

`validate_chapter_against_contract` and `validate_chapter_voice` returned
`passed=False, score=0.0` when the *validation LLM call itself* errored. The
enhancer could not tell that apart from a genuine violation, so one transient
429 triggered a full chapter re-enhance (~12-15 calls) and, on the voice path,
dropped through the binary revert floor and threw away the enhanced dialogue.
"""

from unittest.mock import MagicMock

from models.handoff_schemas import NegotiatedChapterContract
from pipeline.layer2_enhance.chapter_contract import (
    VoiceContract,
    validate_chapter_against_contract,
    validate_chapter_voice,
)


def _contract(n=1):
    return NegotiatedChapterContract(chapter_num=n, pacing_type="rising")


def _rate_limited_llm():
    llm = MagicMock()
    llm.generate_json.side_effect = RuntimeError("429 Too Many Requests")
    return llm


def _malformed_llm():
    llm = MagicMock()
    llm.generate_json.return_value = ["not", "a", "dict"]
    return llm


class TestContractValidationErrorFlag:
    def test_provider_error_is_flagged_as_error(self):
        result = validate_chapter_against_contract(
            _rate_limited_llm(), "nội dung chương", _contract()
        )
        assert result.passed is False
        assert result.error is True, "a 429 is indistinguishable from a real failure"

    def test_malformed_reply_is_flagged_as_error(self):
        result = validate_chapter_against_contract(
            _malformed_llm(), "nội dung chương", _contract()
        )
        assert result.error is True

    def test_genuine_failure_is_not_flagged_as_error(self):
        """A real verdict must still drive remediation."""
        llm = MagicMock()
        llm.generate_json.return_value = {
            "drama_actual": 0.2,
            "missing_escalations": ["đối đầu"],
            "missing_subtext": [],
            "missing_causal_refs": [],
            "violated_patterns": [],
            "reason": "thiếu cao trào",
        }
        result = validate_chapter_against_contract(llm, "nội dung", _contract())
        assert result.error is False


class TestVoiceValidationErrorFlag:
    def _voice_contract(self):
        return VoiceContract(
            chapter_number=1,
            per_character={"Lan": {"tics": ["ừm"], "tone": "lạnh"}},
        )

    def test_provider_error_is_flagged_as_error(self):
        result = validate_chapter_voice(
            _rate_limited_llm(), "nội dung", self._voice_contract()
        )
        assert result.passed is False
        assert result.error is True

    def test_malformed_reply_is_flagged_as_error(self):
        result = validate_chapter_voice(
            _malformed_llm(), "nội dung", self._voice_contract()
        )
        assert result.error is True

    def test_errored_validation_scores_zero_which_is_below_every_revert_floor(self):
        """Documents why the flag matters: 0.0 always trips the binary revert."""
        result = validate_chapter_voice(
            _rate_limited_llm(), "nội dung", self._voice_contract()
        )
        assert result.overall_compliance == 0.0
        assert result.error is True, "without the flag this reverts good dialogue"
