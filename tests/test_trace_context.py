"""Unit tests for services.trace_context + services.llm_pricing (Sprint 1 Task 2)."""
from __future__ import annotations

import asyncio

import pytest

from services.trace_context import (
    LLMCall,
    PipelineTrace,
    clear_trace,
    get_chapter,
    get_module,
    get_trace,
    set_chapter,
    set_module,
    set_trace,
)
from services.llm_pricing import compute_cost, _resolve_rates, PRICING


@pytest.fixture(autouse=True)
def _reset_trace():
    clear_trace()
    yield
    clear_trace()


def _make_call(
    trace_id: str = "t",
    module: str = "m",
    chapter: int | None = 1,
    model: str = "claude-sonnet-4-6",
    prompt: int = 100,
    completion: int = 50,
    cost: float = 0.001,
    success: bool = True,
) -> LLMCall:
    return LLMCall(
        call_id="c",
        trace_id=trace_id,
        chapter_number=chapter,
        module=module,
        model=model,
        model_tier="primary",
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=prompt + completion,
        cost_usd=cost,
        duration_ms=10,
        success=success,
    )


class TestPipelineTrace:
    def test_totals(self):
        t = PipelineTrace()
        t.add_call(_make_call(prompt=100, completion=50, cost=0.001))
        t.add_call(_make_call(prompt=200, completion=100, cost=0.002))
        assert t.total_tokens() == 450
        assert abs(t.total_cost() - 0.003) < 1e-9

    def test_cost_by_module(self):
        t = PipelineTrace()
        t.add_call(_make_call(module="l1", cost=0.1))
        t.add_call(_make_call(module="l1", cost=0.2))
        t.add_call(_make_call(module="l2", cost=0.5))
        breakdown = t.cost_by_module()
        assert abs(breakdown["l1"] - 0.3) < 1e-9
        assert breakdown["l2"] == 0.5

    def test_cost_by_chapter_skips_none(self):
        t = PipelineTrace()
        t.add_call(_make_call(chapter=1, cost=0.1))
        t.add_call(_make_call(chapter=2, cost=0.2))
        t.add_call(_make_call(chapter=None, cost=0.5))
        breakdown = t.cost_by_chapter()
        assert breakdown == {1: 0.1, 2: 0.2}

    def test_summary_structure(self):
        t = PipelineTrace()
        t.add_call(_make_call(module="l1", chapter=1))
        s = t.summary()
        assert set(s) == {
            "trace_id", "total_calls", "total_tokens",
            "total_cost_usd", "cost_by_module", "cost_by_chapter", "rag",
        }
        assert s["total_calls"] == 1


class TestContextVars:
    def test_get_set_clear(self):
        assert get_trace() is None
        t = PipelineTrace()
        set_trace(t)
        assert get_trace() is t
        set_chapter(5)
        set_module("x")
        assert get_chapter() == 5
        assert get_module() == "x"
        clear_trace()
        assert get_trace() is None
        assert get_chapter() is None
        assert get_module() == ""

    @pytest.mark.asyncio
    async def test_asyncio_to_thread_isolation(self):
        """Each worker thread gets its own chapter/module via contextvars copy."""
        set_trace(PipelineTrace())

        def _worker(ch: int) -> tuple[int | None, str]:
            set_chapter(ch)
            set_module(f"mod-{ch}")
            return get_chapter(), get_module()

        results = await asyncio.gather(
            asyncio.to_thread(_worker, 1),
            asyncio.to_thread(_worker, 2),
            asyncio.to_thread(_worker, 3),
        )
        assert sorted(results) == [(1, "mod-1"), (2, "mod-2"), (3, "mod-3")]
        # Main context is unaffected
        assert get_chapter() is None
        assert get_module() == ""


class TestPricing:
    def test_known_model(self):
        c = compute_cost("claude-sonnet-4-6", 1_000_000, 1_000_000)
        assert c == 3.0 + 15.0

    def test_prefix_match(self):
        rates = _resolve_rates("claude-opus-4-7-20250101")
        assert rates == PRICING["claude-opus-4-7"]

    def test_unknown_falls_to_default(self):
        rates = _resolve_rates("totally-unknown-model-xyz")
        assert rates == PRICING["_default"]

    def test_zero_tokens_zero_cost(self):
        assert compute_cost("gpt-5", 0, 0) == 0.0

    def test_negative_guard(self):
        assert compute_cost("gpt-5", -1, 5) == 0.0

    def test_free_tier(self):
        assert compute_cost("glm-4.6", 1_000_000, 1_000_000) == 0.0
