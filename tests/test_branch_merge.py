"""Tests for branch merging feature (Phase 6)."""

import pytest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from models.schemas import MergeConflict, MergeResult
from services.pipeline.branch_narrative import BranchManager


# ══════════════════════════════════════════════════════════════════════════════
# Unit Tests: Schema
# ══════════════════════════════════════════════════════════════════════════════

class TestMergeSchemas:
    """Unit tests for merge-related schemas."""

    def test_merge_conflict_schema(self):
        """Should create valid MergeConflict."""
        conflict = MergeConflict(
            conflict_type="character_state",
            description="Hero has different moods",
            source_a="happy",
            source_b="sad",
            suggested_resolution="Use context to determine mood",
        )
        assert conflict.conflict_type == "character_state"
        assert conflict.description == "Hero has different moods"

    def test_merge_result_schema(self):
        """Should create valid MergeResult."""
        result = MergeResult(
            merged_text="Combined narrative",
            conflicts_resolved=[],
            conflicts_unresolved=[],
            merge_strategy="auto",
        )
        assert result.merged_text == "Combined narrative"
        assert result.merge_strategy == "auto"

    def test_merge_result_defaults(self):
        """Default values should be correct."""
        result = MergeResult(merged_text="Test")
        assert result.conflicts_resolved == []
        assert result.conflicts_unresolved == []
        assert result.merge_strategy == "auto"


# ══════════════════════════════════════════════════════════════════════════════
# Unit Tests: BranchManager.merge_branches
# ══════════════════════════════════════════════════════════════════════════════

class TestBranchManagerMerge:
    """Tests for BranchManager.merge_branches method."""

    def test_merge_branches_creates_new_node(self):
        """Merging should create a new node in the tree."""
        mgr = BranchManager()
        session = mgr.start_session("Root story", ["Option A", "Option B"])
        session_id = session["session_id"]

        # Create two branches
        mgr.add_generated_node(session_id, 0, "Branch A content", ["Continue A"])
        node_a_id = mgr.get_current_node(session_id)["id"]

        mgr.go_back(session_id)
        mgr.add_generated_node(session_id, 1, "Branch B content", ["Continue B"])
        node_b_id = mgr.get_current_node(session_id)["id"]

        # Merge
        result = mgr.merge_branches(session_id, node_a_id, node_b_id, strategy="prefer_a")

        assert "merged_node" in result
        assert result["merged_node"]["text"] == "Branch A content"

    def test_merge_with_prefer_b_strategy(self):
        """prefer_b strategy should use node B's content."""
        mgr = BranchManager()
        session = mgr.start_session("Root", ["A", "B"])
        session_id = session["session_id"]

        mgr.add_generated_node(session_id, 0, "Content A", ["A1"])
        node_a_id = mgr.get_current_node(session_id)["id"]

        mgr.go_back(session_id)
        mgr.add_generated_node(session_id, 1, "Content B", ["B1"])
        node_b_id = mgr.get_current_node(session_id)["id"]

        result = mgr.merge_branches(session_id, node_a_id, node_b_id, strategy="prefer_b")

        assert result["merged_node"]["text"] == "Content B"

    def test_merge_detects_character_state_conflicts(self):
        """Should detect when characters have different states."""
        mgr = BranchManager()
        session = mgr.start_session("Root", ["A", "B"])
        session_id = session["session_id"]

        mgr.add_generated_node(session_id, 0, "A", ["A1"], character_states={"Hero": {"mood": "happy"}})
        node_a_id = mgr.get_current_node(session_id)["id"]

        mgr.go_back(session_id)
        mgr.add_generated_node(session_id, 1, "B", ["B1"], character_states={"Hero": {"mood": "sad"}})
        node_b_id = mgr.get_current_node(session_id)["id"]

        result = mgr.merge_branches(session_id, node_a_id, node_b_id, strategy="prefer_a")

        # Should have resolved conflicts
        assert len(result["conflicts_resolved"]) > 0

    def test_merge_invalid_node_raises(self):
        """Merging with invalid node ID should raise ValueError."""
        mgr = BranchManager()
        session = mgr.start_session("Root", ["A"])
        session_id = session["session_id"]

        with pytest.raises(ValueError, match="not found"):
            mgr.merge_branches(session_id, "invalid_id", "also_invalid")

    def test_merge_invalid_session_raises(self):
        """Merging with invalid session should raise KeyError."""
        mgr = BranchManager()

        with pytest.raises(KeyError):
            mgr.merge_branches("nonexistent_session", "a", "b")

    def test_merge_finds_common_ancestor(self):
        """Should identify common ancestor node."""
        mgr = BranchManager()
        session = mgr.start_session("Root", ["A", "B"])
        session_id = session["session_id"]
        root_id = session["node"]["id"]

        mgr.add_generated_node(session_id, 0, "A", ["A1"])
        node_a_id = mgr.get_current_node(session_id)["id"]

        mgr.go_back(session_id)
        mgr.add_generated_node(session_id, 1, "B", ["B1"])
        node_b_id = mgr.get_current_node(session_id)["id"]

        result = mgr.merge_branches(session_id, node_a_id, node_b_id)

        assert result["common_ancestor"] == root_id

    def test_merge_without_llm_concatenates(self):
        """Without LLM and strategy=auto, should concatenate texts."""
        mgr = BranchManager()
        session = mgr.start_session("Root", ["A", "B"])
        session_id = session["session_id"]

        mgr.add_generated_node(session_id, 0, "Text A", ["A1"])
        node_a_id = mgr.get_current_node(session_id)["id"]

        mgr.go_back(session_id)
        mgr.add_generated_node(session_id, 1, "Text B", ["B1"])
        node_b_id = mgr.get_current_node(session_id)["id"]

        result = mgr.merge_branches(session_id, node_a_id, node_b_id, strategy="auto", llm=None)

        # Should concatenate when no LLM
        assert "Text A" in result["merged_node"]["text"]
        assert "Text B" in result["merged_node"]["text"]


