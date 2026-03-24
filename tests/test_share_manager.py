"""Test ShareManager service."""
import os
import pytest
from unittest.mock import patch
from models.schemas import StoryDraft, Chapter
from services.share_manager import ShareManager


@pytest.fixture
def share_mgr(tmp_path, monkeypatch):
    shares_dir = str(tmp_path / "shares")
    monkeypatch.setattr(ShareManager, "SHARES_DIR", shares_dir)
    monkeypatch.setattr(ShareManager, "SHARES_INDEX", os.path.join(shares_dir, "index.json"))
    return ShareManager()


def _make_story():
    return StoryDraft(
        title="Test Story", genre="Fantasy",
        chapters=[Chapter(chapter_number=1, title="Ch1", content="Content here")],
    )


def test_create_share(share_mgr):
    story = _make_story()
    share = share_mgr.create_share(story)
    assert share.share_id != ""
    assert share.story_title == "Test Story"
    assert share.html_path != ""


def test_get_share_valid(share_mgr):
    story = _make_story()
    share = share_mgr.create_share(story, expires_days=30)
    path = share_mgr.get_share(share.share_id)
    assert path is not None


def test_get_share_nonexistent(share_mgr):
    assert share_mgr.get_share("nonexistent") is None


def test_list_shares(share_mgr):
    story = _make_story()
    share_mgr.create_share(story)
    share_mgr.create_share(story)
    shares = share_mgr.list_shares()
    assert len(shares) == 2


def test_delete_share(share_mgr):
    story = _make_story()
    share = share_mgr.create_share(story)
    assert share_mgr.delete_share(share.share_id) is True
    assert share_mgr.get_share(share.share_id) is None


def test_delete_nonexistent(share_mgr):
    assert share_mgr.delete_share("nonexistent") is False
