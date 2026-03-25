"""Tests for services/progress_tracker.py"""

import pytest
from services.progress_tracker import ProgressEvent, ProgressTracker


# ── ProgressEvent ──────────────────────────────────────────────────────────

class TestProgressEvent:
    def test_creation_defaults(self):
        ev = ProgressEvent(step="gate", status="started", message="hello")
        assert ev.step == "gate"
        assert ev.status == "started"
        assert ev.message == "hello"
        assert ev.detail == ""
        assert ev.progress == 0.0
        assert ev.timestamp > 0

    def test_creation_full(self):
        ev = ProgressEvent(step="revision", status="retry", message="msg",
                           detail="ch3", progress=0.5)
        assert ev.detail == "ch3"
        assert ev.progress == 0.5

    def test_to_log_prefix_known_steps(self):
        cases = [
            ("layer1", "started", "[L1] ▶"),
            ("layer2", "in_progress", "[L2] ⟳"),
            ("layer3", "retry", "[L3] ↻"),
            ("gate", "completed", "[GATE] ✓"),
            ("revision", "failed", "[REVISION] ✗"),
            ("scoring", "started", "[METRICS] ▶"),
        ]
        for step, status, expected_prefix in cases:
            ev = ProgressEvent(step=step, status=status, message="x")
            assert ev.to_log_prefix() == expected_prefix

    def test_to_log_prefix_unknown_step(self):
        ev = ProgressEvent(step="custom", status="started", message="x")
        assert ev.to_log_prefix() == "[CUSTOM] ▶"

    def test_to_log_prefix_unknown_status(self):
        ev = ProgressEvent(step="gate", status="unknown_status", message="x")
        assert ev.to_log_prefix() == "[GATE] •"


# ── ProgressTracker ────────────────────────────────────────────────────────

class TestProgressTrackerEmit:
    def test_emit_calls_callback(self):
        received = []
        tracker = ProgressTracker(callback=received.append)
        tracker.emit("gate", "started", "Testing")
        assert len(received) == 1
        assert "[GATE]" in received[0]
        assert "Testing" in received[0]

    def test_emit_includes_detail_in_callback(self):
        received = []
        tracker = ProgressTracker(callback=received.append)
        tracker.emit("gate", "started", "Testing", detail="Layer 1")
        assert "(Layer 1)" in received[0]

    def test_emit_no_callback_no_crash(self):
        tracker = ProgressTracker(callback=None)
        ev = tracker.emit("gate", "started", "No callback")
        assert ev.message == "No callback"

    def test_emit_returns_event(self):
        tracker = ProgressTracker()
        ev = tracker.emit("scoring", "completed", "Done", progress=1.0)
        assert isinstance(ev, ProgressEvent)
        assert ev.progress == 1.0

    def test_emit_accumulates_events(self):
        tracker = ProgressTracker()
        tracker.emit("gate", "started", "a")
        tracker.emit("gate", "completed", "b")
        assert len(tracker.events) == 2

    def test_events_returns_copy(self):
        tracker = ProgressTracker()
        tracker.emit("gate", "started", "x")
        events_a = tracker.events
        events_b = tracker.events
        assert events_a is not events_b  # different list objects


# ── Gate helpers ───────────────────────────────────────────────────────────

class TestGateHelpers:
    def setup_method(self):
        self.logs = []
        self.tracker = ProgressTracker(callback=self.logs.append)

    def test_gate_started(self):
        self.tracker.gate_started(1)
        ev = self.tracker.last_event
        assert ev.step == "gate"
        assert ev.status == "started"
        assert "Layer 1" in ev.message
        assert "[GATE]" in self.logs[-1]

    def test_gate_passed(self):
        self.tracker.gate_passed(1, 4.2)
        ev = self.tracker.last_event
        assert ev.status == "completed"
        assert "4.2" in ev.message
        assert "PASSED" in ev.message
        assert ev.detail == "Layer 1"

    def test_gate_retry(self):
        self.tracker.gate_retry(2, 3.1, attempt=2)
        ev = self.tracker.last_event
        assert ev.status == "retry"
        assert "3.1" in ev.message
        assert "2" in ev.message
        assert ev.detail == "Layer 2"

    def test_gate_failed(self):
        self.tracker.gate_failed(1, 2.5)
        ev = self.tracker.last_event
        assert ev.status == "failed"
        assert "2.5" in ev.message


