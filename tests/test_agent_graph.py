"""Tests for AgentDAG — topological sort, cycle detection, tiered execution."""
import pytest
from unittest.mock import MagicMock, patch
from pipeline.agents.agent_graph import AgentDAG, AgentNode
from pipeline.agents.base_agent import BaseAgent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_agent(name: str, depends_on: list[str], layers=None):
    """Create a lightweight mock that looks like a BaseAgent."""
    agent = MagicMock(spec=BaseAgent)
    agent.name = name
    agent.depends_on = depends_on
    agent.layers = layers or [1]
    return agent


# ---------------------------------------------------------------------------
# AgentNode
# ---------------------------------------------------------------------------

class TestAgentNode:
    def test_default_depends_on_is_empty(self):
        node = AgentNode(name="A")
        assert node.depends_on == []

    def test_agent_reference_stored(self):
        mock = _make_mock_agent("X", [])
        node = AgentNode(name="X", agent=mock)
        assert node.agent is mock


# ---------------------------------------------------------------------------
# AgentDAG construction
# ---------------------------------------------------------------------------

class TestAgentDAGConstruction:
    def test_add_node_registers_node(self):
        dag = AgentDAG()
        dag.add_node("A")
        assert "A" in dag._nodes

    def test_add_node_with_deps(self):
        dag = AgentDAG()
        dag.add_node("B", depends_on=["A"])
        assert dag._nodes["B"].depends_on == ["A"]

    def test_add_node_replaces_existing(self):
        dag = AgentDAG()
        dag.add_node("A", depends_on=[])
        dag.add_node("A", depends_on=["B"])
        assert dag._nodes["A"].depends_on == ["B"]

    def test_len(self):
        dag = AgentDAG()
        dag.add_node("A")
        dag.add_node("B", depends_on=["A"])
        assert len(dag) == 2

    def test_build_from_registry_populates_nodes(self):
        agents = [
            _make_mock_agent("A", []),
            _make_mock_agent("B", ["A"]),
        ]
        dag = AgentDAG()
        dag.build_from_registry(agents)
        assert "A" in dag._nodes
        assert "B" in dag._nodes

    def test_build_from_registry_stores_agent_ref(self):
        mock_a = _make_mock_agent("A", [])
        dag = AgentDAG()
        dag.build_from_registry([mock_a])
        assert dag._nodes["A"].agent is mock_a

    def test_build_from_registry_unknown_dep_warns(self):
        """Dependency pointing to unknown agent is dropped with a warning."""
        agents = [_make_mock_agent("B", ["UnknownAgent"])]
        dag = AgentDAG()
        with patch("pipeline.agents.agent_graph.logger") as mock_log:
            dag.build_from_registry(agents)
            mock_log.warning.assert_called_once()
        # Unknown dep should be stripped
        assert dag._nodes["B"].depends_on == []


# ---------------------------------------------------------------------------
# Topological sort
# ---------------------------------------------------------------------------

