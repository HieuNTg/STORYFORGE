"""Tests for Phase 2: Chapter Contract System."""

import json
from unittest.mock import MagicMock

from models.narrative_schemas import ArcWaypoint, ChapterContract
from models.schemas import ChapterOutline, Character, ForeshadowingEntry, PlotThread
from pipeline.layer1_story.chapter_contract_builder import (
    build_contract,
    format_contract_for_prompt,
    validate_contract_compliance,
)


def _make_outline(ch=1, chars=None, pacing="rising", emotional="", plants=None, payoffs=None):
    return ChapterOutline(
        chapter_number=ch,
        title=f"Chapter {ch}",
        summary="Test summary",
        characters_involved=chars or [],
        pacing_type=pacing,
        emotional_arc=emotional,
        foreshadowing_plants=plants or [],
        payoff_references=payoffs or [],
    )


def _make_char(name="Alice", waypoints=None):
    c = Character(name=name, role="main", personality="brave", background="test")
    if waypoints:
        c.arc_waypoints = [wp.model_dump() for wp in waypoints]
    return c


def _make_thread(tid="t1", status="open", planted=1, last_mentioned=1, chars=None):
    return PlotThread(
        thread_id=tid,
        description="Test thread",
        planted_chapter=planted,
        status=status,
        involved_characters=chars or [],
        last_mentioned_chapter=last_mentioned,
    )


def _make_foreshadow(hint="dark omen", plant=3, payoff=8, planted=False, paid=False):
    return ForeshadowingEntry(
        hint=hint, plant_chapter=plant, payoff_chapter=payoff,
        planted=planted, paid_off=paid,
    )


class TestBuildContract:
    def test_basic_contract(self):
        outline = _make_outline(ch=5, chars=["Alice", "Bob"], pacing="climax", emotional="tense")
        contract = build_contract(5, outline)
        assert contract.chapter_number == 5
        assert contract.pacing_type == "climax"
        assert contract.emotional_endpoint == "tense"
        assert "Alice" in contract.must_mention_characters
        assert "Bob" in contract.must_mention_characters

    def test_thread_advancement(self):
        outline = _make_outline(ch=10, chars=["Alice"])
        threads = [
            _make_thread("t1", status="open", planted=1, last_mentioned=4, chars=["Alice"]),
            _make_thread("t2", status="open", planted=8, last_mentioned=9, chars=["Bob"]),
            _make_thread("t3", status="resolved", planted=1, last_mentioned=1, chars=["Alice"]),
        ]
        contract = build_contract(10, outline, threads=threads)
        assert "t1" in contract.must_advance_threads  # stale (10-4=6>=5) + involves Alice
        assert "t3" not in contract.must_advance_threads  # resolved

    def test_stale_thread_prioritized(self):
        outline = _make_outline(ch=20, chars=["Carol"])
        threads = [
            _make_thread("stale", status="open", planted=1, last_mentioned=5, chars=["Dave"]),
        ]
        contract = build_contract(20, outline, threads=threads)
        assert "stale" in contract.must_advance_threads  # 20-5=15 >= 5

    def test_foreshadowing_seeds_and_payoffs(self):
        outline = _make_outline(ch=3)
        foreshadowing = [
            _make_foreshadow("omen", plant=3, payoff=8, planted=False),
            _make_foreshadow("hint2", plant=5, payoff=3, planted=True, paid=False),
            _make_foreshadow("done", plant=1, payoff=3, planted=True, paid=True),
        ]
        contract = build_contract(3, outline, foreshadowing_plan=foreshadowing)
        assert "omen" in contract.must_plant_seeds
        assert "hint2" in contract.must_payoff
        assert "done" not in contract.must_payoff  # already paid off

    def test_arc_targets_from_waypoints(self):
        wp = ArcWaypoint(
            stage_name="crisis", chapter_range=[4, 8],
            progress_pct=0.6, emotional_state="anxious",
        )
        char = _make_char("Alice", waypoints=[wp])
        outline = _make_outline(ch=5)
        contract = build_contract(5, outline, characters=[char])
        assert "Alice" in contract.character_arc_targets
        assert "crisis" in contract.character_arc_targets["Alice"]
        assert "60%" in contract.character_arc_targets["Alice"]

    def test_previous_failures_propagated(self):
        outline = _make_outline(ch=5)
        contract = build_contract(5, outline, previous_failures=["missed thread t1"])
        assert "missed thread t1" in contract.previous_contract_failures

    def test_thread_cap(self):
        outline = _make_outline(ch=50, chars=["Alice"])
        threads = [
            _make_thread(f"t{i}", status="open", planted=1, last_mentioned=1, chars=["Alice"])
            for i in range(20)
        ]
        contract = build_contract(50, outline, threads=threads)
        assert len(contract.must_advance_threads) <= 5


