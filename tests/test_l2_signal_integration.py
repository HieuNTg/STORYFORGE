"""Phase A — L1 signal integration tests."""

from unittest.mock import MagicMock, patch

import pytest

from models.schemas import (
    Chapter, Character, PlotThread, SimulationResult, StructuredSummary,
)
from pipeline.layer2_enhance._agent import CharacterAgent
from pipeline.layer2_enhance.adaptive_intensity import AdaptiveController, DRAMA_TARGET
from pipeline.layer2_enhance.scene_enhancer import (
    SceneEnhancer, _build_preserve_facts, _build_thread_status,
)
from pipeline.layer2_enhance.simulator import DramaSimulator


def _char(name="A"):
    return Character(name=name, role="chính", personality="p")


def _thread(status="open", urgency=3, chars=("A",)):
    return PlotThread(
        thread_id="t1",
        description="revenge thread",
        planted_chapter=1,
        status=status,
        involved_characters=list(chars),
        urgency=urgency,
    )


def test_character_agent_waypoint_floor_set():
    agent = CharacterAgent(_char("A"))
    assert agent.waypoint_floor == 0.0
    assert agent.waypoint_stage == ""
    agent.set_waypoint("khủng hoảng", 0.6)
    assert agent.waypoint_stage == "khủng hoảng"
    assert agent.waypoint_floor == pytest.approx(0.6)
    agent.set_waypoint("peak", 1.5)
    assert agent.waypoint_floor == 1.0
    agent.set_waypoint("neg", -0.2)
    assert agent.waypoint_floor == 0.0


def test_simulator_applies_arc_waypoints():
    sim = DramaSimulator()
    sim.setup_agents(
        [_char("A"), _char("B")],
        [],
        arc_waypoints=[
            {"character": "A", "stage_name": "climax", "progress_pct": 0.8, "chapter_range": "1-3"},
            {"character": "B", "stage_name": "setup", "progress_pct": 0.2, "chapter_range": "5-10"},
        ],
        current_chapter=2,
    )
    assert sim.agents["A"].waypoint_floor == pytest.approx(0.8)
    assert sim.agents["A"].waypoint_stage == "climax"
    assert sim.agents["B"].waypoint_floor == 0.0


def test_simulator_thread_gate_blocks_resolved():
    sim = DramaSimulator()
    sim.setup_agents([_char("A")], [], threads=[_thread(status="resolved")])
    evt = MagicMock(event_type="hy_sinh", characters_involved=["A"])
    assert sim._is_event_thread_valid(evt) is False


def test_simulator_thread_gate_blocks_premature_open():
    sim = DramaSimulator()
    sim.setup_agents([_char("A")], [], threads=[_thread(status="open", urgency=2)])
    evt = MagicMock(event_type="đảo_ngược", characters_involved=["A"])
    assert sim._is_event_thread_valid(evt) is False


def test_simulator_thread_gate_allows_high_urgency():
    sim = DramaSimulator()
    sim.setup_agents([_char("A")], [], threads=[_thread(status="open", urgency=5)])
    evt = MagicMock(event_type="hy_sinh", characters_involved=["A"])
    assert sim._is_event_thread_valid(evt) is True


def test_simulator_thread_gate_passes_non_resolution():
    sim = DramaSimulator()
    sim.setup_agents([_char("A")], [], threads=[_thread(status="resolved")])
    evt = MagicMock(event_type="xung_đột", characters_involved=["A"])
    assert sim._is_event_thread_valid(evt) is True


def test_adaptive_pacing_slow_down_target():
    ctrl = AdaptiveController({"temperature": 0.85}, pacing_directive="slow_down")
    assert ctrl.drama_target == 0.55


def test_adaptive_pacing_escalate_target():
    ctrl = AdaptiveController({"temperature": 0.85}, pacing_directive="escalate")
    assert ctrl.drama_target == 0.75


def test_adaptive_pacing_default_target():
    ctrl = AdaptiveController({"temperature": 0.85})
    assert ctrl.drama_target == DRAMA_TARGET


def test_build_preserve_facts_none():
    assert _build_preserve_facts(None) == "Không có"


def test_build_preserve_facts_with_threads():
    summary = StructuredSummary(threads_advanced=["t1: revenge progresses"])
    text = _build_preserve_facts(summary)
    assert "[thread]" in text and "revenge" in text


def test_build_thread_status_lines():
    out = _build_thread_status([_thread(status="open", urgency=4)])
    assert "t1" in out and "open" in out and "4/5" in out


def test_scenes_from_summary_skip_when_sparse():
    ch = Chapter(chapter_number=1, title="t", content="short content")
    summary = StructuredSummary()
    assert SceneEnhancer._scenes_from_summary(ch, summary) == []


def test_scenes_from_summary_builds_when_rich():
    ch = Chapter(chapter_number=1, title="t", content="A" * 1200)
    summary = StructuredSummary()
    object.__setattr__(summary, "key_events", ["e1", "e2", "e3", "e4"])
    scenes = SceneEnhancer._scenes_from_summary(ch, summary)
    assert len(scenes) >= 3
    assert all("content" in s and s["content"] for s in scenes)


def test_enhance_chapter_by_scenes_skips_decompose_with_summary():
    enhancer = SceneEnhancer()
    ch = Chapter(chapter_number=1, title="t", content="X" * 600)
    sim_result = SimulationResult(events=[])
    summary = MagicMock()
    summary.key_events = ["a", "b", "c"]
    summary.threads_advanced = []
    with patch.object(enhancer, "decompose_chapter_content") as dec, \
         patch.object(enhancer, "score_scenes", return_value=[]):
        dec.return_value = []
        enhancer.enhance_chapter_by_scenes(
            ch, sim_result, "drama", chapter_summary=summary,
        )
        dec.assert_not_called()


def test_chapter_contract_field_assignable():
    from models.narrative_schemas import ChapterContract
    ch = Chapter(chapter_number=1, title="t", content="c")
    assert ch.contract is None
    ch.contract = ChapterContract(chapter_number=1, must_mention_characters=["A"])
    assert ch.contract.must_mention_characters == ["A"]
