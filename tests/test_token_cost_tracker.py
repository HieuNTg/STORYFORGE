"""Unit tests for services/token_cost_tracker.py — singleton, pricing, aggregation."""

import json

import pytest

from services.token_cost_tracker import (
    DEFAULT_PRICING,
    StoryCostSummary,
    TokenCostTracker,
    UsageRecord,
)


@pytest.fixture(autouse=True)
def _fresh_tracker(monkeypatch):
    """Isolate every test: clean env, fresh singleton before and after."""
    monkeypatch.delenv("STORYFORGE_TOKEN_PRICING", raising=False)
    monkeypatch.delenv("STORYFORGE_COST_LOG", raising=False)
    TokenCostTracker.reset()
    yield
    TokenCostTracker.reset()


class TestSingleton:
    def test_same_instance(self):
        assert TokenCostTracker() is TokenCostTracker()

    def test_reset_creates_new_instance(self):
        first = TokenCostTracker()
        TokenCostTracker.reset()
        assert TokenCostTracker() is not first


class TestTrackUsage:
    def test_returns_populated_record(self):
        record = TokenCostTracker().track_usage(
            "story-1",
            layer=1,
            agent="Editor",
            model="gpt-4o-mini",
            prompt_tokens=500,
            completion_tokens=250,
        )
        assert isinstance(record, UsageRecord)
        assert record.total_tokens == 750
        expected = (500 * 0.000150 + 250 * 0.000600) / 1000.0
        assert record.cost_usd == pytest.approx(expected)
        assert record.timestamp  # ISO string populated

    def test_records_accumulate_in_session(self):
        tracker = TokenCostTracker()
        tracker.track_usage("s", 1, "A", "gpt-4o-mini", 10, 10)
        tracker.track_usage("s", 2, "B", "gpt-4o", 20, 20)
        assert tracker.get_session_summary()["call_count"] == 2


class TestStoryCost:
    def test_empty_story_is_all_zero(self):
        summary = TokenCostTracker().get_story_cost("missing")
        assert isinstance(summary, StoryCostSummary)
        assert summary.call_count == 0
        assert summary.total_tokens == 0
        assert summary.by_layer == {}

    def test_aggregates_by_layer_agent_model(self):
        tracker = TokenCostTracker()
        tracker.track_usage("s1", 1, "Editor", "gpt-4o-mini", 100, 50)
        tracker.track_usage("s1", 2, "Critic", "gpt-4o", 200, 100)
        tracker.track_usage("s1", 1, "Editor", "gpt-4o-mini", 100, 50)
        tracker.track_usage("other", 1, "Editor", "gpt-4o-mini", 999, 999)

        summary = tracker.get_story_cost("s1")
        assert summary.call_count == 3
        assert summary.total_prompt_tokens == 400
        assert summary.total_completion_tokens == 200
        assert summary.total_tokens == 600
        assert summary.by_layer["1"]["tokens"] == 300
        assert summary.by_layer["2"]["tokens"] == 300
        assert summary.by_agent["Editor"]["tokens"] == 300
        assert summary.by_model["gpt-4o"]["tokens"] == 300
        assert summary.total_cost_usd > 0


class TestSessionSummary:
    def test_summary_shape_and_totals(self):
        tracker = TokenCostTracker()
        tracker.track_usage("s1", 1, "A", "gpt-4o-mini", 100, 50)
        tracker.track_usage("s2", 1, "A", "deepseek-chat", 200, 100)
        data = tracker.get_session_summary()
        assert data["call_count"] == 2
        assert data["total_prompt_tokens"] == 300
        assert data["total_completion_tokens"] == 150
        assert data["total_tokens"] == 450
        assert set(data["by_story"]) == {"s1", "s2"}
        assert set(data["by_model"]) == {"gpt-4o-mini", "deepseek-chat"}

    def test_reset_session_clears_records(self):
        tracker = TokenCostTracker()
        tracker.track_usage("s", 1, "A", "gpt-4o-mini", 10, 10)
        tracker.reset_session()
        assert tracker.get_session_summary()["call_count"] == 0


class TestPricing:
    def test_alias_resolves_to_canonical_rates(self):
        tracker = TokenCostTracker()
        via_alias = tracker._compute_cost("claude-3.5-sonnet", 1000, 1000)
        canonical = tracker._compute_cost("claude-3-5-sonnet", 1000, 1000)
        assert via_alias == canonical

    def test_prefix_match_handles_version_suffix(self):
        tracker = TokenCostTracker()
        suffixed = tracker._compute_cost("gpt-4o-mini-2024-07-18", 1000, 1000)
        exact = tracker._compute_cost("gpt-4o-mini", 1000, 1000)
        assert suffixed == exact

    def test_unknown_model_uses_default_rates(self):
        cost = TokenCostTracker()._compute_cost("totally-unknown-model", 1000, 1000)
        rates = DEFAULT_PRICING["_default"]
        assert cost == pytest.approx(rates["prompt"] + rates["completion"])

    def test_update_pricing_at_runtime(self):
        tracker = TokenCostTracker()
        tracker.update_pricing({"my-model": {"prompt": 1.0, "completion": 2.0}})
        assert tracker._compute_cost("my-model", 1000, 1000) == pytest.approx(3.0)

    def test_env_pricing_override(self, monkeypatch):
        pricing = {"env-model": {"prompt": 0.5, "completion": 0.5}}
        monkeypatch.setenv("STORYFORGE_TOKEN_PRICING", json.dumps(pricing))
        TokenCostTracker.reset()
        cost = TokenCostTracker()._compute_cost("env-model", 1000, 1000)
        assert cost == pytest.approx(1.0)

    def test_env_pricing_invalid_json_keeps_defaults(self, monkeypatch):
        monkeypatch.setenv("STORYFORGE_TOKEN_PRICING", "{not json")
        TokenCostTracker.reset()
        tracker = TokenCostTracker()  # must not raise
        assert tracker._compute_cost("gpt-4o-mini", 1000, 0) == pytest.approx(0.000150)


class TestPersistence:
    def test_appends_jsonl_records(self, monkeypatch, tmp_path):
        log_path = tmp_path / "costs" / "usage.jsonl"
        monkeypatch.setenv("STORYFORGE_COST_LOG", str(log_path))
        TokenCostTracker.reset()
        tracker = TokenCostTracker()
        tracker.track_usage("s", 1, "A", "gpt-4o-mini", 10, 10)
        tracker.track_usage("s", 1, "A", "gpt-4o-mini", 20, 20)

        lines = log_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2
        first = json.loads(lines[0])
        assert first["story_id"] == "s"
        assert first["total_tokens"] == 20

    def test_write_failure_logged_not_raised(self, monkeypatch, tmp_path):
        blocker = tmp_path / "blocker"
        blocker.write_text("file, not a directory")
        monkeypatch.setenv("STORYFORGE_COST_LOG", str(blocker / "sub" / "x.jsonl"))
        TokenCostTracker.reset()
        record = TokenCostTracker().track_usage("s", 1, "A", "gpt-4o-mini", 1, 1)
        assert record.cost_usd >= 0  # tracking still succeeds
