"""Tests for OnboardingManager and STEPS structure."""

import json
import os
import tempfile
import pytest

import services.onboarding as onboarding_module
from services.onboarding import OnboardingManager, STEPS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_manager(tmp_path) -> OnboardingManager:
    """Return a fresh OnboardingManager backed by a temp file."""
    state_file = str(tmp_path / "onboarding_state.json")
    onboarding_module.ONBOARDING_FILE = state_file
    return OnboardingManager()


# ---------------------------------------------------------------------------
# STEPS structure
# ---------------------------------------------------------------------------

class TestStepsStructure:
    def test_steps_not_empty(self):
        assert len(STEPS) > 0

    def test_each_step_has_required_keys(self):
        for step in STEPS:
            assert "id" in step
            assert "title" in step
            assert "description" in step
            assert "action" in step

    def test_step_ids_are_unique(self):
        ids = [s["id"] for s in STEPS]
        assert len(ids) == len(set(ids))

    def test_step_titles_nonempty(self):
        for step in STEPS:
            assert step["title"].strip()


# ---------------------------------------------------------------------------
# OnboardingManager — load / save
# ---------------------------------------------------------------------------

class TestOnboardingManagerLoadSave:
    def test_fresh_state_defaults(self, tmp_path):
        mgr = _make_manager(tmp_path)
        assert mgr.current_step == 0
        assert mgr.is_completed is False

    def test_load_existing_state(self, tmp_path):
        state_file = str(tmp_path / "onboarding_state.json")
        onboarding_module.ONBOARDING_FILE = state_file
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump({"completed": False, "current_step": 2, "skipped": False}, f)
        mgr = OnboardingManager()
        assert mgr.current_step == 2

    def test_corrupt_file_falls_back_to_defaults(self, tmp_path):
        state_file = str(tmp_path / "onboarding_state.json")
        onboarding_module.ONBOARDING_FILE = state_file
        with open(state_file, "w", encoding="utf-8") as f:
            f.write("not-json{{{")
        mgr = OnboardingManager()
        assert mgr.current_step == 0
        assert mgr.is_completed is False

    def test_save_persists_state(self, tmp_path):
        mgr = _make_manager(tmp_path)
        mgr._state["current_step"] = 1
        mgr._save()
        mgr2 = OnboardingManager()
        assert mgr2.current_step == 1


# ---------------------------------------------------------------------------
# advance
# ---------------------------------------------------------------------------

class TestAdvance:
    def test_advance_increments_step(self, tmp_path):
        mgr = _make_manager(tmp_path)
        assert mgr.current_step == 0
        mgr.advance()
        assert mgr.current_step == 1

    def test_advance_returns_step_info(self, tmp_path):
        mgr = _make_manager(tmp_path)
        info = mgr.advance()
        assert "title" in info
        assert "description" in info

    def test_advance_through_all_steps_completes(self, tmp_path):
        mgr = _make_manager(tmp_path)
        for _ in range(len(STEPS)):
            mgr.advance()
        assert mgr.is_completed is True

    def test_advance_does_not_exceed_last_step(self, tmp_path):
        mgr = _make_manager(tmp_path)
        last = len(STEPS) - 1
        for _ in range(last + 5):
            mgr.advance()
        assert mgr.current_step == last

    def test_advance_sets_completed_at_last_step(self, tmp_path):
        mgr = _make_manager(tmp_path)
        # Move to second-to-last step
        mgr._state["current_step"] = len(STEPS) - 2
        mgr._save()
        mgr2 = OnboardingManager()
        mgr2.advance()
        assert mgr2.is_completed is True


# ---------------------------------------------------------------------------
# skip
# ---------------------------------------------------------------------------

class TestSkip:
    def test_skip_marks_completed(self, tmp_path):
        mgr = _make_manager(tmp_path)
        assert mgr.is_completed is False
        mgr.skip()
        assert mgr.is_completed is True

    def test_skip_persists(self, tmp_path):
        mgr = _make_manager(tmp_path)
        mgr.skip()
        mgr2 = OnboardingManager()
        assert mgr2.is_completed is True

    def test_skip_sets_skipped_flag(self, tmp_path):
        mgr = _make_manager(tmp_path)
        mgr.skip()
        assert mgr._state.get("skipped") is True


# ---------------------------------------------------------------------------
# reset
# ---------------------------------------------------------------------------

class TestReset:
    def test_reset_clears_completed(self, tmp_path):
        mgr = _make_manager(tmp_path)
        mgr.skip()
        assert mgr.is_completed is True
        mgr.reset()
        assert mgr.is_completed is False

    def test_reset_sets_step_to_zero(self, tmp_path):
        mgr = _make_manager(tmp_path)
        mgr.advance()
        mgr.advance()
        mgr.reset()
        assert mgr.current_step == 0

    def test_reset_persists(self, tmp_path):
        mgr = _make_manager(tmp_path)
        mgr.skip()
        mgr.reset()
        mgr2 = OnboardingManager()
        assert mgr2.is_completed is False
        assert mgr2.current_step == 0


# ---------------------------------------------------------------------------
# current_step bounds
# ---------------------------------------------------------------------------

class TestCurrentStepBounds:
    def test_get_current_step_info_within_bounds(self, tmp_path):
        mgr = _make_manager(tmp_path)
        for i in range(len(STEPS)):
            mgr._state["current_step"] = i
            info = mgr.get_current_step_info()
            assert info == STEPS[i]

    def test_get_current_step_info_out_of_bounds_returns_last(self, tmp_path):
        mgr = _make_manager(tmp_path)
        mgr._state["current_step"] = 9999
        info = mgr.get_current_step_info()
        assert info == STEPS[-1]
