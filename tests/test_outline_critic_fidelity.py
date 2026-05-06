"""Verify outline_critic proper-noun fidelity guard re-rolls when names are missing.

Literal mode: if outline coverage of idea proper nouns < floor, trigger one
LLM-driven revision pass. Thematic mode: skip the guard entirely.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from models.schemas import Character, ChapterOutline, WorldSetting
from pipeline.layer1_story.outline_critic import (
    PROPER_NOUN_COVERAGE_FLOOR,
    _extract_proper_nouns,
    critique_and_revise,
    proper_noun_fidelity_check,
)


IDEA = "Lý Phong và Tô Vân tới Lạc Dương tu luyện ở Thiên Sơn."

CHARS = [Character(name="Hùng", role="protagonist", personality="brave", background="hero")]
WORLD = WorldSetting(name="W", description="d")

OUTLINES_MISSING = [
    ChapterOutline(chapter_number=1, title="Khởi đầu",
                   summary="Một người trẻ bắt đầu hành trình",
                   characters_involved=["Hùng"], pacing_type="setup", arc_id=1),
    ChapterOutline(chapter_number=2, title="Chuyến đi",
                   summary="Họ đi xa",
                   characters_involved=["Hùng"], pacing_type="rising", arc_id=1),
]

OUTLINES_FULL = [
    ChapterOutline(chapter_number=1, title="Lý Phong tới Lạc Dương",
                   summary="Tô Vân đợi tại Thiên Sơn để gặp Lý Phong",
                   characters_involved=["Lý Phong", "Tô Vân"],
                   pacing_type="setup", arc_id=1),
]


def test_extract_finds_multi_token_names():
    nouns = _extract_proper_nouns(IDEA)
    assert "Lý Phong" in nouns
    assert "Tô Vân" in nouns
    assert "Lạc Dương" in nouns
    assert "Thiên Sơn" in nouns


def test_fidelity_check_flags_missing_nouns():
    cov, missing = proper_noun_fidelity_check(IDEA, OUTLINES_MISSING)
    assert cov < PROPER_NOUN_COVERAGE_FLOOR
    assert "Lý Phong" in missing
    assert "Tô Vân" in missing


def test_fidelity_check_passes_full_coverage():
    cov, missing = proper_noun_fidelity_check(IDEA, OUTLINES_FULL)
    assert cov == 1.0
    assert missing == []


def test_fidelity_check_no_idea_means_pass():
    cov, missing = proper_noun_fidelity_check("", OUTLINES_MISSING)
    assert cov == 1.0
    assert missing == []


def test_literal_mode_triggers_reroll_when_coverage_below_floor():
    llm = MagicMock()
    # Make revise_outline_from_critique return outlines with all names present
    revised_payload = {
        "outlines": [
            {
                "chapter_number": 1,
                "title": "Lý Phong tới Lạc Dương",
                "summary": "Tô Vân và Lý Phong gặp ở Thiên Sơn",
                "key_events": [],
                "characters_involved": ["Lý Phong", "Tô Vân"],
                "emotional_arc": "",
                "pacing_type": "setup",
                "arc_id": 1,
                "foreshadowing_plants": [],
                "payoff_references": [],
            }
        ]
    }
    llm.generate_json.return_value = revised_payload

    with patch("pipeline.layer1_story.outline_critic.score_outline",
               return_value=(MagicMock(model_dump=lambda: {}, overall_score=1.0), False, [])):
        outlines, critique = critique_and_revise(
            llm, OUTLINES_MISSING, CHARS, WORLD, "synopsis", "fantasy",
            max_rounds=1,
            enable_llm_critic=False,
            idea=IDEA,
            idea_fidelity_mode="literal",
        )

    # Revision call MUST have happened (fidelity guard triggered re-roll)
    assert llm.generate_json.called
    # Returned outlines now contain the missing names
    assert any("Lý Phong" in o.title or "Lý Phong" in o.summary for o in outlines)
    assert critique["idea_fidelity_coverage"] == 1.0
    assert critique["idea_fidelity_missing"] == []


def test_thematic_mode_skips_fidelity_guard():
    llm = MagicMock()
    with patch("pipeline.layer1_story.outline_critic.score_outline",
               return_value=(MagicMock(model_dump=lambda: {}, overall_score=1.0), False, [])):
        _, critique = critique_and_revise(
            llm, OUTLINES_MISSING, CHARS, WORLD, "synopsis", "fantasy",
            max_rounds=1,
            enable_llm_critic=False,
            idea=IDEA,
            idea_fidelity_mode="thematic",
        )
    # No re-roll attempted in thematic mode
    assert not llm.generate_json.called
    # Coverage stays at default 1.0 sentinel (guard skipped)
    assert critique["idea_fidelity_coverage"] == 1.0