class TestTopologicalSort:
    def test_single_node_returns_one_tier(self):
        dag = AgentDAG()
        dag.add_node("A")
        assert dag._topological_sort() == [["A"]]

    def test_linear_chain_produces_separate_tiers(self):
        dag = AgentDAG()
        dag.add_node("A")
        dag.add_node("B", depends_on=["A"])
        dag.add_node("C", depends_on=["B"])
        tiers = dag._topological_sort()
        assert tiers == [["A"], ["B"], ["C"]]

    def test_parallel_deps_in_same_tier(self):
        dag = AgentDAG()
        dag.add_node("A")
        dag.add_node("B")
        dag.add_node("C", depends_on=["A", "B"])
        tiers = dag._topological_sort()
        assert tiers[0] == ["A", "B"]
        assert tiers[1] == ["C"]

    def test_four_tier_default_ordering(self):
        """Reproduce the default 4-tier StoryForge DAG using actual agent names."""
        dag = AgentDAG()
        dag.add_node("Chuyen Gia Nhan Vat")  # tier 0
        dag.add_node("Kiem Soat Vien",   depends_on=["Chuyen Gia Nhan Vat"])  # tier 1
        dag.add_node("Chuyen Gia Doi Thoai", depends_on=["Chuyen Gia Nhan Vat"])  # tier 1
        dag.add_node("Kiem Tra Van Phong",   depends_on=["Chuyen Gia Nhan Vat"])  # tier 1
        dag.add_node("Phan Tich Nhip Truyen", depends_on=["Chuyen Gia Nhan Vat"])  # tier 1
        dag.add_node("Nha Phe Binh Kich Tinh", depends_on=["Kiem Soat Vien", "Chuyen Gia Doi Thoai", "Kiem Tra Van Phong"])  # tier 2
        dag.add_node("Can Bang Doi Thoai", depends_on=["Chuyen Gia Doi Thoai"])  # tier 2
        dag.add_node("Bien Tap Truong",    depends_on=["Nha Phe Binh Kich Tinh", "Can Bang Doi Thoai", "Phan Tich Nhip Truyen"])  # tier 3

        tiers = dag._topological_sort()
        assert len(tiers) == 4
        assert tiers[0] == ["Chuyen Gia Nhan Vat"]
        assert "Bien Tap Truong" in tiers[3]

    def test_no_deps_all_agents_in_single_tier(self):
        """When no agent has deps, all run flat-parallel in one tier."""
        dag = AgentDAG()
        for name in ["A", "B", "C"]:
            dag.add_node(name)
        tiers = dag._topological_sort()
        assert len(tiers) == 1
        assert sorted(tiers[0]) == ["A", "B", "C"]

    def test_empty_dag_returns_empty(self):
        dag = AgentDAG()
        assert dag._topological_sort() == []


# ---------------------------------------------------------------------------
# Cycle detection
# ---------------------------------------------------------------------------

class TestCycleDetection:
    def test_validate_acyclic_returns_true(self):
        dag = AgentDAG()
        dag.add_node("A")
        dag.add_node("B", depends_on=["A"])
        assert dag.validate() is True

    def test_simple_cycle_raises(self):
        dag = AgentDAG()
        dag.add_node("A", depends_on=["B"])
        dag.add_node("B", depends_on=["A"])
        with pytest.raises(ValueError, match="Cycle detected"):
            dag.validate()

    def test_three_node_cycle_raises(self):
        dag = AgentDAG()
        dag.add_node("A", depends_on=["C"])
        dag.add_node("B", depends_on=["A"])
        dag.add_node("C", depends_on=["B"])
        with pytest.raises(ValueError):
            dag.validate()

    def test_get_execution_order_raises_on_cycle(self):
        dag = AgentDAG()
        dag.add_node("X", depends_on=["Y"])
        dag.add_node("Y", depends_on=["X"])
        with pytest.raises(ValueError):
            dag.get_execution_order()


# ---------------------------------------------------------------------------
# get_execution_order and get_agents_by_tier
# ---------------------------------------------------------------------------

class TestGetExecutionOrder:
    def test_returns_list_of_lists(self):
        dag = AgentDAG()
        dag.add_node("A")
        result = dag.get_execution_order()
        assert isinstance(result, list)
        assert all(isinstance(t, list) for t in result)

    def test_backward_compat_no_deps_single_tier(self):
        agents = [_make_mock_agent(n, []) for n in ["X", "Y", "Z"]]
        dag = AgentDAG()
        dag.build_from_registry(agents)
        tiers = dag.get_execution_order()
        assert len(tiers) == 1
        assert sorted(tiers[0]) == ["X", "Y", "Z"]

    def test_get_agents_by_tier_returns_agent_instances(self):
        mock_a = _make_mock_agent("A", [])
        mock_b = _make_mock_agent("B", ["A"])
        dag = AgentDAG()
        dag.build_from_registry([mock_a, mock_b])
        tiers = dag.get_agents_by_tier()
        assert len(tiers) == 2
        assert mock_a in tiers[0]
        assert mock_b in tiers[1]

    def test_get_agents_by_tier_filters_none_agents(self):
        dag = AgentDAG()
        dag.add_node("A")  # no agent reference
        dag.add_node("B", depends_on=["A"])
        tiers = dag.get_agents_by_tier()
        # Both tiers have no agent ref, so result should be empty lists filtered out
        assert all(len(t) == 0 for t in tiers)
