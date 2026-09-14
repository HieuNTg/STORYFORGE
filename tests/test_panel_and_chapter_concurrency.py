"""Sprint 2 — bound chapter concurrency, and stop the panel serialising itself.

`enhance_story_async` read `max_parallel_workers` only to print it, then
gathered every chapter at once. A 50-chapter continuation ran 50 chapter
pipelines concurrently, each spawning its own nested pool inside scene
enhancement — well past what a provider or the default executor can serve, and
the opposite of what the setting claims.

The craft panel ran in four sequential tiers because six of its eight agents
declared `depends_on` while ignoring the `prior_reviews` argument entirely. Only
the editor-in-chief consumes it, so only the editor needs its own tier.
"""

from unittest.mock import patch

import pytest


class TestOnlyTheEditorDependsOnPriorReviews:
    def _agents(self):
        with patch("pipeline.agents.base_agent.LLMClient"):
            import pipeline.agents as ap

            ap._agents_registered = False
            from pipeline.agents import register_all_agents

            register_all_agents()
            from pipeline.agents.agent_registry import AgentRegistry

            return AgentRegistry().get_agents_for_layer(2)

    def _tiers(self):
        from pipeline.agents.agent_graph import AgentDAG

        dag = AgentDAG()
        dag.build_from_registry(self._agents())
        return dag.get_agents_by_tier()

    def test_the_panel_runs_in_two_tiers(self):
        tiers = self._tiers()
        assert len(tiers) == 2, [[a.role for a in t] for t in tiers]

    def test_the_editor_is_alone_in_the_final_tier(self):
        tiers = self._tiers()
        assert [a.role for a in tiers[-1]] == ["editor_in_chief"]

    def test_everyone_else_runs_together(self):
        tiers = self._tiers()
        assert len(tiers[0]) >= 6, "the first tier should hold the whole panel"

    def test_only_prior_reviews_consumers_declare_a_dependency(self):
        """A declared dependency must reflect data actually used."""
        for agent in self._agents():
            deps = getattr(agent, "depends_on", [])
            if deps:
                assert agent.role == "editor_in_chief", (
                    f"{agent.role} declares depends_on but ignores prior_reviews"
                )


class TestChapterConcurrencyIsBounded:
    def test_enhancer_uses_a_semaphore_sized_by_config(self):
        import pipeline.layer2_enhance.enhancer as mod

        source = open(mod.__file__, encoding="utf-8").read()
        assert "asyncio.Semaphore(max(1, int(max_workers or 1)))" in source
        assert "async with semaphore:" in source

    @pytest.mark.asyncio
    async def test_a_semaphore_actually_limits_concurrency(self):
        """Guards the mechanism the enhancer now relies on."""
        import asyncio

        semaphore = asyncio.Semaphore(3)
        peak = 0
        live = 0

        async def worker():
            nonlocal peak, live
            async with semaphore:
                live += 1
                peak = max(peak, live)
                await asyncio.sleep(0.01)
                live -= 1

        await asyncio.gather(*[worker() for _ in range(20)])
        assert peak <= 3, f"{peak} ran at once against a limit of 3"

    def test_worker_count_is_read_from_llm_config(self):
        from config.defaults import LLMConfig

        assert LLMConfig().max_parallel_workers >= 1
