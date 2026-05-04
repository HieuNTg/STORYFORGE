"""Unit tests for Sprint 2 P4 structural detector.

Covers both the new NER+embedding-based `detect_structural_issues` function
(pipeline.semantic.structural_detector) and the legacy adapter
(`StructuralFinding.to_legacy_issue()`).

spaCy and the embedding service are mocked throughout — no model download
required to run this suite.
"""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from models.semantic_schemas import (
    StructuralFinding,
    StructuralFindingType,
)
from pipeline.layer2_enhance.structural_detector import (
    StructuralIssue,
    StructuralIssueType,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_chapter(number: int = 1, content: str = "Nội dung chương bình thường."):
    ch = MagicMock()
    ch.chapter_number = number
    ch.content = content
    return ch


def _make_contract(
    must_mention: list[str] | None = None,
    threads: list[str] | None = None,
    pacing_type: str = "rising",
    ch_num: int = 1,
):
    from models.handoff_schemas import NegotiatedChapterContract
    return NegotiatedChapterContract(
        chapter_num=ch_num,
        pacing_type=pacing_type,
        must_mention_characters=must_mention or [],
        threads_advance=threads or [],
    )


def _make_character(name: str):
    ch = MagicMock()
    ch.name = name
    return ch


# A fake L2-normalised vector (dot product with itself = 1.0)
def _unit_vec(dim: int = 4, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    v = rng.standard_normal(dim).astype(np.float32)
    v /= np.linalg.norm(v)
    return v


def _vec_bytes(v: np.ndarray) -> bytes:
    from services.embedding_service import vec_to_bytes
    return vec_to_bytes(v)


# ---------------------------------------------------------------------------
# Mock factories
# ---------------------------------------------------------------------------

def _mock_ner_service(persons: set[str]):
    """Return a mock NERService that always returns *persons*."""
    svc = MagicMock()
    svc.is_available.return_value = True
    svc.extract_persons.return_value = persons
    return svc


def _mock_ner_unavailable():
    svc = MagicMock()
    svc.is_available.return_value = False
    svc.extract_persons.return_value = set()
    return svc


def _mock_emb_service(text_to_vec: dict[str, np.ndarray] | None = None):
    """Return a mock EmbeddingService whose embed_batch returns vecs by text."""
    text_to_vec = text_to_vec or {}
    svc = MagicMock()
    svc.is_available.return_value = True

    def _embed_batch(texts):
        result = []
        for t in texts:
            v = text_to_vec.get(t, _unit_vec(seed=abs(hash(t)) % 100))
            result.append(_vec_bytes(v))
        return result

    svc.embed_batch.side_effect = _embed_batch
    return svc


def _mock_emb_unavailable():
    svc = MagicMock()
    svc.is_available.return_value = False
    return svc


# ---------------------------------------------------------------------------
# Tests: MISSING_CHARACTER
# ---------------------------------------------------------------------------

class TestMissingCharacter:
    def test_all_present_via_ner_no_finding(self):
        """NER finds all must-mention chars → no findings."""
        ch = _make_chapter(content="Nguyễn Long và Minh đang chiến đấu.")
        contract = _make_contract(must_mention=["Nguyễn Long", "Minh"])
        with (
            patch("pipeline.semantic.structural_detector.get_ner_service",
                  return_value=_mock_ner_service({"Nguyễn Long", "Minh"})),
            patch("pipeline.semantic.structural_detector.get_embedding_service",
                  return_value=_mock_emb_unavailable()),
        ):
            from pipeline.semantic.structural_detector import detect_structural_issues
            findings = detect_structural_issues(ch, contract, [])
        assert all(f.finding_type != StructuralFindingType.MISSING_CHARACTER for f in findings)

    def test_missing_one_character_is_critical(self):
        """One must-mention character absent → MISSING_CHARACTER severity=critical."""
        ch = _make_chapter(content="Đây là chương không nhắc đến ai.")
        contract = _make_contract(must_mention=["Nguyễn Long"])
        with (
            patch("pipeline.semantic.structural_detector.get_ner_service",
                  return_value=_mock_ner_service(set())),
            patch("pipeline.semantic.structural_detector.get_embedding_service",
                  return_value=_mock_emb_unavailable()),
        ):
            from pipeline.semantic.structural_detector import detect_structural_issues
            findings = detect_structural_issues(ch, contract, [])
        assert len(findings) == 1
        f = findings[0]
        assert f.finding_type == StructuralFindingType.MISSING_CHARACTER
        assert f.severity >= 0.80  # critical

    def test_substring_fallback_finds_name(self):
        """NER misses, but word-boundary substring detects name."""
        # 'Long' appears as a whole word in content
        ch = _make_chapter(content="Trong đêm tối, Long bước ra sân.")
        contract = _make_contract(must_mention=["Long"])
        with (
            patch("pipeline.semantic.structural_detector.get_ner_service",
                  return_value=_mock_ner_service(set())),  # NER returns nothing
            patch("pipeline.semantic.structural_detector.get_embedding_service",
                  return_value=_mock_emb_unavailable()),
        ):
            from pipeline.semantic.structural_detector import detect_structural_issues
            findings = detect_structural_issues(ch, contract, [])
        # Should find via substring fallback — no MISSING_CHARACTER finding
        assert all(f.finding_type != StructuralFindingType.MISSING_CHARACTER for f in findings)

    def test_substring_word_boundary_does_not_match_partial(self):
        """'Long' should NOT match 'Long-form' due to word-boundary check."""
        ch = _make_chapter(content="Đây là một bài viết Long-form về triết học.")
        contract = _make_contract(must_mention=["Long"])
        with (
            patch("pipeline.semantic.structural_detector.get_ner_service",
                  return_value=_mock_ner_service(set())),
            patch("pipeline.semantic.structural_detector.get_embedding_service",
                  return_value=_mock_emb_unavailable()),
        ):
            from pipeline.semantic.structural_detector import detect_structural_issues
            findings = detect_structural_issues(ch, contract, [])
        # "Long" inside "Long-form" should NOT satisfy the check
        missing = [f for f in findings if f.finding_type == StructuralFindingType.MISSING_CHARACTER]
        assert len(missing) == 1

    def test_vietnamese_full_name_via_ner(self):
        """NER returns 'Nguyễn Long' → must-mention 'Nguyễn Long' satisfied."""
        ch = _make_chapter(content="Nguyễn Long đứng trước cửa nhà.")
        contract = _make_contract(must_mention=["Nguyễn Long"])
        with (
            patch("pipeline.semantic.structural_detector.get_ner_service",
                  return_value=_mock_ner_service({"Nguyễn Long"})),
            patch("pipeline.semantic.structural_detector.get_embedding_service",
                  return_value=_mock_emb_unavailable()),
        ):
            from pipeline.semantic.structural_detector import detect_structural_issues
            findings = detect_structural_issues(ch, contract, [])
        assert not any(f.finding_type == StructuralFindingType.MISSING_CHARACTER for f in findings)

    def test_vietnamese_surname_only_fallback(self):
        """'Long' (first name only) found via substring when full name contract uses 'Long'."""
        ch = _make_chapter(content="Long cười và gật đầu.")
        contract = _make_contract(must_mention=["Long"])
        with (
            patch("pipeline.semantic.structural_detector.get_ner_service",
                  return_value=_mock_ner_service(set())),  # NER misses bare first name
            patch("pipeline.semantic.structural_detector.get_embedding_service",
                  return_value=_mock_emb_unavailable()),
        ):
            from pipeline.semantic.structural_detector import detect_structural_issues
            findings = detect_structural_issues(ch, contract, [])
        assert not any(f.finding_type == StructuralFindingType.MISSING_CHARACTER for f in findings)


# ---------------------------------------------------------------------------
# Tests: DROPPED_THREAD (embedding)
# ---------------------------------------------------------------------------

class TestDroppedThread:
    def test_high_sim_thread_not_flagged(self):
        """Thread label embeds close to chapter spans → no finding."""
        thread_label = "cuộc chiến bí mật"
        span = "Họ đang chiến đấu trong bí mật."
        shared_vec = _unit_vec(seed=42)

        ch = _make_chapter(content=span)
        contract = _make_contract(threads=[thread_label])

        text_to_vec = {thread_label: shared_vec, span: shared_vec}

        with (
            patch("pipeline.semantic.structural_detector.get_ner_service",
                  return_value=_mock_ner_service(set())),
            patch("pipeline.semantic.structural_detector.get_embedding_service",
                  return_value=_mock_emb_service(text_to_vec)),
        ):
            from pipeline.semantic import structural_detector as sd
            # Reload to pick up mock
            findings = sd.detect_structural_issues(ch, contract, [], thread_threshold=0.50)
        assert not any(f.finding_type == StructuralFindingType.MISSING_KEY_EVENT for f in findings)

    def test_low_sim_thread_flagged(self):
        """Thread label embeds far from chapter spans → MISSING_KEY_EVENT finding."""
        thread_label = "cuộc chiến bí mật"
        span = "Hôm nay trời nắng đẹp."
        # Orthogonal vectors → cosine sim = 0
        vec_thread = _unit_vec(seed=1)
        vec_span = _unit_vec(seed=99)
        # Make them orthogonal
        vec_span -= vec_span.dot(vec_thread) * vec_thread
        vec_span /= np.linalg.norm(vec_span)

        ch = _make_chapter(content=span)
        contract = _make_contract(threads=[thread_label])

        text_to_vec = {thread_label: vec_thread, span: vec_span}

        with (
            patch("pipeline.semantic.structural_detector.get_ner_service",
                  return_value=_mock_ner_service(set())),
            patch("pipeline.semantic.structural_detector.get_embedding_service",
                  return_value=_mock_emb_service(text_to_vec)),
        ):
            from pipeline.semantic import structural_detector as sd
            findings = sd.detect_structural_issues(ch, contract, [], thread_threshold=0.50)
        dropped = [f for f in findings if f.finding_type == StructuralFindingType.MISSING_KEY_EVENT]
        assert len(dropped) >= 1

    def test_empty_threads_no_embedding_call(self):
        """No threads → embedding service never called."""
        ch = _make_chapter(content="Normal content.")
        contract = _make_contract(threads=[])
        mock_emb = _mock_emb_service()

        with (
            patch("pipeline.semantic.structural_detector.get_ner_service",
                  return_value=_mock_ner_service(set())),
            patch("pipeline.semantic.structural_detector.get_embedding_service",
                  return_value=mock_emb),
        ):
            from pipeline.semantic import structural_detector as sd
            findings = sd.detect_structural_issues(ch, contract, [], thread_threshold=0.50)
        mock_emb.embed_batch.assert_not_called()
        assert findings == []

    def test_embedding_unavailable_skips_thread_check(self):
        """Embedding service down → thread checks skipped, no exception."""
        ch = _make_chapter(content="Some content here.")
        contract = _make_contract(threads=["revenge plot"])

        with (
            patch("pipeline.semantic.structural_detector.get_ner_service",
                  return_value=_mock_ner_service(set())),
            patch("pipeline.semantic.structural_detector.get_embedding_service",
                  return_value=_mock_emb_unavailable()),
        ):
            from pipeline.semantic import structural_detector as sd
            findings = sd.detect_structural_issues(ch, contract, [], thread_threshold=0.50)
        # No thread findings (skipped), no crash
        assert not any(f.finding_type == StructuralFindingType.MISSING_KEY_EVENT for f in findings)


# ---------------------------------------------------------------------------
# Tests: DANGLING_REFERENCE
# ---------------------------------------------------------------------------

class TestDanglingReference:
    def test_unknown_person_is_dangling(self):
        """NER finds a name not in cast or threads → DANGLING_REFERENCE."""
        ch = _make_chapter(content="Thám tử Hoàng xuất hiện bất ngờ.")
        contract = _make_contract(must_mention=[], threads=[])
        characters = [_make_character("Minh"), _make_character("Lan")]

        with (
            patch("pipeline.semantic.structural_detector.get_ner_service",
                  return_value=_mock_ner_service({"Hoàng"})),
            patch("pipeline.semantic.structural_detector.get_embedding_service",
                  return_value=_mock_emb_unavailable()),
        ):
            from pipeline.semantic import structural_detector as sd
            findings = sd.detect_structural_issues(ch, contract, characters)
        dangling = [
            f for f in findings
            if f.finding_type == StructuralFindingType.MISSING_CHARACTER
            and "Dangling" in f.description
        ]
        assert len(dangling) == 1

    def test_cast_member_not_dangling(self):
        """NER finds cast member → no dangling reference."""
        ch = _make_chapter(content="Minh bước vào phòng.")
        contract = _make_contract(must_mention=["Minh"])
        characters = [_make_character("Minh")]

        with (
            patch("pipeline.semantic.structural_detector.get_ner_service",
                  return_value=_mock_ner_service({"Minh"})),
            patch("pipeline.semantic.structural_detector.get_embedding_service",
                  return_value=_mock_emb_unavailable()),
        ):
            from pipeline.semantic import structural_detector as sd
            findings = sd.detect_structural_issues(ch, contract, characters)
        dangling = [f for f in findings if "Dangling" in f.description]
        assert dangling == []

    def test_ner_unavailable_no_dangling_check(self):
        """When NER is down, dangling check is skipped entirely."""
        ch = _make_chapter(content="Some unknown person appeared.")
        contract = _make_contract()

        with (
            patch("pipeline.semantic.structural_detector.get_ner_service",
                  return_value=_mock_ner_unavailable()),
            patch("pipeline.semantic.structural_detector.get_embedding_service",
                  return_value=_mock_emb_unavailable()),
        ):
            from pipeline.semantic import structural_detector as sd
            findings = sd.detect_structural_issues(ch, contract, [])
        assert findings == []


# ---------------------------------------------------------------------------
# Tests: Strict mode
# ---------------------------------------------------------------------------

class TestStrictMode:
    def test_critical_finding_raises_in_strict_mode(self, monkeypatch):
        """STORYFORGE_SEMANTIC_STRICT=1 + critical finding → SemanticVerificationError."""
        monkeypatch.setenv("STORYFORGE_SEMANTIC_STRICT", "1")
        ch = _make_chapter(content="Không có ai trong chương này.")
        contract = _make_contract(must_mention=["Bí Ẩn"])

        with (
            patch("pipeline.semantic.structural_detector.get_ner_service",
                  return_value=_mock_ner_service(set())),
            patch("pipeline.semantic.structural_detector.get_embedding_service",
                  return_value=_mock_emb_unavailable()),
        ):
            from pipeline.semantic import structural_detector as sd
            from pipeline.semantic import SemanticVerificationError
            with pytest.raises(SemanticVerificationError) as exc_info:
                sd.detect_structural_issues(ch, contract, [])
        assert exc_info.value.critical_findings

    def test_no_critical_no_raise_in_strict_mode(self, monkeypatch):
        """Strict mode with no critical findings does not raise."""
        monkeypatch.setenv("STORYFORGE_SEMANTIC_STRICT", "1")
        ch = _make_chapter(content="Bình thường không có vấn đề gì.")
        contract = _make_contract()

        with (
            patch("pipeline.semantic.structural_detector.get_ner_service",
                  return_value=_mock_ner_service(set())),
            patch("pipeline.semantic.structural_detector.get_embedding_service",
                  return_value=_mock_emb_unavailable()),
        ):
            from pipeline.semantic import structural_detector as sd
            findings = sd.detect_structural_issues(ch, contract, [])
        # Should not raise
        assert isinstance(findings, list)

    def test_critical_finding_no_raise_without_strict(self, monkeypatch):
        """Without strict mode, critical finding is returned but no exception."""
        monkeypatch.delenv("STORYFORGE_SEMANTIC_STRICT", raising=False)
        ch = _make_chapter(content="Không có nhân vật nào ở đây.")
        contract = _make_contract(must_mention=["Nhân Vật Quan Trọng"])

        with (
            patch("pipeline.semantic.structural_detector.get_ner_service",
                  return_value=_mock_ner_service(set())),
            patch("pipeline.semantic.structural_detector.get_embedding_service",
                  return_value=_mock_emb_unavailable()),
        ):
            from pipeline.semantic import structural_detector as sd
            findings = sd.detect_structural_issues(ch, contract, [])
        assert len(findings) == 1
        assert findings[0].severity >= 0.80


# ---------------------------------------------------------------------------
# Tests: to_legacy_issue() adapter
# ---------------------------------------------------------------------------

class TestToLegacyIssueAdapter:
    def test_missing_character_maps_to_wrong_characters(self):
        """`MISSING_CHARACTER` → legacy `WRONG_CHARACTERS`."""
        finding = StructuralFinding(
            finding_type=StructuralFindingType.MISSING_CHARACTER,
            chapter_num=3,
            severity=0.9,
            description="Missing char",
            fix_hint="Add the char",
            detection_method="ner",
            evidence=(),
            confidence=1.0,
        )
        legacy = finding.to_legacy_issue()
        assert isinstance(legacy, StructuralIssue)
        assert legacy.issue_type == StructuralIssueType.WRONG_CHARACTERS
        assert legacy.chapter_number == 3
        assert legacy.severity == pytest.approx(0.9)

    def test_missing_key_event_maps_correctly(self):
        finding = StructuralFinding(
            finding_type=StructuralFindingType.MISSING_KEY_EVENT,
            chapter_num=1,
            severity=0.75,
            description="Missing event",
            fix_hint="Add event",
            detection_method="embedding",
            evidence=(),
            confidence=0.8,
        )
        legacy = finding.to_legacy_issue()
        assert legacy.issue_type == StructuralIssueType.MISSING_KEY_EVENT

    def test_pacing_violation_maps_correctly(self):
        finding = StructuralFinding(
            finding_type=StructuralFindingType.PACING_VIOLATION,
            chapter_num=5,
            severity=0.7,
            description="Pacing off",
            fix_hint="Fix pacing",
            detection_method="embedding",
            evidence=(),
            confidence=0.6,
        )
        legacy = finding.to_legacy_issue()
        assert legacy.issue_type == StructuralIssueType.PACING_VIOLATION
        assert legacy.fix_hint == "Fix pacing"

    def test_missed_arc_waypoint_maps_correctly(self):
        finding = StructuralFinding(
            finding_type=StructuralFindingType.MISSED_ARC_WAYPOINT,
            chapter_num=7,
            severity=0.7,
            description="Missed waypoint",
            fix_hint="Add waypoint",
            detection_method="embedding",
            evidence=(),
            confidence=0.7,
        )
        legacy = finding.to_legacy_issue()
        assert legacy.issue_type == StructuralIssueType.MISSED_ARC_WAYPOINT


# ---------------------------------------------------------------------------
# Tests: Legacy dataclass preserved
# ---------------------------------------------------------------------------

class TestLegacyDataclassPreserved:
    def test_structural_issue_dataclass_still_importable(self):
        """Ensure legacy StructuralIssue still importable from old module."""
        from pipeline.layer2_enhance.structural_detector import (
            StructuralIssue,
            StructuralIssueType,
        )
        issue = StructuralIssue(
            issue_type=StructuralIssueType.PACING_VIOLATION,
            severity=0.7,
            description="test",
            chapter_number=1,
            fix_hint="hint",
        )
        assert issue.severity == pytest.approx(0.7)

    def test_structural_issue_detector_class_removed(self):
        """StructuralIssueDetector class should no longer exist in legacy module."""
        import pipeline.layer2_enhance.structural_detector as legacy_mod
        assert not hasattr(legacy_mod, "StructuralIssueDetector"), (
            "StructuralIssueDetector should have been removed in P4"
        )


# ---------------------------------------------------------------------------
# Tests: No-op / edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_content_chapter(self):
        """Chapter with empty content does not raise."""
        ch = _make_chapter(content="")
        contract = _make_contract(must_mention=["Minh"])

        with (
            patch("pipeline.semantic.structural_detector.get_ner_service",
                  return_value=_mock_ner_service(set())),
            patch("pipeline.semantic.structural_detector.get_embedding_service",
                  return_value=_mock_emb_unavailable()),
        ):
            from pipeline.semantic import structural_detector as sd
            findings = sd.detect_structural_issues(ch, contract, [])
        # Missing character should be flagged even on empty content
        missing = [f for f in findings if f.finding_type == StructuralFindingType.MISSING_CHARACTER]
        assert len(missing) == 1

    def test_none_content_safe(self):
        """Chapter with None content is handled gracefully."""
        ch = MagicMock()
        ch.chapter_number = 1
        ch.content = None
        contract = _make_contract()

        with (
            patch("pipeline.semantic.structural_detector.get_ner_service",
                  return_value=_mock_ner_service(set())),
            patch("pipeline.semantic.structural_detector.get_embedding_service",
                  return_value=_mock_emb_unavailable()),
        ):
            from pipeline.semantic import structural_detector as sd
            findings = sd.detect_structural_issues(ch, contract, [])
        assert isinstance(findings, list)

    def test_no_must_mention_no_character_findings(self):
        """Empty must_mention contract → no character findings."""
        ch = _make_chapter(content="Some story content here.")
        contract = _make_contract(must_mention=[])

        with (
            patch("pipeline.semantic.structural_detector.get_ner_service",
                  return_value=_mock_ner_service(set())),
            patch("pipeline.semantic.structural_detector.get_embedding_service",
                  return_value=_mock_emb_unavailable()),
        ):
            from pipeline.semantic import structural_detector as sd
            findings = sd.detect_structural_issues(ch, contract, [])
        missing = [f for f in findings if f.finding_type == StructuralFindingType.MISSING_CHARACTER]
        assert missing == []
