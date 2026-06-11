"""Test ShareManager service."""

import os
import pytest
from models.schemas import StoryDraft, Chapter
from services.share_manager import ShareManager


@pytest.fixture
def share_mgr(tmp_path, monkeypatch):
    shares_dir = str(tmp_path / "shares")
    monkeypatch.setattr(ShareManager, "SHARES_DIR", shares_dir)
    monkeypatch.setattr(
        ShareManager, "SHARES_INDEX", os.path.join(shares_dir, "index.json")
    )
    return ShareManager()


def _make_story():
    return StoryDraft(
        title="Test Story",
        genre="Fantasy",
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


def test_share_captures_genre_and_comic_cover(share_mgr):
    story = StoryDraft(
        title="Comic Story",
        genre="tien_hiep",
        chapters=[
            Chapter(chapter_number=1, title="Ch1", content="x"),  # no images
            Chapter(
                chapter_number=2,
                title="Ch2",
                content="y",
                images=["/media/output/s/pages/ch02_page01.png"],
            ),
        ],
    )
    share = share_mgr.create_share(story, is_public=True)
    assert share.genre == "tien_hiep"
    # Cover = first /media image across chapters
    assert share.cover_url == "/media/output/s/pages/ch02_page01.png"
    # Survives the index round-trip (what /api/share/gallery reads)
    listed = share_mgr.list_public_shares()
    assert listed[0].genre == "tien_hiep"
    assert listed[0].cover_url == "/media/output/s/pages/ch02_page01.png"


def test_share_cover_ignores_unsafe_urls(share_mgr):
    story = StoryDraft(
        title="S",
        genre="Fantasy",
        chapters=[
            Chapter(
                chapter_number=1,
                title="C",
                content="x",
                images=["https://evil.example/a.png", "/media/../etc"],
            )
        ],
    )
    share = share_mgr.create_share(story)
    assert share.cover_url == ""


def test_legacy_index_entries_without_new_fields_still_load(share_mgr):
    # Simulate a pre-existing index.json entry written before genre/cover_url
    share_mgr.shares.append(
        {
            "share_id": "legacy0001",
            "story_title": "Old",
            "created_at": "2026-01-01T00:00:00",
            "html_path": "",
            "expires_at": "2099-01-01T00:00:00",
            "is_public": True,
        }
    )
    listed = share_mgr.list_public_shares()
    legacy = [s for s in listed if s.share_id == "legacy0001"][0]
    assert legacy.genre == ""
    assert legacy.cover_url == ""