# ── Revision helpers ───────────────────────────────────────────────────────

class TestRevisionHelpers:
    def setup_method(self):
        self.logs = []
        self.tracker = ProgressTracker(callback=self.logs.append)

    def test_revision_started(self):
        self.tracker.revision_started(5)
        ev = self.tracker.last_event
        assert ev.step == "revision"
        assert ev.status == "started"
        assert "5" in ev.message

    def test_revision_chapter(self):
        self.tracker.revision_chapter(chapter_num=3, pass_num=1, total_weak=5, current=2)
        ev = self.tracker.last_event
        assert ev.status == "in_progress"
        assert "3" in ev.message
        assert ev.detail == "2/5"
        assert abs(ev.progress - 0.4) < 1e-9

    def test_revision_chapter_progress_clamp_zero(self):
        self.tracker.revision_chapter(chapter_num=1, pass_num=1, total_weak=0, current=0)
        ev = self.tracker.last_event
        # total_weak=0 uses max(0,1)=1, so progress = 0/1 = 0.0
        assert ev.progress == 0.0

    def test_revision_chapter_done(self):
        self.tracker.revision_chapter_done(chapter_num=3, old_score=2.5, new_score=3.8)
        ev = self.tracker.last_event
        assert ev.status == "completed"
        assert "2.5" in ev.message
        assert "3.8" in ev.message
        assert "+1.3" in ev.message
        assert ev.detail == "ch3"

    def test_revision_chapter_done_negative_delta(self):
        self.tracker.revision_chapter_done(chapter_num=2, old_score=4.0, new_score=3.5)
        ev = self.tracker.last_event
        assert "-0.5" in ev.message

    def test_revision_done(self):
        self.tracker.revision_done(revised=4, total_weak=5)
        ev = self.tracker.last_event
        assert ev.status == "completed"
        assert "4" in ev.message
        assert "5" in ev.message
        assert ev.progress == 1.0


# ── Scoring helpers ────────────────────────────────────────────────────────

class TestScoringHelpers:
    def setup_method(self):
        self.logs = []
        self.tracker = ProgressTracker(callback=self.logs.append)

    def test_scoring_started(self):
        self.tracker.scoring_started(2)
        ev = self.tracker.last_event
        assert ev.step == "scoring"
        assert ev.status == "started"
        assert "Layer 2" in ev.message
        assert "[METRICS]" in self.logs[-1]

    def test_scoring_done(self):
        self.tracker.scoring_done(1, 3.7)
        ev = self.tracker.last_event
        assert ev.status == "completed"
        assert "3.7" in ev.message
        assert "Layer 1" in ev.message


# ── Accumulation and last_event ────────────────────────────────────────────

class TestAccumulationAndLastEvent:
    def test_events_accumulate_across_helpers(self):
        tracker = ProgressTracker()
        tracker.gate_started(1)
        tracker.gate_passed(1, 4.0)
        tracker.scoring_started(1)
        tracker.scoring_done(1, 4.0)
        tracker.revision_started(3)
        tracker.revision_done(3, 3)
        assert len(tracker.events) == 6

    def test_last_event_none_when_empty(self):
        tracker = ProgressTracker()
        assert tracker.last_event is None

    def test_last_event_is_most_recent(self):
        tracker = ProgressTracker()
        tracker.gate_started(1)
        tracker.gate_passed(1, 5.0)
        ev = tracker.last_event
        assert ev.status == "completed"

    def test_progress_values_in_range(self):
        tracker = ProgressTracker()
        for i in range(1, 6):
            tracker.revision_chapter(chapter_num=i, pass_num=1, total_weak=5, current=i)
        for ev in tracker.events:
            assert 0.0 <= ev.progress <= 1.0

    def test_revision_done_progress_is_one(self):
        tracker = ProgressTracker()
        tracker.revision_done(5, 5)
        assert tracker.last_event.progress == 1.0

    def test_callback_called_for_every_emit(self):
        received = []
        tracker = ProgressTracker(callback=received.append)
        tracker.gate_started(1)
        tracker.gate_passed(1, 4.0)
        tracker.scoring_started(1)
        assert len(received) == 3
