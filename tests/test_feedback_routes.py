"""Route tests for api/feedback_routes.py (previously untested).

Open when no access token is configured; with STORYFORGE_ACCESS_TOKEN set,
the router requires it. The module-level in-memory
store is cleared around each test so tests stay independent.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import feedback_routes


@pytest.fixture(autouse=True)
def _clean_store():
    feedback_routes._store.clear()
    yield
    feedback_routes._store.clear()


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(feedback_routes.router, prefix="/api")
    return TestClient(app)


def _submit(client: TestClient, rating: int, comment: str | None = None):
    return client.post(
        "/api/feedback",
        json={"story_id": "truyen-1", "rating": rating, "comment": comment},
    )


class TestSubmitFeedback:
    def test_submit_stores_entry(self):
        resp = _submit(_client(), 5, "hay quá")
        assert resp.status_code == 201
        assert resp.json() == {"status": "ok", "story_id": "truyen-1"}
        assert len(feedback_routes._store["truyen-1"]) == 1
        assert feedback_routes._store["truyen-1"][0]["rating"] == 5

    def test_rating_out_of_range_maps_to_422(self):
        resp = _submit(_client(), 6)
        assert resp.status_code == 422


class TestGetFeedback:
    def test_listing_requires_token_when_configured(self, monkeypatch):
        monkeypatch.setenv("STORYFORGE_ACCESS_TOKEN", "s3cret")
        client = _client()
        assert client.get("/api/feedback/truyen-1").status_code == 401
        authed = client.get(
            "/api/feedback/truyen-1", headers={"Authorization": "Bearer s3cret"}
        )
        assert authed.status_code == 404  # past the gate; nothing stored

    def test_unknown_story_maps_to_404(self):
        resp = _client().get("/api/feedback/truyen-x")
        assert resp.status_code == 404

    def test_average_and_pagination(self):
        client = _client()
        for rating in (2, 4, 5):
            _submit(client, rating)
        resp = client.get("/api/feedback/truyen-1?limit=2&offset=1")
        body = resp.json()
        assert resp.status_code == 200
        # average is computed over ALL entries, not just the page
        assert body["average_rating"] == round((2 + 4 + 5) / 3, 2)
        assert body["total"] == 3
        assert body["count"] == 2
        assert [e["rating"] for e in body["entries"]] == [4, 5]
        assert body["limit"] == 2
        assert body["offset"] == 1
