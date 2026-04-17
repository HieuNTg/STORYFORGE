"""Verify LLMClient _record_trace_call appends to active trace."""
from __future__ import annotations

import pytest

from services.llm.client import _record_trace_call
from services.trace_context import (
    PipelineTrace,
    clear_trace,
    set_chapter,
    set_module,
    set_trace,
)


@pytest.fixture(autouse=True)
def _reset():
    clear_trace()
    yield
    clear_trace()


def test_no_trace_is_noop():
    # Must not raise when no trace is active
    _record_trace_call(
        model="gpt-5", model_tier="primary",
        messages=[{"role": "user", "content": "hi"}],
        result="hello", duration_ms=10, success=True,
    )


def test_records_call_with_tags():
    t = PipelineTrace()
    set_trace(t)
    set_module("chapter_writer")
    set_chapter(3)
    _record_trace_call(
        model="claude-sonnet-4-6", model_tier="primary",
        messages=[{"role": "user", "content": "x" * 400}],
        result="y" * 200, duration_ms=150, success=True,
    )
    assert len(t.calls) == 1
    c = t.calls[0]
    assert c.chapter_number == 3
    assert c.module == "chapter_writer"
    assert c.model == "claude-sonnet-4-6"
    assert c.prompt_tokens == 100
    assert c.completion_tokens == 50
    assert c.total_tokens == 150
    assert c.cost_usd > 0
    assert c.success is True


def test_failure_records_no_completion_tokens():
    t = PipelineTrace()
    set_trace(t)
    _record_trace_call(
        model="gpt-5", model_tier="fallback",
        messages=[{"role": "user", "content": "x" * 400}],
        result="", duration_ms=20, success=False, error="boom",
    )
    assert len(t.calls) == 1
    c = t.calls[0]
    assert c.success is False
    assert c.completion_tokens == 0
    assert c.error == "boom"


def test_missing_module_defaults_to_unknown():
    t = PipelineTrace()
    set_trace(t)
    _record_trace_call(
        model="gpt-5", model_tier="primary",
        messages=[{"role": "user", "content": "hi"}],
        result="ok", duration_ms=5, success=True,
    )
    assert t.calls[0].module == "unknown"
