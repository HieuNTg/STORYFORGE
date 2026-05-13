"""Tests for api.pipeline_output_builder.build_output_summary.

Covers:
  - conflict_web surfaces when story_draft has entries
  - conflict_web omitted when story_draft has empty/absent conflict_web
  - conflict_web omitted when no story_draft
"""
from unittest.mock import MagicMock

import pytest

from api.pipeline_output_builder import build_output_summary


def _make_conflict(cid="c1", ctype="external", chars=None, desc="Test conflict", arc="1-3"):
    c = MagicMock()
    c.conflict_id = cid
    c.conflict_type = ctype
    c.characters = chars or ["Alice", "Bob"]
    c.description = desc
    c.arc_range = arc
    return c


def _make_draft(conflict_web=None):
    draft = MagicMock()
    draft.title = "Test Story"
    draft.genre = "Tiên Hiệp"
    draft.synopsis = "A short synopsis."
    draft.characters = []
    draft.chapters = []
    draft.conflict_web = conflict_web or []
    return draft


def _make_output(draft=None, enhanced=None, simulation=None, quality=None, handoff=None):
    out = MagicMock()
    out.story_draft = draft
    out.enhanced_story = enhanced
    out.simulation_result = simulation
    out.quality_scores = quality or []
    out.handoff_health = handoff
    return out


# ---------------------------------------------------------------------------


def test_conflict_web_surfaced_when_present():
    conflict = _make_conflict(cid="c1", ctype="external", chars=["Alice", "Bob"], desc="Power struggle")
    draft = _make_draft(conflict_web=[conflict])
    output = _make_output(draft=draft)

    result = build_output_summary(output)

    assert "conflict_web" in result
    assert len(result["conflict_web"]) == 1
    cw = result["conflict_web"][0]
    assert cw["conflict_id"] == "c1"
    assert cw["conflict_type"] == "external"
    assert cw["characters"] == ["Alice", "Bob"]
    assert cw["description"] == "Power struggle"
    assert cw["arc_range"] == "1-3"


def test_conflict_web_omitted_when_empty():
    draft = _make_draft(conflict_web=[])
    output = _make_output(draft=draft)

    result = build_output_summary(output)

    assert "conflict_web" not in result


def test_conflict_web_omitted_when_no_draft():
    output = _make_output(draft=None)

    result = build_output_summary(output)

    assert "conflict_web" not in result
    assert result["has_draft"] is False


def test_conflict_web_multiple_entries():
    conflicts = [
        _make_conflict(cid="c1", desc="First conflict"),
        _make_conflict(cid="c2", ctype="internal", desc="Inner struggle"),
    ]
    draft = _make_draft(conflict_web=conflicts)
    output = _make_output(draft=draft)

    result = build_output_summary(output)

    assert len(result["conflict_web"]) == 2
    ids = [c["conflict_id"] for c in result["conflict_web"]]
    assert "c1" in ids
    assert "c2" in ids


def test_existing_fields_unaffected():
    """Adding conflict_web must not break other summary fields."""
    conflict = _make_conflict()
    draft = _make_draft(conflict_web=[conflict])
    output = _make_output(draft=draft)

    result = build_output_summary(output)

    assert result["has_draft"] is True
    assert "draft" in result
    assert result["draft"]["title"] == "Test Story"