# ══════════════════════════════════════════════════════════════════════════════
# API Tests
# ══════════════════════════════════════════════════════════════════════════════

def _make_app() -> FastAPI:
    from fastapi import APIRouter
    from api.branch_routes import router as branch_router
    app = FastAPI()
    api = APIRouter(prefix="/api")
    api.include_router(branch_router)
    app.include_router(api)
    return app


@pytest.fixture
def client():
    app = _make_app()
    return TestClient(app)


class TestBranchMergeAPI:
    """API endpoint tests for branch merging."""

    def test_merge_endpoint_exists(self, client):
        """Merge endpoint should exist and return proper errors."""
        resp = client.post(
            "/api/branch/nonexistent/merge",
            json={"node_a_id": "a", "node_b_id": "b"},
        )
        # Should return 404 for missing session, not 404 for missing route
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_merge_validates_strategy(self, client):
        """Invalid strategy should return 400."""
        # First create a session
        resp = client.post(
            "/api/branch/start",
            json={"text": "Test story content here"},
        )
        session_id = resp.json()["session_id"]

        resp = client.post(
            f"/api/branch/{session_id}/merge",
            json={"node_a_id": "a", "node_b_id": "b", "strategy": "invalid"},
        )
        assert resp.status_code == 400
        assert "invalid strategy" in resp.json()["detail"].lower()

    def test_merge_returns_merged_node(self, client):
        """Successful merge should return merged node."""
        # Create session
        resp = client.post(
            "/api/branch/start",
            json={"text": "The hero stood at the crossroads."},
        )
        session_id = resp.json()["session_id"]
        root_id = resp.json()["node"]["id"]

        # Create branch A
        resp = client.post(
            f"/api/branch/{session_id}/goto",
            json={"node_id": root_id},
        )

        # For a real test we'd need to mock LLM, but let's test structure
        # This tests that the endpoint accepts valid requests
        resp = client.post(
            f"/api/branch/{session_id}/merge",
            json={"node_a_id": root_id, "node_b_id": root_id, "strategy": "prefer_a"},
        )
        # Merging same node with itself should work (edge case)
        assert resp.status_code == 200
        assert "merged_node" in resp.json()
