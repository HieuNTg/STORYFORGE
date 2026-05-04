"""Tests for D3 async/sync split: simulator.py + agent_registry.py (Sprint 3 P4).

Coverage:
1. run_simulation_async works inside pytest.mark.asyncio
2. run_simulation (sync) works in plain test (no event loop)
3. Calling sync run_simulation from a running loop raises RuntimeError
4-6. Same three for run_review_cycle / run_review_cycle_async
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models.schemas import (
    AgentReview,
    Character,
    PipelineOutput,
    Relationship,
    RelationType,
    SimulationResult,
)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _make_characters() -> list[Character]:
    return [
        Character(name="Lan", role="main", personality="brave", background="orphan", motivation="revenge"),
        Character(name="Hung", role="support", personality="wise", background="scholar", motivation="peace"),
    ]


def _make_relationships(chars: list[Character]) -> list[Relationship]:
    return [
        Relationship(
            character_a=chars[0].name,
            character_b=chars[1].name,
            relation_type=RelationType.ALLY,
            intensity=0.6,
            tension=0.3,
            description="allies",
        )
    ]


def _make_output() -> PipelineOutput:
    return PipelineOutput(status="running", current_layer=1)


def _stub_run_simulation_result() -> SimulationResult:
    return SimulationResult(events=[], updated_relationships=[], drama_suggestions=[], actual_rounds=1)


def _stub_agent_review() -> AgentReview:
    return AgentReview(agent_role="test", agent_name="stub_agent", score=0.9, approved=True)


# ---------------------------------------------------------------------------
# 1. run_simulation_async works inside asyncio test
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_simulation_async_returns_result():
    """run_simulation_async returns SimulationResult when all LLM calls are stubbed."""
    chars = _make_characters()
    rels = _make_relationships(chars)

    with patch(
        "pipeline.layer2_enhance.simulator.DramaSimulator.setup_agents"
    ), patch(
        "pipeline.layer2_enhance.simulator.DramaSimulator.simulate_round_async",
        new_callable=AsyncMock,
        return_value=[],
    ), patch(
        "pipeline.layer2_enhance.simulator.DramaSimulator.evaluate_drama",
        return_value={"overall_drama_score": 0.7, "events": [], "relationship_changes": []},
    ), patch(
        "pipeline.layer2_enhance.simulator.DramaSimulator._generate_suggestions",
        return_value={"suggestions": [], "character_arcs": {}, "tension_points": {}},
    ), patch(
        "pipeline.layer2_enhance.simulator._ADAPTIVE_AVAILABLE",
        False,
    ):
        from pipeline.layer2_enhance.simulator import DramaSimulator

        sim = DramaSimulator.__new__(DramaSimulator)
        sim.agents = {}
        sim.relationships = rels
        sim.all_posts = []
        sim.knowledge = None
        sim.causal_graph = None
        sim.adaptive = None
        sim.foreshadowing_plan = []
        sim.trust_network = {}
        sim._psychology_engine = None
        sim._intensity = {"temperature": 0.9, "escalation_scale": 1.0, "max_escalations": 2, "reaction_depth": 1}
        sim.conflict_web = []
        sim.threads = []

        result = await sim.run_simulation_async(
            characters=chars,
            relationships=rels,
            genre="romance",
            num_rounds=1,
        )

    assert isinstance(result, SimulationResult)


# ---------------------------------------------------------------------------
# 2. run_simulation (sync) works in a plain (non-async) test
# ---------------------------------------------------------------------------

def test_run_simulation_sync_works_outside_loop():
    """Sync run_simulation completes without error when no event loop is running."""
    chars = _make_characters()
    rels = _make_relationships(chars)

    async def _stub(*args, **kwargs):
        return _stub_run_simulation_result()

    with patch(
        "pipeline.layer2_enhance.simulator.DramaSimulator.run_simulation_async",
        side_effect=_stub,
    ):
        from pipeline.layer2_enhance.simulator import DramaSimulator

        sim = DramaSimulator.__new__(DramaSimulator)
        result = sim.run_simulation(
            characters=chars,
            relationships=rels,
            genre="romance",
            num_rounds=1,
        )

    assert isinstance(result, SimulationResult)


# ---------------------------------------------------------------------------
# 3. Calling sync run_simulation from inside a running loop raises RuntimeError
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_simulation_sync_raises_inside_loop():
    """Sync run_simulation raises RuntimeError with correct message when loop is running."""
    chars = _make_characters()
    rels = _make_relationships(chars)

    from pipeline.layer2_enhance.simulator import DramaSimulator

    sim = DramaSimulator.__new__(DramaSimulator)

    with pytest.raises(RuntimeError, match="run_simulation_async"):
        sim.run_simulation(characters=chars, relationships=rels, genre="romance", num_rounds=1)


# ---------------------------------------------------------------------------
# 4. run_review_cycle_async works inside asyncio test
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_review_cycle_async_returns_reviews():
    """run_review_cycle_async returns list[AgentReview] when agents are stubbed."""
    from pipeline.agents.agent_registry import AgentRegistry

    # Reset singleton for test isolation
    AgentRegistry._instance = None
    registry = AgentRegistry()

    stub_review = _stub_agent_review()

    mock_agent = MagicMock()
    mock_agent.name = "stub"
    mock_agent.role = "test"
    mock_agent.layers = [1]
    mock_agent.review = MagicMock(return_value=stub_review)

    registry._agents = [mock_agent]

    output = _make_output()

    with patch(
        "pipeline.agents.agent_registry.AgentRegistry._run_tier_parallel_async",
        new_callable=AsyncMock,
        return_value=[stub_review],
    ), patch(
        "pipeline.agents.agent_registry.ConfigManager"
    ) as mock_cfg:
        mock_cfg.return_value.pipeline.enable_agent_debate = False
        reviews = await registry.run_review_cycle_async(output, layer=1, max_iterations=1)

    assert len(reviews) == 1
    assert reviews[0].approved is True

    # Cleanup singleton
    AgentRegistry._instance = None


# ---------------------------------------------------------------------------
# 5. run_review_cycle (sync) works in a plain test
# ---------------------------------------------------------------------------

def test_run_review_cycle_sync_works_outside_loop():
    """Sync run_review_cycle completes without error when no event loop is running."""
    from pipeline.agents.agent_registry import AgentRegistry

    AgentRegistry._instance = None
    registry = AgentRegistry()
    registry._agents = []
    output = _make_output()

    # Empty agents list returns [] immediately without entering the loop
    result = registry.run_review_cycle(output, layer=99, max_iterations=1)
    assert result == []

    AgentRegistry._instance = None


# ---------------------------------------------------------------------------
# 6. Calling sync run_review_cycle from inside a running loop raises RuntimeError
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_review_cycle_sync_raises_inside_loop():
    """Sync run_review_cycle raises RuntimeError with correct message when loop is running."""
    from pipeline.agents.agent_registry import AgentRegistry

    AgentRegistry._instance = None
    registry = AgentRegistry()
    registry._agents = []
    output = _make_output()

    with pytest.raises(RuntimeError, match="run_review_cycle_async"):
        # layer=99 so get_agents_for_layer returns [] — but the loop detection
        # fires BEFORE any business logic, so it still raises.
        registry.run_review_cycle(output, layer=1, max_iterations=1)

    AgentRegistry._instance = None
