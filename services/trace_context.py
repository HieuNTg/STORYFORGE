"""Pipeline trace + per-LLM-call telemetry (Sprint 1 Task 2).

A PipelineTrace is attached to a contextvar for the duration of a pipeline
run. LLMClient records each call (tokens, cost, duration, success) into the
active trace. Orchestrator summarizes breakdowns into PipelineOutput.trace.

Isolation: contextvars.ContextVar so concurrent pipelines don't mix calls.
Per-chapter / per-module tags are ALSO ContextVars — each thread spawned via
asyncio.to_thread() gets its own copy so parallel batches don't race.
"""
from __future__ import annotations

import contextvars
import uuid
from dataclasses import dataclass, field
from typing import Optional

_current_trace: contextvars.ContextVar[Optional["PipelineTrace"]] = (
    contextvars.ContextVar("storyforge_trace", default=None)
)
_current_chapter: contextvars.ContextVar[Optional[int]] = (
    contextvars.ContextVar("storyforge_trace_chapter", default=None)
)
_current_module: contextvars.ContextVar[str] = (
    contextvars.ContextVar("storyforge_trace_module", default="")
)


@dataclass
class LLMCall:
    call_id: str
    trace_id: str
    chapter_number: Optional[int]
    module: str
    model: str
    model_tier: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    duration_ms: int
    success: bool
    error: str = ""


@dataclass
class RagEventStats:
    """Lightweight RAG telemetry (Sprint 2 Task 1). Not LLM-backed, so not in `calls`."""
    chapters_indexed: int = 0
    chunks_indexed_total: int = 0
    retrievals_performed: int = 0
    retrievals_with_hits: int = 0
    chunks_retrieved_total: int = 0
    index_latencies_ms: list[float] = field(default_factory=list)
    retrieval_latencies_ms: list[float] = field(default_factory=list)

    def record_index(self, chunks: int, duration_ms: float) -> None:
        if chunks > 0:
            self.chapters_indexed += 1
            self.chunks_indexed_total += chunks
        self.index_latencies_ms.append(float(duration_ms))

    def record_retrieval(self, chunks: int, duration_ms: float) -> None:
        self.retrievals_performed += 1
        if chunks > 0:
            self.retrievals_with_hits += 1
            self.chunks_retrieved_total += chunks
        self.retrieval_latencies_ms.append(float(duration_ms))

    def summary(self) -> dict:
        def _p(samples: list[float], q: float) -> float:
            if not samples:
                return 0.0
            xs = sorted(samples)
            idx = min(len(xs) - 1, int(q * (len(xs) - 1) + 0.5))
            return round(xs[idx], 2)

        avg_retrieved = (
            round(self.chunks_retrieved_total / self.retrievals_performed, 2)
            if self.retrievals_performed else 0.0
        )
        return {
            "chapters_indexed": self.chapters_indexed,
            "chunks_indexed_total": self.chunks_indexed_total,
            "retrievals_performed": self.retrievals_performed,
            "retrievals_with_hits": self.retrievals_with_hits,
            "avg_chunks_retrieved": avg_retrieved,
            "index_latency_ms_p50": _p(self.index_latencies_ms, 0.50),
            "index_latency_ms_p95": _p(self.index_latencies_ms, 0.95),
            "retrieval_latency_ms_p50": _p(self.retrieval_latencies_ms, 0.50),
            "retrieval_latency_ms_p95": _p(self.retrieval_latencies_ms, 0.95),
        }


@dataclass
class PipelineTrace:
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    session_id: str = ""
    # Story title — used by services.usage_history to attribute LLM calls to
    # the correct ``<slug>_layer{L}.usage.json`` sidecar. Empty disables write.
    title: str = ""
    layer: int = 1
    calls: list[LLMCall] = field(default_factory=list)
    rag_stats: RagEventStats = field(default_factory=RagEventStats)

    def add_call(self, call: LLMCall) -> None:
        self.calls.append(call)

    def total_cost(self) -> float:
        return sum(c.cost_usd for c in self.calls)

    def total_tokens(self) -> int:
        return sum(c.total_tokens for c in self.calls)

    def cost_by_module(self) -> dict[str, float]:
        out: dict[str, float] = {}
        for c in self.calls:
            key = c.module or "unknown"
            out[key] = out.get(key, 0.0) + c.cost_usd
        return out

    def cost_by_chapter(self) -> dict[int, float]:
        out: dict[int, float] = {}
        for c in self.calls:
            if c.chapter_number is None:
                continue
            out[c.chapter_number] = out.get(c.chapter_number, 0.0) + c.cost_usd
        return out

    def summary(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "total_calls": len(self.calls),
            "total_tokens": self.total_tokens(),
            "total_cost_usd": round(self.total_cost(), 6),
            "cost_by_module": {k: round(v, 6) for k, v in self.cost_by_module().items()},
            "cost_by_chapter": {k: round(v, 6) for k, v in self.cost_by_chapter().items()},
            "rag": self.rag_stats.summary(),
        }


def get_trace() -> Optional[PipelineTrace]:
    return _current_trace.get()


def set_trace(trace: Optional[PipelineTrace]) -> contextvars.Token:
    return _current_trace.set(trace)


def clear_trace() -> None:
    _current_trace.set(None)
    _current_chapter.set(None)
    _current_module.set("")


def set_module(module: str) -> contextvars.Token:
    return _current_module.set(module)


def get_module() -> str:
    return _current_module.get()


def set_chapter(chapter: Optional[int]) -> contextvars.Token:
    return _current_chapter.set(chapter)


def get_chapter() -> Optional[int]:
    return _current_chapter.get()
