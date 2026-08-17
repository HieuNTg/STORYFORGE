"""Tests for api.pipeline_output_builder.build_output_summary.

Covers:
  - conflict_web surfaces when story_draft has entries
  - conflict_web omitted when story_draft has empty/absent conflict_web
  - conflict_web omitted when no story_draft
"""

from unittest.mock import MagicMock


from api.pipeline_output_builder import build_output_summary


def _make_conflict(
    cid="c1", ctype="external", chars=None, desc="Test conflict", arc="1-3"
):
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


def _make_output(
    draft=None, enhanced=None, simulation=None, quality=None, handoff=None
):
    out = MagicMock()
    out.story_draft = draft
    out.enhanced_story = enhanced
    out.simulation_result = simulation
    out.quality_scores = quality or []
    out.handoff_health = handoff
    return out


# ---------------------------------------------------------------------------


def test_conflict_web_surfaced_when_present():
    conflict = _make_conflict(
        cid="c1", ctype="external", chars=["Alice", "Bob"], desc="Power struggle"
    )
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


class TestRosterAndSummariesSurvive:
    """The Library persists this payload verbatim and the continuation pipeline
    reads it back, so dropping fields here silently degrades continuations."""

    def _draft_with_content(self):
        from models.schemas import Chapter, Character, StoryDraft

        return StoryDraft(
            title="Phụng Hoàng Tàn",
            genre="Tiên Hiệp",
            synopsis="Một câu chuyện.",
            characters=[
                Character(
                    name="Lý Hữu",
                    role="chính",
                    personality="Cương trực",
                    background="Xuất thân hàn vi",
                    motivation="Tìm sư phụ",
                    internal_conflict="Trung nghĩa hay tự do",
                    secret="Hậu duệ phụng hoàng",
                )
            ],
            chapters=[
                Chapter(
                    chapter_number=1,
                    title="Khởi đầu",
                    content="Nội dung.",
                    summary="Lý Hữu rời quê.",
                )
            ],
        )

    def test_chapter_summary_is_emitted(self):
        out = _make_output(draft=self._draft_with_content())
        summary = build_output_summary(out)
        assert summary["draft"]["chapters"][0]["summary"] == "Lý Hữu rời quê."

    def test_character_sheet_is_emitted_in_full(self):
        out = _make_output(draft=self._draft_with_content())
        char = build_output_summary(out)["draft"]["characters"][0]
        assert char["name"] == "Lý Hữu"
        assert char["role"] == "chính"
        assert char["personality"] == "Cương trực"
        assert char["background"] == "Xuất thân hàn vi"
        assert char["secret"] == "Hậu duệ phụng hoàng"
        assert char["internal_conflict"] == "Trung nghĩa hay tự do"
        assert char["motivation"] == "Tìm sư phụ"

    def test_enhanced_chapters_carry_summary(self):
        from models.schemas import Chapter, EnhancedStory

        enhanced = EnhancedStory(
            title="Phụng Hoàng Tàn",
            genre="Tiên Hiệp",
            chapters=[
                Chapter(
                    chapter_number=1,
                    title="Khởi đầu",
                    content="Bản nâng cao.",
                    summary="Lý Hữu rời quê.",
                )
            ],
        )
        out = _make_output(draft=self._draft_with_content(), enhanced=enhanced)
        summary = build_output_summary(out)
        assert summary["enhanced"]["chapters"][0]["summary"] == "Lý Hữu rời quê."
