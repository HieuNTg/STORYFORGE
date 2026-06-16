"""Tests for D3 async/sync split: StoryEnhancer (Sprint 3 P5).

Coverage:
1. enhance_story_async works inside pytest.mark.asyncio with stub
2. enhance_with_feedback_async works inside pytest.mark.asyncio with stub
3. enhance_story sync wrapper works outside any loop
4. enhance_with_feedback sync wrapper works outside any loop
5. Calling enhance_story from inside a running loop raises RuntimeError naming _async
6. Calling enhance_with_feedback from inside a running loop raises RuntimeError naming _async
7. ThreadPoolExecutor escape hatch is gone from enhancer module source
"""

from __future__ import annotations

import inspect
from unittest.mock import patch

import pytest

from models.schemas import (
    Chapter,
    EnhancedStory,
    SimulationResult,
    StoryDraft,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_chapter(n: int = 1) -> Chapter:
    return Chapter(
        chapter_number=n,
        title=f"Chương {n}",
        content="Nội dung chương test.",
        word_count=5,
    )


def _make_draft(num_chapters: int = 1) -> StoryDraft:
    chapters = [_make_chapter(i + 1) for i in range(num_chapters)]
    return StoryDraft(
        title="Test Story",
        genre="romance",
        chapters=chapters,
        characters=[],
    )


def _make_sim_result() -> SimulationResult:
    return SimulationResult(
        events=[],
        drama_suggestions=["suggestion 1"],
        drama_score=0.7,
    )


def _make_enhanced(draft: StoryDraft) -> EnhancedStory:
    return EnhancedStory(
        title=draft.title,
        genre=draft.genre,
        chapters=list(draft.chapters),
        enhancement_notes=[],
    )


# ---------------------------------------------------------------------------
# Helper: patch enhance_story_async to return a stub EnhancedStory directly
# ---------------------------------------------------------------------------


def _patch_enhance_story_async(enhanced: EnhancedStory):
    """Return a context manager that replaces enhance_story_async with an AsyncMock."""

    async def _stub(self, draft, sim_result, *args, **kwargs):  # noqa: ARG001
        return enhanced

    return patch(
        "pipeline.layer2_enhance.enhancer.StoryEnhancer.enhance_story_async",
        new=_stub,
    )


def _patch_feedback_llm_validators():
    """Stub the LLM-backed validators enhance_with_feedback_async calls after rewrite.

    Without these, validate_coherence/apply_contract_gate hit the real LLM
    client and hang the suite in its retry/sleep loop.
    """
    return (
        patch(
            "pipeline.layer2_enhance.coherence_validator.validate_coherence",
            return_value=[],
        ),
        patch(
            "pipeline.layer2_enhance.contract_gate.apply_contract_gate",
            return_value={"rewrites": 0, "total_failures": 0},
        ),
    )


# ---------------------------------------------------------------------------
# 1. enhance_story_async works inside pytest.mark.asyncio
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enhance_story_async_runs_in_loop():
    """enhance_story_async completes and returns EnhancedStory."""
    from pipeline.layer2_enhance.enhancer import StoryEnhancer

    draft = _make_draft(1)
    sim = _make_sim_result()
    expected = _make_enhanced(draft)

    with _patch_enhance_story_async(expected):
        enhancer = StoryEnhancer()
        result = await enhancer.enhance_story_async(draft, sim)

    assert isinstance(result, EnhancedStory)
    assert result.title == draft.title


# ---------------------------------------------------------------------------
# 2. enhance_with_feedback_async works inside pytest.mark.asyncio
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enhance_with_feedback_async_runs_in_loop():
    """enhance_with_feedback_async completes without calling the sync wrapper."""
    from pipeline.layer2_enhance.enhancer import StoryEnhancer

    draft = _make_draft(1)
    sim = _make_sim_result()
    expected = _make_enhanced(draft)

    coherence_patch, gate_patch = _patch_feedback_llm_validators()
    with _patch_enhance_story_async(expected), coherence_patch, gate_patch:
        # Also stub _find_weak_chapters so no LLM call is made
        enhancer = StoryEnhancer()
        with patch.object(enhancer, "_find_weak_chapters", return_value=[]):
            result = await enhancer.enhance_with_feedback_async(draft, sim)

    assert isinstance(result, EnhancedStory)


# ---------------------------------------------------------------------------
# 3. enhance_story sync wrapper works outside any loop
# ---------------------------------------------------------------------------


def test_enhance_story_sync_outside_loop():
    """enhance_story (sync wrapper) succeeds when there is no running event loop."""
    from pipeline.layer2_enhance.enhancer import StoryEnhancer

    draft = _make_draft(1)
    sim = _make_sim_result()
    expected = _make_enhanced(draft)

    with _patch_enhance_story_async(expected):
        enhancer = StoryEnhancer()
        result = enhancer.enhance_story(draft, sim)

    assert isinstance(result, EnhancedStory)
    assert result.title == draft.title


# ---------------------------------------------------------------------------
# 4. enhance_with_feedback sync wrapper works outside any loop
# ---------------------------------------------------------------------------


def test_enhance_with_feedback_sync_outside_loop():
    """enhance_with_feedback (sync wrapper) succeeds when there is no running loop."""
    from pipeline.layer2_enhance.enhancer import StoryEnhancer

    draft = _make_draft(1)
    sim = _make_sim_result()
    expected = _make_enhanced(draft)

    coherence_patch, gate_patch = _patch_feedback_llm_validators()
    with _patch_enhance_story_async(expected), coherence_patch, gate_patch:
        enhancer = StoryEnhancer()
        with patch.object(enhancer, "_find_weak_chapters", return_value=[]):
            result = enhancer.enhance_with_feedback(draft, sim)

    assert isinstance(result, EnhancedStory)


# ---------------------------------------------------------------------------
# 5. enhance_story sync wrapper raises from a running loop
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enhance_story_raises_from_running_loop():
    """enhance_story raises RuntimeError and names enhance_story_async in message."""
    from pipeline.layer2_enhance.enhancer import StoryEnhancer

    draft = _make_draft(1)
    sim = _make_sim_result()

    enhancer = StoryEnhancer()
    with pytest.raises(RuntimeError) as exc_info:
        enhancer.enhance_story(draft, sim)

    assert "enhance_story_async" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 6. enhance_with_feedback sync wrapper raises from a running loop
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enhance_with_feedback_raises_from_running_loop():
    """enhance_with_feedback raises RuntimeError and names enhance_with_feedback_async."""
    from pipeline.layer2_enhance.enhancer import StoryEnhancer

    draft = _make_draft(1)
    sim = _make_sim_result()

    enhancer = StoryEnhancer()
    with pytest.raises(RuntimeError) as exc_info:
        enhancer.enhance_with_feedback(draft, sim)

    assert "enhance_with_feedback_async" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 7. ThreadPoolExecutor escape hatch is gone from enhancer module source
# ---------------------------------------------------------------------------


def test_no_threadpool_asyncio_run_escape_in_enhancer():
    """Prove the submit(asyncio.run, coro) escape pattern no longer exists in enhancer."""
    import pipeline.layer2_enhance.enhancer as _mod

    src = inspect.getsource(_mod)
    assert ".submit(asyncio.run" not in src, (
        "ThreadPoolExecutor escape hatch (.submit(asyncio.run, ...)) found in enhancer.py — "
        "this pattern must be removed per Sprint 3 P5."
    )
