"""Verify the user's original idea is preserved on StoryDraft after L1.

Backstops the idea-fidelity fix: schema must carry `original_idea` and
`idea_summary_for_chapters`, defaults remain backward-compatible.
"""
from __future__ import annotations

from models.schemas import StoryDraft


def _mk_draft(**kw):
    base = dict(
        title="t", genre="g", synopsis="s",
        characters=[], world={"name": "x", "description": "y"}, outlines=[],
    )
    base.update(kw)
    return StoryDraft(**base)


def test_original_idea_defaults_empty_for_backward_compat():
    d = _mk_draft()
    assert d.original_idea == ""
    assert d.idea_summary_for_chapters == ""


def test_original_idea_is_persisted_verbatim():
    idea = "Lý Phong gặp Tô Vân tại Lạc Dương."
    d = _mk_draft(original_idea=idea)
    assert d.original_idea == idea
    assert d.idea_summary_for_chapters == ""


def test_idea_summary_persisted_when_set():
    summary = "Tóm tắt giữ tên: Lý Phong, Tô Vân, Lạc Dương."
    d = _mk_draft(original_idea="x" * 4000, idea_summary_for_chapters=summary)
    assert d.idea_summary_for_chapters == summary
    assert len(d.original_idea) == 4000
