"""Regression test: a boolean env override must be able to turn a flag OFF.

Env values arrive as strings, and `_apply_env_overrides` only coerces fields
listed in `_BOOL_FIELDS`. A bool field missing from that set was assigned the
raw string instead — and every non-empty string is truthy, so `FLAG=0` turned
the flag ON. Two flags were in that state: `STORYFORGE_LENGTH_GATE` (shipped
that way) and `STORYFORGE_AGENTIC_REPAIR`, whose docs advertise `=0` as the
kill switch for the repair loop.

The general test matters more than the two specific ones: it fails for any
future bool added to `_ENV_MAP` without coercion, which is how both got here.
"""

import dataclasses

import pytest

from config.defaults import LLMConfig, PipelineConfig
from config.persistence import _BOOL_FIELDS, _ENV_MAP, _apply_env_overrides


def _apply(monkeypatch, env_key: str, value: str):
    monkeypatch.setenv(env_key, value)
    llm, pipeline = LLMConfig(), PipelineConfig()
    _apply_env_overrides(llm, pipeline)
    return llm, pipeline


@pytest.mark.parametrize(
    "env_key,field",
    [
        ("STORYFORGE_AGENTIC_REPAIR", "enable_agentic_repair"),
        ("STORYFORGE_LENGTH_GATE", "enable_length_gate"),
    ],
)
def test_zero_turns_the_flag_off(monkeypatch, env_key, field):
    assert getattr(PipelineConfig(), field) is True, "precondition: default is on"
    _, pipeline = _apply(monkeypatch, env_key, "0")
    assert getattr(pipeline, field) is False


@pytest.mark.parametrize(
    "env_key,field",
    [
        ("STORYFORGE_AGENTIC_REPAIR", "enable_agentic_repair"),
        ("STORYFORGE_LENGTH_GATE", "enable_length_gate"),
    ],
)
def test_one_turns_the_flag_on(monkeypatch, env_key, field):
    _, pipeline = _apply(monkeypatch, env_key, "1")
    assert getattr(pipeline, field) is True


def test_every_bool_in_the_env_map_is_coerced():
    """The rule, not the two instances: no bool reaches setattr as a string."""
    types = {
        f.name: f.type
        for f in dataclasses.fields(PipelineConfig) + dataclasses.fields(LLMConfig)
    }
    uncoerced = sorted(
        field
        for _env_key, (_section, field) in _ENV_MAP.items()
        if str(types.get(field, "")).startswith("bool") and field not in _BOOL_FIELDS
    )
    assert not uncoerced, (
        f"bool fields in _ENV_MAP missing from _BOOL_FIELDS: {uncoerced} — "
        "their env override can only turn the flag on"
    )
