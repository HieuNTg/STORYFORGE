"""Tests for StoryAnalyzer - conflict_web merge logic."""

import pytest
from unittest.mock import MagicMock, patch

from models.schemas import (
    Character, Relationship, RelationType, ConflictEntry, StoryDraft,
)
from pipeline.layer2_enhance.analyzer import StoryAnalyzer


def _draft(title="T"):
    return StoryDraft(
        title=title,
        genre="fantasy",
        characters=[Character(name="A", role="chính", personality="brave")],
        synopsis="A story",
    )


def _rel(a, b, tension=0.3, rel_type=RelationType.ALLY):
    return Relationship(character_a=a, character_b=b, relation_type=rel_type, tension=tension)


def _conflict(chars, intensity=3, description="conflict"):
    return ConflictEntry(
        conflict_id="c1",
        conflict_type="external",
        characters=chars,
        description=description,
        intensity=intensity,
    )


class TestMergeConflictWeb:
    """Unit tests for StoryAnalyzer._merge_conflict_web (static method)."""

    def test_new_pair_appended(self):
        llm_rels = [_rel("A", "B", tension=0.2)]
        conflicts = [_conflict(["C", "D"], intensity=4)]
        result = StoryAnalyzer._merge_conflict_web(llm_rels, conflicts)
        assert len(result) == 2
        pairs = [(r.character_a, r.character_b) for r in result]
        assert ("C", "D") in pairs

    def test_higher_tension_wins(self):
        llm_rels = [_rel("A", "B", tension=0.2)]
        # intensity=5 → tension=1.0
        conflicts = [_conflict(["A", "B"], intensity=5)]
        result = StoryAnalyzer._merge_conflict_web(llm_rels, conflicts)
        assert len(result) == 1
        assert result[0].tension == pytest.approx(1.0)

    def test_lower_l1_tension_not_override(self):
        llm_rels = [_rel("A", "B", tension=0.9)]
        # intensity=1 → tension=0.2 — should NOT override the higher 0.9
        conflicts = [_conflict(["A", "B"], intensity=1)]
        result = StoryAnalyzer._merge_conflict_web(llm_rels, conflicts)
        assert len(result) == 1
        assert result[0].tension == pytest.approx(0.9)

    def test_pair_order_independent(self):
        """Conflict with chars ["B", "A"] should merge with rel (A, B)."""
        llm_rels = [_rel("A", "B", tension=0.2)]
        conflicts = [_conflict(["B", "A"], intensity=5)]
        result = StoryAnalyzer._merge_conflict_web(llm_rels, conflicts)
        assert len(result) == 1
        assert result[0].tension == pytest.approx(1.0)

    def test_empty_conflict_web_unchanged(self):
        llm_rels = [_rel("A", "B", tension=0.5)]
        result = StoryAnalyzer._merge_conflict_web(llm_rels, [])
        assert len(result) == 1
        assert result[0].tension == pytest.approx(0.5)

    def test_intensity_to_tension_mapping(self):
        """intensity 1-5 maps to tension 0.2-1.0."""
        for intensity, expected in [(1, 0.2), (2, 0.4), (3, 0.6), (4, 0.8), (5, 1.0)]:
            llm_rels = []
            conflicts = [_conflict(["X", "Y"], intensity=intensity)]
            result = StoryAnalyzer._merge_conflict_web(llm_rels, conflicts)
            assert result[0].tension == pytest.approx(expected)

    def test_single_char_entry_skipped(self):
        llm_rels = [_rel("A", "B", tension=0.3)]
        conflicts = [_conflict(["A"], intensity=5)]
        result = StoryAnalyzer._merge_conflict_web(llm_rels, conflicts)
        assert len(result) == 1  # no new entry added

    def test_multiple_conflicts_all_merged(self):
        llm_rels = []
        conflicts = [
            _conflict(["A", "B"], intensity=3),
            _conflict(["C", "D"], intensity=5),
        ]
        result = StoryAnalyzer._merge_conflict_web(llm_rels, conflicts)
        assert len(result) == 2


class TestAnalyzeWithConflictWeb:
    """Integration test: analyze() passes conflict_web to merge."""

    def test_analyze_no_conflict_web(self):
        analyzer = StoryAnalyzer()
        mock_result = {
            "relationships": [
                {"character_a": "A", "character_b": "B", "relation_type": "đối_thủ", "tension": 0.4}
            ],
            "conflict_points": [],
            "untapped_drama": [],
            "character_weaknesses": {},
        }
        with patch.object(analyzer.llm, "generate_json", return_value=mock_result):
            result = analyzer.analyze(_draft())
        assert len(result["relationships"]) == 1

    def test_analyze_merges_conflict_web(self):
        analyzer = StoryAnalyzer()
        mock_result = {
            "relationships": [
                {"character_a": "A", "character_b": "B", "relation_type": "đối_thủ", "tension": 0.2}
            ],
            "conflict_points": [],
            "untapped_drama": [],
            "character_weaknesses": {},
        }
        conflicts = [_conflict(["A", "B"], intensity=5)]  # → tension 1.0
        with patch.object(analyzer.llm, "generate_json", return_value=mock_result):
            result = analyzer.analyze(_draft(), conflict_web=conflicts)
        assert len(result["relationships"]) == 1
        assert result["relationships"][0].tension == pytest.approx(1.0)

    def test_analyze_appends_new_conflict_pair(self):
        analyzer = StoryAnalyzer()
        mock_result = {
            "relationships": [
                {"character_a": "A", "character_b": "B", "relation_type": "đối_thủ", "tension": 0.2}
            ],
            "conflict_points": [],
            "untapped_drama": [],
            "character_weaknesses": {},
        }
        conflicts = [_conflict(["C", "D"], intensity=3)]  # new pair
        with patch.object(analyzer.llm, "generate_json", return_value=mock_result):
            result = analyzer.analyze(_draft(), conflict_web=conflicts)
        assert len(result["relationships"]) == 2
