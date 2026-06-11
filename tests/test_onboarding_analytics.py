"""Unit tests for services/onboarding_analytics.py (previously untested)."""

from __future__ import annotations

from services.onboarding_analytics import OnboardingTracker


def test_track_step_aggregates_count_and_average():
    tracker = OnboardingTracker()
    tracker.track_step("s-1", "chọn thể loại", 1000)
    tracker.track_step("s-2", "chọn thể loại", 3000)
    funnel = tracker.get_funnel()
    assert funnel["chọn thể loại"] == {
        "count": 2,
        "avg_duration_ms": 2000,
        "dropout_count": 0,
    }


def test_dropout_only_step_has_no_average():
    tracker = OnboardingTracker()
    tracker.track_dropout("s-1", "nhập ý tưởng")
    funnel = tracker.get_funnel()
    assert funnel["nhập ý tưởng"] == {
        "count": 0,
        "avg_duration_ms": None,
        "dropout_count": 1,
    }


def test_mixed_steps_are_aggregated_independently():
    tracker = OnboardingTracker()
    tracker.track_step("s-1", "bước 1", 500)
    tracker.track_dropout("s-2", "bước 1")
    tracker.track_step("s-1", "bước 2", 800)
    funnel = tracker.get_funnel()
    assert funnel["bước 1"]["count"] == 1
    assert funnel["bước 1"]["dropout_count"] == 1
    assert funnel["bước 2"] == {
        "count": 1,
        "avg_duration_ms": 800,
        "dropout_count": 0,
    }


def test_none_duration_counts_as_zero_in_average():
    tracker = OnboardingTracker()
    tracker.track_step("s-1", "bước 1", 1000)
    tracker._events.append(
        {
            "session_id": "s-2",
            "step": "bước 1",
            "event": "complete",
            "duration_ms": None,
            "timestamp": 0.0,
        }
    )
    assert tracker.get_funnel()["bước 1"]["avg_duration_ms"] == 500


def test_event_buffer_trimmed_to_max_events():
    tracker = OnboardingTracker(max_events=3)
    for i in range(5):
        tracker.track_step(f"s-{i}", "bước 1", 100)
    assert len(tracker._events) == 3
    # oldest events were dropped
    assert tracker._events[0]["session_id"] == "s-2"


def test_empty_tracker_returns_empty_funnel():
    assert OnboardingTracker().get_funnel() == {}
