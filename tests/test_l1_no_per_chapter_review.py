"""Task 15: Layer 1 must not run a discarded agent review after every chapter.

The old per-chapter hook ran ``AgentRegistry.run_review_cycle`` once per
chapter while L1 was still writing and threw the result away. Only the full
post-L1 review (whose results land in ``output.reviews``) may call it.
"""

from __future__ import annotations

from unittest.mock import patch

from models.schemas import Chapter, StoryDraft
from pipeline.pipeline_utils import DraftIntegrityError

NUM_CHAPTERS = 3


def _fake_generate_full_story(*args, **kwargs):
    """Stand-in for L1: writes 3 chapters, firing the per-chapter hook like
    ``batch_generator`` does, so a passed callback would run 3 times."""
    callback = kwargs.get("chapter_complete_callback")
    draft = StoryDraft(title=kwargs.get("title", "T"), genre=kwargs.get("genre", "G"))
    for n in range(1, NUM_CHAPTERS + 1):
        ch = Chapter(chapter_number=n, title=f"Ch {n}", content=f"Nội dung {n}")
        draft.chapters.append(ch)
        if callback:
            try:
                callback(ch, draft, NUM_CHAPTERS)
            except Exception:
                pass
    _fake_generate_full_story.l1_done = True
    return draft


async def test_l1_runs_no_per_chapter_review_but_keeps_post_l1_review():
    from pipeline.orchestrator import PipelineOrchestrator

    calls_during_l1: list[int] = []
    calls_after_l1: list[int] = []

    def _fake_review_cycle(self, output, layer=1, max_iterations=3, **kwargs):
        if getattr(_fake_generate_full_story, "l1_done", False):
            calls_after_l1.append(max_iterations)
        else:
            calls_during_l1.append(max_iterations)
        return []

    _fake_generate_full_story.l1_done = False

    with (
        patch(
            "services.llm_client.LLMClient.check_connection",
            return_value=(True, "OK"),
        ),
        patch("pipeline.agents.register_all_agents", lambda: None),
        patch(
            "pipeline.agents.agent_registry.AgentRegistry.run_review_cycle",
            _fake_review_cycle,
        ),
        patch(
            "pipeline.layer1_story.generator.StoryGenerator.generate_full_story",
            side_effect=_fake_generate_full_story,
        ),
        patch(
            "services.knowledge_graph.StoryKnowledgeGraph.build_from_story_draft",
            side_effect=RuntimeError("skip KG in this test"),
        ),
        # Stop the run right after L1 + its post-L1 review.
        patch(
            "pipeline.orchestrator_layers.verify_draft_integrity",
            side_effect=DraftIntegrityError("stop after L1"),
        ),
    ):
        orch = PipelineOrchestrator()
        orch.config.pipeline.enable_agent_debate = True
        orch.config.pipeline.enable_chapter_checkpoint = False
        with patch.object(orch.checkpoint, "save", return_value="ckpt"):
            output = await orch.run_full_pipeline(
                title="Thử nghiệm",
                genre="tiên hiệp",
                idea="ý tưởng",
                num_chapters=NUM_CHAPTERS,
                num_characters=2,
                word_count=300,
                enable_agents=True,
                enable_scoring=False,
                enable_media=False,
            )

    assert output.story_draft is not None
    assert len(output.story_draft.chapters) == NUM_CHAPTERS
    assert calls_during_l1 == [], (
        f"run_review_cycle ran {len(calls_during_l1)}x during L1"
    )
    assert calls_after_l1 == [3], "post-L1 full review must still run exactly once"
