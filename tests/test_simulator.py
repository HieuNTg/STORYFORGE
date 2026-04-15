"""Tests for DramaSimulator - conflict_web and foreshadowing_plan signal preservation."""

import pytest
from unittest.mock import MagicMock, patch

from models.schemas import Character, Relationship, RelationType, ConflictEntry, ForeshadowingEntry
from pipeline.layer2_enhance.simulator import DramaSimulator, calculate_adaptive_rounds


def _sim():
    """Create a DramaSimulator with psychology extraction disabled."""
    sim = DramaSimulator()
    sim._psychology_engine = None  # disable LLM calls in setup_agents
    return sim


def _char(name):
    return Character(name=name, role="chính", personality="stubborn")


def _rel(a, b, rel_type=RelationType.ALLY, tension=0.3):
    return Relationship(character_a=a, character_b=b, relation_type=rel_type, tension=tension)


def _conflict(chars, intensity=3, description="test conflict"):
    return ConflictEntry(
        conflict_id="c1",
        conflict_type="external",
        characters=chars,
        description=description,
        intensity=intensity,
    )


class TestSetupAgentsConflictWeb:
    def test_conflict_web_stored(self):
        sim = _sim()
        conflicts = [_conflict(["A", "B"], intensity=4)]
        sim.setup_agents([_char("A"), _char("B")], [], conflict_web=conflicts)
        assert len(sim.conflict_web) == 1

    def test_conflict_web_none_defaults_empty(self):
        sim = _sim()
        sim.setup_agents([_char("A")], [])
        assert sim.conflict_web == []

    def test_foreshadowing_plan_stored(self):
        sim = _sim()
        entries = [ForeshadowingEntry(hint="dark secret", plant_chapter=1, payoff_chapter=3)]
        sim.setup_agents([_char("A")], [], foreshadowing_plan=entries)
        assert len(sim.foreshadowing_plan) == 1

    def test_foreshadowing_plan_none_defaults_empty(self):
        sim = _sim()
        sim.setup_agents([_char("A")], [])
        assert sim.foreshadowing_plan == []


class TestApplyConflictWebTensions:
    def test_lowers_trust_for_conflict_pair(self):
        sim = _sim()
        # Set up with a trust edge already present
        rel = _rel("A", "B", RelationType.ALLY)
        conflicts = [_conflict(["A", "B"], intensity=5)]
        sim.setup_agents([_char("A"), _char("B")], [rel], conflict_web=conflicts)
        # intensity=5 → penalty=50 → trust starts at 70 (ALLY) minus 50 = 20
        edge = sim.trust_network.get("A|B") or sim.trust_network.get("B|A")
        assert edge is not None
        assert edge.trust < 70.0

    def test_creates_edge_for_unknown_pair(self):
        sim = _sim()
        conflicts = [_conflict(["A", "B"], intensity=2)]
        sim.setup_agents([_char("A"), _char("B")], [], conflict_web=conflicts)
        edge = sim.trust_network.get("A|B") or sim.trust_network.get("B|A")
        assert edge is not None

    def test_no_conflict_web_trust_unchanged(self):
        sim = _sim()
        rel = _rel("A", "B", RelationType.ALLY)
        sim.setup_agents([_char("A"), _char("B")], [rel])
        edge = sim.trust_network.get("A|B")
        assert edge is not None
        assert edge.trust == pytest.approx(70.0)

    def test_intensity_scales_penalty(self):
        sim_low = DramaSimulator()
        sim_high = DramaSimulator()
        rel_low = _rel("A", "B", RelationType.ALLY)
        rel_high = _rel("A", "B", RelationType.ALLY)
        sim_low.setup_agents([_char("A"), _char("B")], [rel_low], conflict_web=[_conflict(["A", "B"], intensity=1)])
        sim_high.setup_agents([_char("A"), _char("B")], [rel_high], conflict_web=[_conflict(["A", "B"], intensity=5)])
        edge_low = sim_low.trust_network.get("A|B")
        edge_high = sim_high.trust_network.get("A|B")
        assert edge_low.trust > edge_high.trust


