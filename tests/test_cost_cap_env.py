"""Per-run cost caps can be set from the environment.

Docker users cannot easily edit ``data/config.json`` (it lives in a named
volume of a slim image), and Settings does not expose the caps, so they come
from ``STORYFORGE_MAX_COST_PER_RUN_USD`` / ``STORYFORGE_MAX_TOKENS_PER_RUN`` /
``STORYFORGE_MAX_CALLS_PER_RUN`` with proper numeric types.
"""

from __future__ import annotations

import pytest

from config import ConfigManager
from config import persistence
from config.defaults import LLMConfig, PipelineConfig
from config.persistence import _apply_env_overrides, _env_overridden_fields

_CAP_ENV = {
    "STORYFORGE_MAX_COST_PER_RUN_USD": "2.5",
    "STORYFORGE_MAX_TOKENS_PER_RUN": "400000",
    "STORYFORGE_MAX_CALLS_PER_RUN": "150",
}


@pytest.fixture
def fresh_config_manager(tmp_path, monkeypatch):
    monkeypatch.setattr(persistence, "CONFIG_FILE", str(tmp_path / "config.json"))
    previous = ConfigManager._instance
    ConfigManager._instance = None
    try:
        yield
    finally:
        ConfigManager._instance = previous


def test_cap_env_vars_land_on_config_manager(monkeypatch, fresh_config_manager):
    for k, v in _CAP_ENV.items():
        monkeypatch.setenv(k, v)
    llm = ConfigManager().llm
    assert llm.max_cost_per_run_usd == 2.5
    assert isinstance(llm.max_cost_per_run_usd, float)
    assert llm.max_total_tokens_per_run == 400000
    assert isinstance(llm.max_total_tokens_per_run, int)
    assert llm.max_calls_per_run == 150
    assert isinstance(llm.max_calls_per_run, int)


def test_cap_env_vars_are_not_written_back(monkeypatch):
    for k, v in _CAP_ENV.items():
        monkeypatch.setenv(k, v)
    assert {
        "max_cost_per_run_usd",
        "max_total_tokens_per_run",
        "max_calls_per_run",
    } <= _env_overridden_fields("llm")


@pytest.mark.parametrize("env_key", sorted(_CAP_ENV))
def test_malformed_cap_value_is_ignored(monkeypatch, env_key):
    monkeypatch.setenv(env_key, "lots")
    llm = LLMConfig()
    _apply_env_overrides(llm, PipelineConfig())
    assert llm.max_cost_per_run_usd == 0.0
    assert llm.max_total_tokens_per_run == 0
    assert llm.max_calls_per_run == 0


def test_integer_cap_accepts_float_notation(monkeypatch):
    monkeypatch.setenv("STORYFORGE_MAX_CALLS_PER_RUN", "200.0")
    llm = LLMConfig()
    _apply_env_overrides(llm, PipelineConfig())
    assert llm.max_calls_per_run == 200 and isinstance(llm.max_calls_per_run, int)
