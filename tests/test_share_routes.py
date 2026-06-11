"""Tests for api/share_routes.py — library-story share + gallery metadata."""

from __future__ import annotations

import os
import sys

import pytest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    from fastapi.testclient import TestClient
    from fastapi import FastAPI

    _HAS_FASTAPI = True
except ImportError:
    _HAS_FASTAPI = False

from services.share_manager import ShareManager


def _make_client():
    from api.share_routes import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def sandbox_mgr(tmp_path, monkeypatch):
    """ShareManager bound to a temp dir, patched into the routes module."""
    shares_dir = str(tmp_path / "shares")
    monkeypatch.setattr(ShareManager, "SHARES_DIR", shares_dir)
    monkeypatch.setattr(
        ShareManager, "SHARES_INDEX", os.path.join(shares_dir, "index.json")
    )
    mgr = ShareManager()
    with patch("api.share_routes._share_manager", mgr):
        yield mgr


def _library_payload(**overrides):
    payload = {
        "title": "Truyện Thử Nghiệm",
        "genre": "tien_hiep",
        "synopsis": "Tóm tắt.",
        "chapters": [
            {
                "title": "Chương 1",
                "content": "Nội dung chương một.",
                "summary": "",
                "images": ["/media/output/s/pages/ch01_page01.png"],
            },
            {"title": "Chương 2", "content": "Nội dung hai.", "images": []},
        ],
        "characters": [
            {
                "name": "Kiên",
                "role": "protagonist",
                "personality": "kiên định",
                "motivation": "báo thù",
            },
        ],
        "is_public": True,
    }
    payload.update(overrides)
    return payload


@pytest.mark.skipif(not _HAS_FASTAPI, reason="FastAPI not installed")
class TestCreateFromLibrary:
    @pytest.fixture(autouse=True)
    def setup(self, sandbox_mgr):
        self.mgr = sandbox_mgr
        self.client = _make_client()

    def test_creates_public_share_with_cover(self):
        resp = self.client.post("/share/create-from-library", json=_library_payload())
        assert resp.status_code == 200
        body = resp.json()
        assert body["story_title"] == "Truyện Thử Nghiệm"
        assert body["is_public"] is True
        assert body["cover_url"] == "/media/output/s/pages/ch01_page01.png"
        assert body["url"] == f"/api/share/{body['share_id']}"

    def test_share_html_contains_comic_pages_and_prose(self):
        resp = self.client.post("/share/create-from-library", json=_library_payload())
        share_id = resp.json()["share_id"]
        html_path = self.mgr.get_share(share_id)
        content = open(html_path, encoding="utf-8").read()
        assert 'src="/media/output/s/pages/ch01_page01.png"' in content
        assert "comic-pages" in content
        assert "Nội dung chương một." in content
        assert "Kiên" in content  # character card

    def test_unsafe_image_urls_dropped(self):
        payload = _library_payload()
        payload["chapters"][0]["images"] = [
            "https://evil.example/x.png",
            "/media/../data/config.json",
        ]
        resp = self.client.post("/share/create-from-library", json=payload)
        assert resp.status_code == 200
        assert resp.json()["cover_url"] == ""
        html_path = self.mgr.get_share(resp.json()["share_id"])
        content = open(html_path, encoding="utf-8").read()
        assert "evil.example" not in content

    def test_appears_in_gallery_with_metadata(self):
        self.client.post("/share/create-from-library", json=_library_payload())
        resp = self.client.get("/share/gallery")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["genre"] == "tien_hiep"
        assert items[0]["cover_url"] == "/media/output/s/pages/ch01_page01.png"

    def test_private_share_not_in_gallery(self):
        self.client.post(
            "/share/create-from-library", json=_library_payload(is_public=False)
        )
        resp = self.client.get("/share/gallery")
        assert resp.json()["total"] == 0

    def test_empty_chapters_rejected(self):
        resp = self.client.post(
            "/share/create-from-library", json=_library_payload(chapters=[])
        )
        assert resp.status_code == 422

    def test_missing_title_rejected(self):
        payload = _library_payload()
        del payload["title"]
        resp = self.client.post("/share/create-from-library", json=payload)
        assert resp.status_code == 422

    def test_replace_share_id_replaces_old_entry(self):
        first = self.client.post(
            "/share/create-from-library", json=_library_payload()
        ).json()
        second = self.client.post(
            "/share/create-from-library",
            json=_library_payload(replace_share_id=first["share_id"]),
        ).json()
        assert second["share_id"] != first["share_id"]
        # Old share is gone — gallery holds exactly the replacement
        assert self.mgr.get_share(first["share_id"]) is None
        items = self.client.get("/share/gallery").json()["items"]
        assert [it["share_id"] for it in items] == [second["share_id"]]

    def test_bogus_replace_share_id_ignored(self):
        # Traversal-looking ids fail the strict regex and are silently ignored
        resp = self.client.post(
            "/share/create-from-library",
            json=_library_payload(replace_share_id="../etc/passwd"),
        )
        assert resp.status_code == 200
        assert self.client.get("/share/gallery").json()["total"] == 1
