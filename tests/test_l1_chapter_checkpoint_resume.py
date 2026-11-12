"""Task 15 fix: L1 per-chapter checkpoints must carry the live partial draft.

``CheckpointManager.save_chapter`` dumps ``output``. During L1,
``output.story_draft`` is only set after ``generate_full_story`` returns, so
the batch checkpoint callback has to publish the live draft first. Otherwise
the checkpoint holds ``story_draft=None`` and ``resume_from_chapter`` restarts
at chapter 1. This must work with the agent debate on and off.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from models.schemas import PipelineOutput, StoryContext, StoryDraft
from pipeline.layer1_story.batch_generator import BatchChapterGenerator
from pipeline.orchestrator_checkpoint import CheckpointManager
from tests.test_batch_generator_behavior import (
    _WORLD,
    _make_chapter,
    _make_outline,
    _mock_generator,
)

BATCH_SIZE = 2
WRITTEN = 4  # 2 batches of 2


def _run_batches(batch_checkpoint_callback, n_chapters=WRITTEN, title="T"):
    gen = _mock_generator(batch_size=BATCH_SIZE)
    gen._write_chapter_with_long_context.side_effect = lambda *a, **kw: (
        _make_chapter(a[5].chapter_number)
    )
    draft = StoryDraft(title=title, genre="G")
    with patch("pipeline.layer1_story.chapter_finalizer.process_chapter_post_write"):
        BatchChapterGenerator(gen).generate_chapters(
            draft=draft,
            outlines=[_make_outline(i) for i in range(1, n_chapters + 1)],
            story_context=StoryContext(total_chapters=n_chapters),
            title=title,
            genre="G",
            style="S",
            characters=[],
            world=_WORLD,
            batch_checkpoint_callback=batch_checkpoint_callback,
        )
    return draft


def test_batch_checkpoint_callback_receives_live_draft():
    seen = []

    def cb(batch_done, total_batches, draft):
        seen.append((batch_done, total_batches, len(draft.chapters)))

    _run_batches(cb)
    assert seen == [(1, 2, 2), (2, 2, 4)]


def test_two_arg_batch_checkpoint_callback_still_supported():
    seen = []
    _run_batches(lambda batch_done, total_batches: seen.append((batch_done, total_batches)))
    assert seen == [(1, 2), (2, 2)]


@pytest.mark.parametrize("debate", [True, False])
async def test_l1_chapter_checkpoint_resumes_after_written_chapters(tmp_path, debate):
    from pipeline.orchestrator import PipelineOrchestrator

    title = f"Resume {'debate' if debate else 'plain'}"

    def _fake_generate_full_story(*args, **kwargs):
        # The real batch loop with a mocked chapter writer; then L1 "crashes"
        # before generate_full_story returns, as an interrupted run would.
        _run_batches(kwargs.get("batch_checkpoint_callback"), title=title)
        raise RuntimeError("simulated crash after 2 batches")

    with (
        patch("services.output_paths.OUTPUT_ROOT", str(tmp_path)),
        patch(
            "pipeline.orchestrator_checkpoint.CHECKPOINT_DIR",
            os.path.join(str(tmp_path), "checkpoints"),
        ),
        patch(
            "services.llm_client.LLMClient.check_connection",
            return_value=(True, "OK"),
        ),
        patch("pipeline.agents.register_all_agents", lambda: None),
        patch(
            "pipeline.agents.agent_registry.AgentRegistry.run_review_cycle",
            MagicMock(return_value=[]),
        ),
        patch(
            "pipeline.layer1_story.generator.StoryGenerator.generate_full_story",
            side_effect=_fake_generate_full_story,
        ),
    ):
        orch = PipelineOrchestrator()
        orch.config.pipeline.enable_agent_debate = debate
        orch.config.pipeline.enable_chapter_checkpoint = True
        orch.config.pipeline.chapter_batch_size = BATCH_SIZE
        orch.config.pipeline.chapter_checkpoint_every_n_batches = 1
        orch.config.pipeline.chapter_checkpoint_keep_last = 5
        _orig_save_chapter = orch.checkpoint.save_chapter
        saved_paths: list[str] = []

        def _save_chapter_sync(**kw):
            path = _orig_save_chapter(**{**kw, "background": False})
            saved_paths.append(path)
            return path

        orch.checkpoint.save_chapter = _save_chapter_sync
        output = await orch.run_full_pipeline(
            title=title,
            genre="G",
            idea="ý tưởng",
            num_chapters=6,
            num_characters=2,
            word_count=300,
            enable_agents=debate,
            enable_scoring=False,
            enable_media=False,
        )

        assert output.status == "error"  # the simulated crash
        assert len(saved_paths) == 2
        last = saved_paths[-1]
        assert f"_ch{WRITTEN}_layer1_" in os.path.basename(last)

        fresh = CheckpointManager(
            output=PipelineOutput(),
            analyzer=MagicMock(),
            simulator=MagicMock(),
            enhancer=MagicMock(),
        )
        resumed, next_ch = fresh.resume_from_chapter(last)

    assert resumed.story_draft is not None
    assert [c.chapter_number for c in resumed.story_draft.chapters] == [1, 2, 3, 4]
    assert next_ch == WRITTEN + 1
