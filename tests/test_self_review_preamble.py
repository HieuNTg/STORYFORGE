"""Tests: SelfReviewer.revise() must strip LLM preambles from revised output.

Revisions re-run the LLM and can re-introduce meta-prefaces like
"Đây là phiên bản đã chỉnh sửa của Chương 3..." even when the input was clean.
"""

from unittest.mock import patch

from services.pipeline.self_review import SelfReviewer


class TestRevisePreambleStripping:
    def test_revise_strips_vn_preamble(self):
        bad = (
            "Đây là phiên bản đã chỉnh sửa của Chương 3, đã khắc phục các "
            "điểm yếu được nêu ra.\n\n"
            "Hùng nín thở, lắng nghe tiếng bước chân vọng lại từ hành lang."
        )
        with patch.object(SelfReviewer, "__init__", lambda self, threshold=3.0: None):
            reviewer = SelfReviewer()
            with patch.object(reviewer, "llm", create=True) as mock_llm:
                mock_llm.generate.return_value = bad
                out = reviewer.revise(
                    content="seed", weaknesses=["pacing chậm"], word_count=2000,
                )
        assert out.startswith("Hùng nín thở")
        assert "phiên bản" not in out.lower()

    def test_revise_strips_en_preamble(self):
        bad = (
            "Here is the revised version of Chapter 3, with the requested "
            "improvements.\n\n"
            "The mountain stood silent under the morning mist."
        )
        with patch.object(SelfReviewer, "__init__", lambda self, threshold=3.0: None):
            reviewer = SelfReviewer()
            with patch.object(reviewer, "llm", create=True) as mock_llm:
                mock_llm.generate.return_value = bad
                out = reviewer.revise(
                    content="seed", weaknesses=["voice"], word_count=2000,
                )
        assert out.startswith("The mountain")

    def test_revise_leaves_clean_prose_untouched(self):
        clean = "Hùng bước vào phòng. Bóng tối phủ kín mọi góc."
        with patch.object(SelfReviewer, "__init__", lambda self, threshold=3.0: None):
            reviewer = SelfReviewer()
            with patch.object(reviewer, "llm", create=True) as mock_llm:
                mock_llm.generate.return_value = clean
                out = reviewer.revise(
                    content="seed", weaknesses=["x"], word_count=2000,
                )
        assert out == clean

    def test_revise_returns_original_on_llm_failure(self):
        original = "Original chapter content."
        with patch.object(SelfReviewer, "__init__", lambda self, threshold=3.0: None):
            reviewer = SelfReviewer()
            with patch.object(reviewer, "llm", create=True) as mock_llm:
                mock_llm.generate.side_effect = RuntimeError("LLM down")
                out = reviewer.revise(
                    content=original, weaknesses=["x"], word_count=2000,
                )
        assert out == original
