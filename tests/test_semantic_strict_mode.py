"""Tests verifying the consolidated is_strict_mode() helper and that all three
modules (P3 foreshadowing_verifier, P4 structural_detector, P5 outline_critic)
honour it correctly (Sprint 2 P6).
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# is_strict_mode() helper
# ---------------------------------------------------------------------------


class TestIsStrictMode:
    def test_returns_false_when_unset(self, monkeypatch):
        monkeypatch.delenv("STORYFORGE_SEMANTIC_STRICT", raising=False)
        from pipeline.semantic import is_strict_mode
        assert is_strict_mode() is False

    def test_returns_true_when_set_to_1(self, monkeypatch):
        monkeypatch.setenv("STORYFORGE_SEMANTIC_STRICT", "1")
        from pipeline.semantic import is_strict_mode
        assert is_strict_mode() is True

    def test_returns_false_when_set_to_0(self, monkeypatch):
        monkeypatch.setenv("STORYFORGE_SEMANTIC_STRICT", "0")
        from pipeline.semantic import is_strict_mode
        assert is_strict_mode() is False

    def test_returns_false_for_other_values(self, monkeypatch):
        monkeypatch.setenv("STORYFORGE_SEMANTIC_STRICT", "true")
        from pipeline.semantic import is_strict_mode
        assert is_strict_mode() is False

    def test_strips_whitespace(self, monkeypatch):
        monkeypatch.setenv("STORYFORGE_SEMANTIC_STRICT", " 1 ")
        from pipeline.semantic import is_strict_mode
        assert is_strict_mode() is True

    def test_no_direct_env_reads_in_p3(self):
        """P3 (foreshadowing_verifier) must not read STORYFORGE_SEMANTIC_STRICT directly."""
        import inspect
        import pipeline.semantic.foreshadowing_verifier as mod
        src = inspect.getsource(mod)
        # The module-level _STRICT_ENV constant should be gone; direct env.get should be gone
        assert 'os.environ.get("STORYFORGE_SEMANTIC_STRICT"' not in src
        assert "_STRICT_ENV" not in src

    def test_no_direct_env_reads_in_p4(self):
        """P4 (structural_detector) must not read STORYFORGE_SEMANTIC_STRICT directly."""
        import inspect
        import pipeline.semantic.structural_detector as mod
        src = inspect.getsource(mod)
        assert 'os.environ.get("STORYFORGE_SEMANTIC_STRICT"' not in src
        assert "_STRICT_ENV" not in src

    def test_no_direct_env_reads_in_p5(self):
        """P5 (outline_critic) must not read STORYFORGE_SEMANTIC_STRICT directly."""
        import inspect
        import pipeline.layer1_story.outline_critic as mod
        src = inspect.getsource(mod)
        assert 'os.environ.get("STORYFORGE_SEMANTIC_STRICT"' not in src


# ---------------------------------------------------------------------------
# P3 — foreshadowing_verifier honours is_strict_mode()
# ---------------------------------------------------------------------------


class _FakeChapter:
    def __init__(self, num, content):
        self.chapter_number = num
        self.content = content


class TestForeshadowingVerifierStrictMode:
    def _make_seed(self, payoff_ch):
        """Minimal ForeshadowingEntry-like object with payoff_chapter."""
        seed = MagicMock()
        seed.payoff_chapter = payoff_ch
        seed.plant_chapter = payoff_ch
        seed.hint = "the hero draws a legendary sword"
        seed.paid_off = False
        seed.planted = False
        seed.planted_confidence = 0.0
        return seed

    def test_strict_raises_on_missed(self, monkeypatch):
        """STORYFORGE_SEMANTIC_STRICT=1 + missed payoff → SemanticVerificationError."""
        monkeypatch.setenv("STORYFORGE_SEMANTIC_STRICT", "1")

        # Mock embedding service as unavailable → keyword fallback with low ratio
        mock_svc = MagicMock()
        mock_svc.is_available.return_value = False

        with patch("pipeline.semantic.foreshadowing_verifier.get_embedding_service", return_value=mock_svc):
            from pipeline.semantic import SemanticVerificationError
            from pipeline.semantic.foreshadowing_verifier import verify_payoffs

            seed = self._make_seed(payoff_ch=1)
            seed.hint = "zxzxzx totally unrelated unique nonsense"  # won't match
            chapter = _FakeChapter(1, "The hero walked through the forest quietly.")

            with pytest.raises(SemanticVerificationError):
                verify_payoffs([seed], [chapter], threshold=0.62)

    def test_default_mode_does_not_raise_on_missed(self, monkeypatch):
        """Default mode: missed payoff → no exception (warn and continue)."""
        monkeypatch.delenv("STORYFORGE_SEMANTIC_STRICT", raising=False)

        mock_svc = MagicMock()
        mock_svc.is_available.return_value = False

        with patch("pipeline.semantic.foreshadowing_verifier.get_embedding_service", return_value=mock_svc):
            from pipeline.semantic.foreshadowing_verifier import verify_payoffs

            seed = self._make_seed(payoff_ch=1)
            seed.hint = "zxzxzx totally unrelated unique nonsense"
            chapter = _FakeChapter(1, "The hero walked through the forest quietly.")

            results = verify_payoffs([seed], [chapter], threshold=0.62)
            assert results  # results returned, no exception


# ---------------------------------------------------------------------------
# P4 — structural_detector honours is_strict_mode()
# ---------------------------------------------------------------------------


class TestStructuralDetectorStrictMode:
    def _make_chapter(self, content="Some content."):
        ch = MagicMock()
        ch.chapter_number = 1
        ch.content = content
        return ch

    def _make_contract(self, must_mention=None, threads_advance=None):
        c = MagicMock()
        c.must_mention_characters = must_mention or ["Lan"]
        c.threads_advance = threads_advance or []
        return c

    def test_strict_raises_on_critical_finding(self, monkeypatch):
        """STORYFORGE_SEMANTIC_STRICT=1 + critical finding → SemanticVerificationError."""
        monkeypatch.setenv("STORYFORGE_SEMANTIC_STRICT", "1")

        mock_ner = MagicMock()
        mock_ner.is_available.return_value = False  # fallback to substring
        mock_emb = MagicMock()
        mock_emb.is_available.return_value = False

        with (
            patch("pipeline.semantic.structural_detector.get_ner_service", return_value=mock_ner),
            patch("pipeline.semantic.structural_detector.get_embedding_service", return_value=mock_emb),
        ):
            from pipeline.semantic import SemanticVerificationError
            from pipeline.semantic.structural_detector import detect_structural_issues

            chapter = self._make_chapter("This chapter has no mention of the required character.")
            contract = self._make_contract(must_mention=["ZxZxZxMissingChar"])

            with pytest.raises(SemanticVerificationError):
                detect_structural_issues(chapter, contract, characters=[])

    def test_default_mode_does_not_raise_on_critical(self, monkeypatch):
        """Default mode: critical finding → no exception (findings returned)."""
        monkeypatch.delenv("STORYFORGE_SEMANTIC_STRICT", raising=False)

        mock_ner = MagicMock()
        mock_ner.is_available.return_value = False
        mock_emb = MagicMock()
        mock_emb.is_available.return_value = False

        with (
            patch("pipeline.semantic.structural_detector.get_ner_service", return_value=mock_ner),
            patch("pipeline.semantic.structural_detector.get_embedding_service", return_value=mock_emb),
        ):
            from pipeline.semantic.structural_detector import detect_structural_issues

            chapter = self._make_chapter("No mention of missing character here.")
            contract = self._make_contract(must_mention=["ZxZxZxMissingChar"])

            findings = detect_structural_issues(chapter, contract, characters=[])
            assert any(f.severity >= 0.80 for f in findings)


# ---------------------------------------------------------------------------
# P5 — outline_critic honours is_strict_mode()
# ---------------------------------------------------------------------------


class TestOutlineCriticStrictMode:
    def _make_metrics(self, overall_score=0.30):
        """Mock OutlineMetrics with a specific overall_score."""
        m = MagicMock()
        m.overall_score = overall_score
        m.conflict_web_density = 0.50
        m.arc_trajectory_variance = 0.50
        m.pacing_distribution_skew = 0.50
        m.beat_coverage_ratio = 0.50
        m.character_screen_time_gini = 0.20
        return m

    def test_strict_raises_when_score_below_floor(self, monkeypatch):
        """STORYFORGE_SEMANTIC_STRICT=1 + score < 0.50 → SemanticVerificationError."""
        monkeypatch.setenv("STORYFORGE_SEMANTIC_STRICT", "1")

        metrics = self._make_metrics(overall_score=0.30)  # below STRICT_RAISE_THRESHOLD=0.50

        # compute_outline_metrics is imported inside score_outline locally,
        # so we patch it at the source module level.
        with patch(
            "pipeline.layer1_story.outline_metrics.compute_outline_metrics",
            return_value=metrics,
        ):
            from pipeline.semantic import SemanticVerificationError
            from pipeline.layer1_story.outline_critic import score_outline

            with pytest.raises(SemanticVerificationError):
                score_outline(outlines=[], characters=[])

    def test_strict_does_not_raise_when_score_above_floor(self, monkeypatch):
        """STORYFORGE_SEMANTIC_STRICT=1 + score >= 0.50 → no raise."""
        monkeypatch.setenv("STORYFORGE_SEMANTIC_STRICT", "1")

        metrics = self._make_metrics(overall_score=0.55)  # above STRICT_RAISE_THRESHOLD

        with patch(
            "pipeline.layer1_story.outline_metrics.compute_outline_metrics",
            return_value=metrics,
        ):
            from pipeline.layer1_story.outline_critic import score_outline
            # Should not raise
            result_metrics, should_rewrite, failing = score_outline(outlines=[], characters=[])
        assert result_metrics.overall_score == 0.55

    def test_default_mode_does_not_raise_when_low_score(self, monkeypatch):
        """Default mode: low score → no exception."""
        monkeypatch.delenv("STORYFORGE_SEMANTIC_STRICT", raising=False)

        metrics = self._make_metrics(overall_score=0.20)

        with patch(
            "pipeline.layer1_story.outline_metrics.compute_outline_metrics",
            return_value=metrics,
        ):
            from pipeline.layer1_story.outline_critic import score_outline
            # Should not raise
            result_metrics, should_rewrite, failing = score_outline(outlines=[], characters=[])
        assert result_metrics.overall_score == 0.20