class TestFormatContract:
    def test_basic_format(self):
        contract = ChapterContract(
            chapter_number=3,
            must_advance_threads=["t1", "t2"],
            must_plant_seeds=["omen"],
            pacing_type="rising",
            must_mention_characters=["Alice"],
        )
        text = format_contract_for_prompt(contract)
        assert "HỢP ĐỒNG CHƯƠNG 3" in text
        assert "t1" in text
        assert "omen" in text
        assert "Alice" in text

    def test_previous_failures_shown(self):
        contract = ChapterContract(
            chapter_number=5,
            previous_contract_failures=["missed omen", "thread t1 not advanced"],
        )
        text = format_contract_for_prompt(contract)
        assert "CHƯƠNG TRƯỚC ĐÃ BỎ LỠ" in text
        assert "missed omen" in text

    def test_cap_at_800_chars(self):
        contract = ChapterContract(
            chapter_number=1,
            must_advance_threads=[f"thread_{i}_very_long_name" for i in range(50)],
            must_plant_seeds=[f"seed_{i}_long_description" for i in range(50)],
            must_mention_characters=[f"character_{i}" for i in range(50)],
        )
        text = format_contract_for_prompt(contract)
        assert len(text) <= 800

    def test_empty_contract_minimal(self):
        contract = ChapterContract(chapter_number=1)
        text = format_contract_for_prompt(contract)
        assert "HỢP ĐỒNG CHƯƠNG 1" in text
        assert "rising" in text  # default pacing


class TestValidateCompliance:
    def test_successful_validation(self):
        mock_llm = MagicMock()
        mock_llm.generate.return_value = json.dumps({
            "compliance_score": 0.85,
            "met": ["thread advanced", "seed planted"],
            "failures": ["arc target missed"],
        })
        contract = ChapterContract(
            chapter_number=1,
            must_advance_threads=["t1"],
            must_plant_seeds=["omen"],
        )
        result = validate_contract_compliance(mock_llm, "Chapter content here...", contract)
        assert result["compliance_score"] == 0.85
        assert len(result["met"]) == 2
        assert len(result["failures"]) == 1

    def test_markdown_json_extraction(self):
        mock_llm = MagicMock()
        mock_llm.generate.return_value = '```json\n{"compliance_score": 0.9, "met": [], "failures": []}\n```'
        contract = ChapterContract(chapter_number=1)
        result = validate_contract_compliance(mock_llm, "content", contract)
        assert result["compliance_score"] == 0.9

    def test_malformed_response_returns_zero(self):
        mock_llm = MagicMock()
        mock_llm.generate.return_value = "This is not JSON at all"
        contract = ChapterContract(chapter_number=1)
        result = validate_contract_compliance(mock_llm, "content", contract)
        assert result["compliance_score"] == 0.0
        assert result["failures"] == []

    def test_llm_exception_returns_zero(self):
        mock_llm = MagicMock()
        mock_llm.generate.side_effect = Exception("API error")
        contract = ChapterContract(chapter_number=1)
        result = validate_contract_compliance(mock_llm, "content", contract)
        assert result["compliance_score"] == 0.0