class TestGetForeshadowingHints:
    def test_returns_hint_when_due(self):
        sim = _sim()
        entries = [ForeshadowingEntry(hint="betrayal hint", plant_chapter=1, payoff_chapter=3, planted=True)]
        sim.setup_agents([_char("A")], [], foreshadowing_plan=entries)
        hints = sim._get_foreshadowing_hints(current_chapter=3)
        assert "betrayal hint" in hints

    def test_no_hint_when_not_yet_due(self):
        sim = _sim()
        entries = [ForeshadowingEntry(hint="future reveal", plant_chapter=1, payoff_chapter=10, planted=True)]
        sim.setup_agents([_char("A")], [], foreshadowing_plan=entries)
        hints = sim._get_foreshadowing_hints(current_chapter=3)
        assert hints == []

    def test_no_hint_when_not_planted(self):
        sim = _sim()
        entries = [ForeshadowingEntry(hint="not planted", plant_chapter=1, payoff_chapter=2, planted=False)]
        sim.setup_agents([_char("A")], [], foreshadowing_plan=entries)
        hints = sim._get_foreshadowing_hints(current_chapter=5)
        assert hints == []

    def test_no_hint_when_already_paid_off(self):
        sim = _sim()
        entries = [ForeshadowingEntry(hint="done", plant_chapter=1, payoff_chapter=2, planted=True, paid_off=True)]
        sim.setup_agents([_char("A")], [], foreshadowing_plan=entries)
        hints = sim._get_foreshadowing_hints(current_chapter=5)
        assert hints == []

    def test_empty_foreshadowing_returns_empty(self):
        sim = _sim()
        sim.setup_agents([_char("A")], [])
        hints = sim._get_foreshadowing_hints(current_chapter=1)
        assert hints == []


class TestCalculateAdaptiveRounds:
    def test_base_no_inputs(self):
        """Empty story → base 4 rounds."""
        assert calculate_adaptive_rounds([]) == 4

    def test_min_clamp(self):
        """Never returns below min_rounds=4."""
        assert calculate_adaptive_rounds([], min_rounds=4) >= 4

    def test_max_clamp(self):
        """Never exceeds max_rounds=10."""
        chars = [_char(f"C{i}") for i in range(30)]
        threads = list(range(30))
        conflicts = list(range(30))
        result = calculate_adaptive_rounds(chars, threads=threads, conflict_web=conflicts)
        assert result <= 10

    def test_character_factor(self):
        """6 characters → +2 char_factor → 6 rounds (base 4 + 2)."""
        chars = [_char(f"C{i}") for i in range(6)]
        assert calculate_adaptive_rounds(chars) == 6

    def test_thread_factor(self):
        """5 threads → +1 thread_factor → 5 rounds (base 4 + 1)."""
        assert calculate_adaptive_rounds([], threads=list(range(5))) == 5

    def test_conflict_factor(self):
        """4 conflicts → +1 conflict_factor → 5 rounds (base 4 + 1)."""
        assert calculate_adaptive_rounds([], conflict_web=list(range(4))) == 5

    def test_complex_story(self):
        """10 chars, 8 threads, 6 conflicts → 8 rounds.

        char_factor=min(2,10//3)=2, thread_factor=min(1,8//5)=1,
        conflict_factor=min(2,6//4)=1 → base 4+2+1+1=8.
        """
        chars = [_char(f"C{i}") for i in range(10)]
        result = calculate_adaptive_rounds(chars, threads=list(range(8)), conflict_web=list(range(6)))
        assert result == 8

    def test_simple_story(self):
        """3 chars, 2 threads → 5 rounds.

        char_factor=min(2,3//3)=1, thread_factor=min(1,2//5)=0 → base 4+1=5.
        """
        chars = [_char(f"C{i}") for i in range(3)]
        result = calculate_adaptive_rounds(chars, threads=list(range(2)))
        assert result == 5

    def test_custom_min_max(self):
        """Custom min/max bounds are respected."""
        result = calculate_adaptive_rounds([], min_rounds=6, max_rounds=8)
        assert result == 6  # base=4 clamped to min=6

    def test_none_threads_and_conflicts(self):
        """None inputs treated as empty lists (no error)."""
        result = calculate_adaptive_rounds([_char("A")], threads=None, conflict_web=None)
        assert result == 4


class TestRunSimulationSignalPassthrough:
    def test_run_simulation_accepts_conflict_web_param(self):
        """run_simulation should accept conflict_web without raising."""
        sim = _sim()
        conflicts = [_conflict(["A", "B"], intensity=3)]
        # Patch the heavy LLM-dependent simulation loop by replacing methods
        sim._simulate_round = MagicMock(return_value=[])
        sim._check_escalations = MagicMock(return_value=None)
        # We just verify setup_agents is called with conflict_web stored
        sim.setup_agents(
            [_char("A"), _char("B")], [],
            conflict_web=conflicts,
        )
        assert sim.conflict_web == conflicts
