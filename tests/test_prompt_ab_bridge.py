"""Unit tests for services/prompt_ab_bridge.py (previously untested).

Fresh PromptABBridge instances are used instead of the module singleton;
ab_manager is patched at the bridge module's namespace (top-level import
alias) and prompt_manager at its source module (lazy import).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from services.prompt_ab_bridge import PromptABBridge


@pytest.fixture
def ab_manager():
    with patch("services.prompt_ab_bridge.ab_manager") as mock:
        yield mock


@pytest.fixture
def prompt_manager():
    mock = MagicMock()
    mock.get.return_value = "prompt đã định dạng"
    with patch("services.prompt_manager.prompt_manager", mock):
        yield mock


class TestCreateExperiment:
    def test_registers_mapping_and_returns_id(self, ab_manager):
        ab_manager.create_experiment.return_value = "exp-1"
        bridge = PromptABBridge()
        result = bridge.create_prompt_experiment("write_chapter", ["v1", "v2"])
        assert result == "exp-1"
        ab_manager.create_experiment.assert_called_once_with(
            "prompt:write_chapter", ["v1", "v2"]
        )
        assert bridge.get_active_experiment_id("write_chapter") == "exp-1"

    def test_no_experiment_returns_none(self, ab_manager):
        assert PromptABBridge().get_active_experiment_id("write_chapter") is None


class TestGetPrompt:
    def test_without_experiment_uses_latest(self, ab_manager, prompt_manager):
        result = PromptABBridge().get_prompt("write_chapter", "s-1", genre="ngôn tình")
        assert result == "prompt đã định dạng"
        prompt_manager.get.assert_called_once_with(
            "write_chapter", version="latest", genre="ngôn tình"
        )

    def test_with_experiment_routes_to_assigned_variant(
        self, ab_manager, prompt_manager
    ):
        ab_manager.create_experiment.return_value = "exp-1"
        ab_manager.assign_variant.return_value = "v2"
        bridge = PromptABBridge()
        bridge.create_prompt_experiment("write_chapter", ["v1", "v2"])
        bridge.get_prompt("write_chapter", "s-1")
        ab_manager.assign_variant.assert_called_once_with("exp-1", "s-1")
        prompt_manager.get.assert_called_once_with("write_chapter", version="v2")

    def test_assignment_failure_falls_back_to_latest(self, ab_manager, prompt_manager):
        ab_manager.create_experiment.return_value = "exp-1"
        ab_manager.assign_variant.side_effect = KeyError("exp-1")
        bridge = PromptABBridge()
        bridge.create_prompt_experiment("write_chapter", ["v1", "v2"])
        result = bridge.get_prompt("write_chapter", "s-1")
        assert result == "prompt đã định dạng"
        prompt_manager.get.assert_called_once_with("write_chapter", version="latest")


class TestRecordQuality:
    def test_without_experiment_is_a_noop(self, ab_manager):
        PromptABBridge().record_quality("write_chapter", "s-1", 0.9)
        ab_manager.record_result.assert_not_called()

    def test_with_experiment_records_quality_metric(self, ab_manager):
        ab_manager.create_experiment.return_value = "exp-1"
        bridge = PromptABBridge()
        bridge.create_prompt_experiment("write_chapter", ["v1", "v2"])
        bridge.record_quality("write_chapter", "s-1", 0.75)
        ab_manager.record_result.assert_called_once_with(
            "exp-1", "s-1", metric="quality", value=0.75
        )


class TestResults:
    def test_results_without_experiment_raises_key_error(self, ab_manager):
        with pytest.raises(KeyError):
            PromptABBridge().get_experiment_results("write_chapter")

    def test_results_shape(self, ab_manager):
        ab_manager.create_experiment.return_value = "exp-1"
        ab_manager.get_results.return_value = {"v1": {"quality": 0.8}}
        bridge = PromptABBridge()
        bridge.create_prompt_experiment("write_chapter", ["v1", "v2"])
        assert bridge.get_experiment_results("write_chapter") == {
            "experiment_id": "exp-1",
            "prompt_name": "write_chapter",
            "results": {"v1": {"quality": 0.8}},
        }

    def test_list_active_merges_ab_metadata(self, ab_manager):
        ab_manager.create_experiment.return_value = "exp-1"
        ab_manager.list_experiments.return_value = [
            {"id": "exp-1", "name": "prompt:write_chapter", "status": "active"},
            {"id": "exp-other", "name": "khác"},
        ]
        bridge = PromptABBridge()
        bridge.create_prompt_experiment("write_chapter", ["v1", "v2"])
        active = bridge.list_active_experiments()
        assert active == [
            {
                "prompt_name": "write_chapter",
                "experiment_id": "exp-1",
                "id": "exp-1",
                "name": "prompt:write_chapter",
                "status": "active",
            }
        ]
