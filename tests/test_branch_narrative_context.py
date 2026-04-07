"""Tests for BranchManager story context and per-node character state tracking."""

from services.pipeline.branch_narrative import BranchManager


class TestBranchManagerContext:
    """Verify context storage and per-node character state tracking."""

    def _make_manager_with_context(self):
        mgr = BranchManager()
        ctx = {
            "genre": "fantasy",
            "characters": [{"name": "Aria", "role": "hero", "personality": "brave"}],
            "world_summary": "A magical kingdom",
            "conflict_summary": "war between factions",
        }
        data = mgr.start_session("Once upon a time...", context=ctx)
        return mgr, data["session_id"], ctx

    def test_start_session_stores_context(self):
        mgr, sid, ctx = self._make_manager_with_context()
        stored = mgr.get_context(sid)
        assert stored["genre"] == "fantasy"
        assert len(stored["characters"]) == 1
        assert stored["characters"][0]["name"] == "Aria"
        assert stored["world_summary"] == "A magical kingdom"

    def test_start_session_without_context_backward_compat(self):
        mgr = BranchManager()
        data = mgr.start_session("Some story text here.")
        sid = data["session_id"]
        assert mgr.get_context(sid) == {}

    def test_node_character_states_default_empty(self):
        mgr, sid, _ = self._make_manager_with_context()
        states = mgr.get_node_states(sid)
        assert states == {}

    def test_add_generated_node_with_character_states(self):
        mgr, sid, _ = self._make_manager_with_context()
        states = {"Aria": {"mood": "determined", "arc_position": "rising"}}
        node = mgr.add_generated_node(sid, 0, "Aria drew her sword.", ["Fight", "Flee"], character_states=states)
        assert node is not None
        retrieved = mgr.get_node_states(sid)
        assert retrieved["Aria"]["mood"] == "determined"

    def test_character_states_differ_across_branches(self):
        mgr, sid, _ = self._make_manager_with_context()
        # Branch A: Aria is brave
        mgr.add_generated_node(sid, 0, "Branch A", ["Next"], character_states={"Aria": {"mood": "brave"}})
        states_a = mgr.get_node_states(sid)

        # Go back to root
        mgr.go_back(sid)

        # Branch B: Aria is fearful
        mgr.add_generated_node(sid, 1, "Branch B", ["Next"], character_states={"Aria": {"mood": "fearful"}})
        states_b = mgr.get_node_states(sid)

        assert states_a["Aria"]["mood"] == "brave"
        assert states_b["Aria"]["mood"] == "fearful"

    def test_add_generated_node_without_states_backward_compat(self):
        mgr, sid, _ = self._make_manager_with_context()
        node = mgr.add_generated_node(sid, 0, "Continuation text", ["Go on"])
        assert node is not None
        states = mgr.get_node_states(sid)
        assert states == {}
