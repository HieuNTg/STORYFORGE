"""Tests for Layer 2 Phase 2 wiring: knowledge context in prompts, causal chain formatting, quality scoring."""

from unittest.mock import MagicMock, patch
from models.schemas import SimulationResult, SimulationEvent, Chapter, ChapterScore
from pipeline.layer2_enhance.knowledge_system import KnowledgeRegistry, KnowledgeItem
from pipeline.layer2_enhance.causal_chain import CausalGraph, CausalEvent
from pipeline.layer2_enhance.scene_enhancer import _format_events_with_causality


class TestKnowledgeRegistry:
    def test_register_secret(self):
        reg = KnowledgeRegistry()
        char = MagicMock()
        char.name = "Minh"
        char.secret = "biết kho vàng ẩn giấu"
        reg.register_secret(char)
        assert "secret_Minh" in reg.items
        assert reg.character_knows("Minh", "secret_Minh")
        assert not reg.character_knows("Linh", "secret_Minh")

    def test_empty_secret_skips(self):
        reg = KnowledgeRegistry()
        char = MagicMock()
        char.name = "A"
        char.secret = ""
        reg.register_secret(char)
        assert len(reg.items) == 0

    def test_reveal_to(self):
        reg = KnowledgeRegistry()
        reg.items["s1"] = KnowledgeItem(
            fact_id="s1", content="secret", known_by=["A"], is_secret=True
        )
        reg.reveal_to("s1", "B", round_num=3)
        assert reg.character_knows("B", "s1")

    def test_get_knowledge_context(self):
        reg = KnowledgeRegistry()
        reg.items["s1"] = KnowledgeItem(
            fact_id="s1", content="biết kho vàng", known_by=["Minh"], is_secret=True
        )
        ctx = reg.get_knowledge_context("Minh")
        assert "BÍ MẬT" in ctx
        assert "kho vàng" in ctx

    def test_get_knowledge_context_unknown(self):
        reg = KnowledgeRegistry()
        ctx = reg.get_knowledge_context("Nobody")
        assert "Không có" in ctx


class TestCausalGraph:
    def _event(self, round_num, desc, chars, drama=0.5):
        return MagicMock(
            round_number=round_num,
            event_type="confrontation",
            characters_involved=chars,
            description=desc,
            drama_score=drama,
            cause_event_id="",
        )

    def test_add_and_get_chain(self):
        g = CausalGraph()
        e1 = self._event(1, "A argues B", ["A", "B"])
        e2 = self._event(2, "B betrays A", ["A", "B"])
        id1 = g.add_event(e1)
        id2 = g.add_event(e2, cause_id=id1)
        chain = g.get_chain(id2)
        assert len(chain) == 2
        assert chain[0].event_id == id1
        assert chain[1].event_id == id2

    def test_get_roots(self):
        g = CausalGraph()
        e1 = self._event(1, "root", ["A"])
        e2 = self._event(2, "child", ["A"])
        id1 = g.add_event(e1)
        g.add_event(e2, cause_id=id1)
        roots = g.get_roots()
        assert len(roots) == 1
        assert roots[0].event_id == id1

    def test_format_causal_text(self):
        g = CausalGraph()
        e1 = self._event(1, "A gặp B tại quán rượu", ["A", "B"], drama=0.8)
        e2 = self._event(2, "B tiết lộ bí mật cho A", ["A", "B"], drama=0.9)
        id1 = g.add_event(e1)
        g.add_event(e2, cause_id=id1)
        text = g.format_causal_text()
        assert "→" in text
        assert "quán rượu" in text

    def test_empty_graph(self):
        g = CausalGraph()
        assert g.format_causal_text() == ""


class TestFormatEventsWithCausality:
    def test_falls_back_to_flat_list(self):
        sim = SimulationResult(
            events=[
                SimulationEvent(
                    round_number=1, event_type="test",
                    characters_involved=["A"], description="Something happened",
                    drama_score=0.5, suggested_insertion="1",
                ),
            ],
            drama_suggestions=[],
        )
        text = _format_events_with_causality(sim)
        assert "Something happened" in text

    def test_empty_events(self):
        sim = SimulationResult(events=[], drama_suggestions=[])
        text = _format_events_with_causality(sim)
        assert "Không có sự kiện" in text

    def test_causal_chains_used_when_available(self):
        events = [
            SimulationEvent(
                round_number=1, event_type="confrontation",
                characters_involved=["A", "B"], description="A confronts B",
                drama_score=0.7, suggested_insertion="1",
                cause_event_id="",
            ),
            SimulationEvent(
                round_number=2, event_type="betrayal",
                characters_involved=["A", "B"], description="B betrays A",
                drama_score=0.9, suggested_insertion="1",
                cause_event_id="evt_1_0",
            ),
        ]
        sim = SimulationResult(
            events=events,
            drama_suggestions=[],
            causal_chains=[["evt_1_0", "evt_2_1"]],
        )
        text = _format_events_with_causality(sim)
        assert "→" in text or "confronts" in text


class TestQualityScorerNewDimensions:
    def test_score_chapter_extracts_new_dimensions(self):
        from services.pipeline.quality_scorer import QualityScorer
        with patch("services.pipeline.quality_scorer.LLMClient") as MockLLM:
            mock_llm = MockLLM.return_value
            mock_llm.generate_json.return_value = {
                "coherence": 4.0,
                "character_consistency": 3.5,
                "drama": 4.5,
                "writing_quality": 3.0,
                "thematic_alignment": 4.2,
                "dialogue_depth": 3.8,
                "notes": "Good chapter",
            }
            scorer = QualityScorer()
            ch = Chapter(chapter_number=1, title="Ch1", content="test " * 100,
                         word_count=100, summary="test")
            score = scorer.score_chapter(ch)
            assert score.thematic_alignment == 4.2
            assert score.dialogue_depth == 3.8
            assert score.overall == (4.0 + 3.5 + 4.5 + 3.0) / 4

    def test_score_chapter_defaults_new_dimensions_to_zero(self):
        from services.pipeline.quality_scorer import QualityScorer
        with patch("services.pipeline.quality_scorer.LLMClient") as MockLLM:
            mock_llm = MockLLM.return_value
            mock_llm.generate_json.return_value = {
                "coherence": 3.0,
                "character_consistency": 3.0,
                "drama": 3.0,
                "writing_quality": 3.0,
                "notes": "",
            }
            scorer = QualityScorer()
            ch = Chapter(chapter_number=1, title="Ch1", content="test " * 100,
                         word_count=100, summary="test")
            score = scorer.score_chapter(ch)
            assert score.thematic_alignment == 0.0
            assert score.dialogue_depth == 0.0

    def test_chapter_score_schema_has_new_fields(self):
        score = ChapterScore(chapter_number=1)
        assert hasattr(score, "thematic_alignment")
        assert hasattr(score, "dialogue_depth")
        assert score.thematic_alignment == 0.0
        assert score.dialogue_depth == 0.0

    def test_score_chapter_prompt_includes_new_dimensions(self):
        from services.prompts.story_prompts import SCORE_CHAPTER
        assert "thematic_alignment" in SCORE_CHAPTER
        assert "dialogue_depth" in SCORE_CHAPTER
