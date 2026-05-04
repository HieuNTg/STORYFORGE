"""Negative-path / degradation tests for Sprint 2 semantic verification (P7).

Covers:
- Foreshadowing contradiction (anchor says "found"; chapter says "never found")
- Wrong canonical name → substring fallback still detects via NER
- Single-chapter outline doesn't crash compute_outline_metrics
- STORYFORGE_SEMANTIC_STRICT=1 + critical structural finding raises
- Embedding service unavailable → keyword fallback (foreshadowing) and
  thread-coverage skip (structural detector)

All tests mock the embedding/NER services so they run hermetically.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from models.handoff_schemas import ForeshadowingSeed, NegotiatedChapterContract
from models.schemas import (
    Chapter,
    ChapterOutline,
    Character,
    ConflictEntry,
    ForeshadowingEntry,
)
from models.semantic_schemas import StructuralFindingType
from pipeline.semantic import SemanticVerificationError
from pipeline.semantic.foreshadowing_verifier import verify_payoffs
from pipeline.semantic.structural_detector import detect_structural_issues
from pipeline.layer1_story.outline_metrics import compute_outline_metrics
from services.embedding_service import vec_to_bytes


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _unit_vec(seed: int, dim: int = 16) -> np.ndarray:
    """Deterministic unit vector for cosine-similarity mocking."""
    rng = np.random.default_rng(seed)
    v = rng.standard_normal(dim).astype(np.float32)
    v /= np.linalg.norm(v)
    return v


def _bytes_for(vec: np.ndarray) -> bytes:
    return vec_to_bytes(vec)


def _make_emb_service(text_to_seed: dict[str, int]):
    """Build a MagicMock embedding service whose embed_batch returns
    deterministic bytes per input text. Cosine = dot of normalised vectors.
    """

    def _embed_batch(texts):
        return [_bytes_for(_unit_vec(text_to_seed.get(t, hash(t) & 0xFFFF))) for t in texts]

    svc = MagicMock()
    svc.is_available.return_value = True
    svc.embed_batch.side_effect = _embed_batch
    svc.similarity.side_effect = lambda a, b: float(
        np.dot(np.frombuffer(a, dtype="<f4"), np.frombuffer(b, dtype="<f4"))
    )
    svc.model_id = "mock-model"
    return svc


# ---------------------------------------------------------------------------
# 1. Contradiction — anchor and chapter span use shared keywords but invert
#    the action. Embedding similarity is too high to fully reject (this is
#    a known limitation), but we can verify the verifier returns the
#    embedding-method match rather than crashing.
# ---------------------------------------------------------------------------


class TestContradiction:
    def test_contradicting_chapter_does_not_crash(self, monkeypatch):
        """Contradicting span: anchor says 'finds sword', chapter says 'never finds the sword'.

        We don't claim the verifier perfectly distinguishes negation —
        the multilingual MiniLM is known weak there. We DO assert the
        verifier returns a match object rather than raising in default mode.
        """
        monkeypatch.delenv("STORYFORGE_SEMANTIC_STRICT", raising=False)

        seed = ForeshadowingSeed(
            id="contra-1",
            plant_chapter=1,
            payoff_chapter=1,
            description="Long finds the ancestral sword",
            semantic_anchor="Long finds the ancestral sword in the cave",
        )
        chapter = Chapter(
            chapter_number=1,
            title="Ch1",
            content="Long never finds the ancestral sword in the cave. The cave is empty.",
            word_count=12,
        )

        emb = _make_emb_service({})  # all unrelated → low similarity

        with patch(
            "pipeline.semantic.foreshadowing_verifier.get_embedding_service",
            return_value=emb,
        ):
            results = verify_payoffs([seed], [chapter], threshold=0.62)

        assert len(results) == 1
        m = results[0]
        assert m.seed_id == "contra-1"
        assert m.chapter_num == 1
        assert m.method == "embedding"

    def test_strict_mode_raises_on_missed(self, monkeypatch):
        """Strict mode + low-confidence match → SemanticVerificationError."""
        monkeypatch.setenv("STORYFORGE_SEMANTIC_STRICT", "1")

        seed = ForeshadowingSeed(
            id="strict-miss",
            plant_chapter=1,
            payoff_chapter=1,
            description="some payoff",
            semantic_anchor="anchor text alpha bravo",
        )
        chapter = Chapter(
            chapter_number=1,
            title="Ch1",
            content="Completely unrelated chapter content here, just words and stuff.",
            word_count=10,
        )

        # All texts get unrelated random vectors → cosine ~ 0
        emb = _make_emb_service({})

        with patch(
            "pipeline.semantic.foreshadowing_verifier.get_embedding_service",
            return_value=emb,
        ):
            with pytest.raises(SemanticVerificationError) as excinfo:
                verify_payoffs([seed], [chapter], threshold=0.62)
            assert "strict-miss" in str(excinfo.value)
            assert len(excinfo.value.missed_payoffs) == 1


# ---------------------------------------------------------------------------
# 2. Wrong canonical name → substring fallback
# ---------------------------------------------------------------------------


class TestNameSpellingFallback:
    def test_substring_fallback_when_ner_misses(self, monkeypatch):
        """NER returns empty set; the canonical-name regex still matches.

        This exercises the substring fallback in `_check_missing_characters`.
        """
        monkeypatch.delenv("STORYFORGE_SEMANTIC_STRICT", raising=False)

        chapter = Chapter(
            chapter_number=1,
            title="Ch1",
            content="Long bước vào động và tìm thấy thanh kiếm cổ.",
            word_count=10,
        )
        contract = NegotiatedChapterContract(
            chapter_num=1,
            pacing_type="rising",
            must_mention_characters=["Long"],
        )

        ner = MagicMock()
        ner.is_available.return_value = False  # forces substring fallback
        ner.extract_persons.return_value = set()

        emb = MagicMock()
        emb.is_available.return_value = False  # disable thread checks (N/A here)

        with (
            patch("pipeline.semantic.structural_detector.get_ner_service", return_value=ner),
            patch("pipeline.semantic.structural_detector.get_embedding_service", return_value=emb),
        ):
            findings = detect_structural_issues(chapter, contract, characters=[])

        # Substring matched "Long" → no missing-character finding
        missing = [
            f for f in findings if f.finding_type == StructuralFindingType.MISSING_CHARACTER
        ]
        assert missing == []

    def test_missing_when_neither_ner_nor_substring_match(self, monkeypatch):
        """When both NER and substring miss, finding is emitted (default mode)."""
        monkeypatch.delenv("STORYFORGE_SEMANTIC_STRICT", raising=False)

        chapter = Chapter(
            chapter_number=1,
            title="Ch1",
            content="Hôm nay trời mưa to và đường ngập nặng.",
            word_count=8,
        )
        contract = NegotiatedChapterContract(
            chapter_num=1,
            pacing_type="rising",
            must_mention_characters=["Long"],
        )

        ner = MagicMock()
        ner.is_available.return_value = False
        ner.extract_persons.return_value = set()
        emb = MagicMock()
        emb.is_available.return_value = False

        with (
            patch("pipeline.semantic.structural_detector.get_ner_service", return_value=ner),
            patch("pipeline.semantic.structural_detector.get_embedding_service", return_value=emb),
        ):
            findings = detect_structural_issues(chapter, contract, characters=[])

        critical = [f for f in findings if f.severity >= 0.80]
        assert len(critical) == 1
        assert critical[0].finding_type == StructuralFindingType.MISSING_CHARACTER
        assert "Long" in critical[0].description


# ---------------------------------------------------------------------------
# 3. Single-chapter outline edge case
# ---------------------------------------------------------------------------


class TestSingleChapterOutline:
    def test_single_chapter_outline_does_not_crash(self):
        """compute_outline_metrics must handle a 1-chapter outline gracefully."""
        outline = ChapterOutline(
            chapter_number=1,
            title="Mở đầu",
            summary="Long phát hiện thanh kiếm tổ tiên trong động.",
            key_events=["Long bước vào động", "Long tìm thấy thanh kiếm"],
            characters_involved=["Long"],
            pacing_type="setup",
        )
        characters = [Character(name="Long", role="protagonist", description="Hero")]
        conflict_web: list[ConflictEntry] = []
        foreshadowing: list[ForeshadowingEntry] = []

        # No embedding mock: real path falls back to string match for beat coverage
        # via _beat_coverage_string when service is unavailable. To keep this hermetic
        # we patch get_embedding_service to a stub that reports unavailable.
        emb = MagicMock()
        emb.is_available.return_value = False

        with patch(
            "pipeline.layer1_story.outline_metrics.get_embedding_service",
            return_value=emb,
        ):
            metrics = compute_outline_metrics(
                outlines=[outline],
                conflict_web=conflict_web,
                characters=characters,
                foreshadowing_plan=foreshadowing,
            )

        # Sanity bounds — none of the metrics should be NaN or out of [0, 1]
        assert metrics.num_chapters == 1
        assert metrics.num_characters == 1
        for field in (
            "conflict_web_density",
            "arc_trajectory_variance",
            "pacing_distribution_skew",
            "beat_coverage_ratio",
            "character_screen_time_gini",
            "overall_score",
        ):
            v = getattr(metrics, field)
            assert 0.0 <= v <= 1.0, f"{field}={v} out of range"


# ---------------------------------------------------------------------------
# 4. Strict mode + critical finding → SemanticVerificationError
# ---------------------------------------------------------------------------


class TestStrictCriticalFinding:
    def test_strict_raises_when_must_mention_missing(self, monkeypatch):
        monkeypatch.setenv("STORYFORGE_SEMANTIC_STRICT", "1")

        chapter = Chapter(
            chapter_number=2,
            title="Ch2",
            content="Một ngày bình thường, không có gì đặc biệt xảy ra.",
            word_count=10,
        )
        contract = NegotiatedChapterContract(
            chapter_num=2,
            pacing_type="rising",
            must_mention_characters=["Phong"],
        )

        ner = MagicMock()
        ner.is_available.return_value = False
        ner.extract_persons.return_value = set()
        emb = MagicMock()
        emb.is_available.return_value = False

        with (
            patch("pipeline.semantic.structural_detector.get_ner_service", return_value=ner),
            patch("pipeline.semantic.structural_detector.get_embedding_service", return_value=emb),
        ):
            with pytest.raises(SemanticVerificationError) as excinfo:
                detect_structural_issues(chapter, contract, characters=[])

        assert excinfo.value.critical_findings
        assert all(f.severity >= 0.80 for f in excinfo.value.critical_findings)


# ---------------------------------------------------------------------------
# 5. Embedding unavailable → degradation paths
# ---------------------------------------------------------------------------


class TestEmbeddingUnavailableDegradation:
    def test_foreshadowing_falls_back_to_keyword(self, monkeypatch):
        """When the embedding service is unavailable, verify_payoffs uses the
        keyword-overlap fallback. The fallback is a coarse heuristic; we
        assert the result is the keyword-method (not embedding) and that
        no exception is raised in default mode.
        """
        monkeypatch.delenv("STORYFORGE_SEMANTIC_STRICT", raising=False)

        seed = ForeshadowingSeed(
            id="kw-1",
            plant_chapter=1,
            payoff_chapter=1,
            description="Long finds ancestral sword",
            semantic_anchor="Long finds the ancestral sword in the cave",
        )
        chapter = Chapter(
            chapter_number=1,
            title="Ch1",
            content="Long discovers the ancestral sword hidden inside the cave.",
            word_count=10,
        )

        emb = MagicMock()
        emb.is_available.return_value = False

        with patch(
            "pipeline.semantic.foreshadowing_verifier.get_embedding_service",
            return_value=emb,
        ):
            results = verify_payoffs([seed], [chapter], threshold=0.62)

        assert len(results) == 1
        assert results[0].method == "keyword_fallback"

    def test_structural_detector_skips_thread_check(self, monkeypatch, caplog):
        """When embedding service is unavailable, thread-coverage check is
        skipped with a warning (no exception, no false-positive findings)."""
        monkeypatch.delenv("STORYFORGE_SEMANTIC_STRICT", raising=False)

        chapter = Chapter(
            chapter_number=1,
            title="Ch1",
            content="Long bước vào động và tìm thấy thanh kiếm cổ.",
            word_count=10,
        )
        contract = NegotiatedChapterContract(
            chapter_num=1,
            pacing_type="rising",
            must_mention_characters=["Long"],
            threads_advance=["main_quest"],
        )

        ner = MagicMock()
        ner.is_available.return_value = False
        ner.extract_persons.return_value = set()
        emb = MagicMock()
        emb.is_available.return_value = False

        with (
            patch("pipeline.semantic.structural_detector.get_ner_service", return_value=ner),
            patch("pipeline.semantic.structural_detector.get_embedding_service", return_value=emb),
        ):
            with caplog.at_level("WARNING"):
                findings = detect_structural_issues(chapter, contract, characters=[])

        # No thread-coverage findings (would be MISSING_KEY_EVENT)
        thread_findings = [
            f for f in findings if f.finding_type == StructuralFindingType.MISSING_KEY_EVENT
        ]
        assert thread_findings == []
        # And a warning was logged
        assert any("Embedding service unavailable" in rec.message for rec in caplog.records)
