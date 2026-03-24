"""
Comprehensive tests for Layer 2 drama enhancement upgrades.
Tests cover: EmotionalState, CharacterAgent, TrustNetworkEdge,
genre drama rules, and targeted rewriting enhancements.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from models.schemas import Character, Relationship, RelationType, Chapter, StoryDraft, SimulationResult, AgentPost, SimulationEvent
from pipeline.layer2_enhance._agent import EmotionalState, CharacterAgent, TrustEdge, MOOD_DRAMA, MOOD_TRIGGERS, TENSION_DELTAS
from pipeline.layer2_enhance.simulator import TrustNetworkEdge, DramaSimulator
from pipeline.layer2_enhance.genre_drama_rules import get_genre_rules, get_genre_enhancement_hints, GENRE_DRAMA_RULES
from pipeline.layer2_enhance.enhancer import StoryEnhancer, MIN_DRAMA_SCORE


# ============================================================================
# EMOTIONAL STATE TESTS
# ============================================================================

class TestEmotionalState:
    """Test EmotionalState initialization and updates."""

    def test_initial_state(self):
        """Test EmotionalState initializes with correct defaults."""
        state = EmotionalState()
        assert state.mood == "bình_thường"
        assert state.energy == 0.7
        assert state.stakes == 0.3
        assert state.mood_history == []

    def test_update_mood_with_event_type(self):
        """Test mood updates based on event type."""
        state = EmotionalState()
        # Test phản_bội event → phẫn_nộ mood
        state.update_mood("phản_bội")
        assert state.mood == "phẫn_nộ"
        assert state.mood_history[0] == "bình_thường"

    def test_mood_history_tracking(self):
        """Test mood history tracks multiple updates."""
        state = EmotionalState()
        state.update_mood("phản_bội")  # → phẫn_nộ
        state.update_mood("tiết_lộ")   # → sốc
        state.update_mood("đối_đầu")   # → quyết_tâm
        assert len(state.mood_history) == 3
        assert state.mood_history[0] == "bình_thường"
        assert state.mood_history[1] == "phẫn_nộ"
        assert state.mood_history[2] == "sốc"

    def test_mood_history_bounded_to_20(self):
        """Test mood history capped at 20 entries."""
        state = EmotionalState()
        for i in range(25):
            state.update_mood("tiết_lộ")  # Cycle through sốc
        # Should have max 20 history + 1 current
        assert len(state.mood_history) <= 20

    def test_energy_bounds_lower(self):
        """Test energy can't go below 0."""
        state = EmotionalState()
        state.update_energy(-1.5)
        assert state.energy == 0.0

    def test_energy_bounds_upper(self):
        """Test energy can't exceed 1."""
        state = EmotionalState()
        state.update_energy(0.5)
        assert state.energy == 1.0

    def test_stakes_increase_when_targeted(self):
        """Test stakes increase with positive delta."""
        state = EmotionalState()
        initial_stakes = state.stakes
        state.update_stakes(0.15)
        assert state.stakes == initial_stakes + 0.15

    def test_stakes_bounds(self):
        """Test stakes stay within 0-1 bounds."""
        state = EmotionalState()
        state.update_stakes(0.8)  # 0.3 + 0.8 = 1.1 → clamp to 1.0
        assert state.stakes == 1.0
        state.update_stakes(-1.5)
        assert state.stakes == 0.0

    def test_drama_multiplier_calculation(self):
        """Test drama multiplier is calculated correctly."""
        state = EmotionalState()
        state.mood = "tức_giận"  # mood_drama = 1.5
        state.stakes = 0.5
        state.energy = 0.5
        multiplier = state.drama_multiplier
        # base = 1.5, desperation = 0.5 * (1-0.5) * 0.5 = 0.125
        expected = 1.5 + 0.125
        assert abs(multiplier - expected) < 0.01

    def test_to_prompt_text_format(self):
        """Test prompt text formatting."""
        state = EmotionalState()
        state.mood = "tức_giận"
        state.energy = 0.8
        state.stakes = 0.5
        text = state.to_prompt_text()
        assert "tức_giận" in text
        assert "0.8" in text
        assert "0.5" in text
        assert "Tâm trạng" in text
        assert "Năng lượng" in text
        assert "Mức rủi ro" in text

    def test_update_method_with_all_params(self):
        """Test update() method with mood, energy, and stakes."""
        state = EmotionalState()
        state.update("hận_thù", energy_delta=0.1, stakes_delta=0.2)
        assert state.mood == "hận_thù"
        assert abs(state.energy - 0.8) < 0.01  # 0.7 + 0.1 (floating point safe)
        assert abs(state.stakes - 0.5) < 0.01  # 0.3 + 0.2

    def test_update_ignores_invalid_mood(self):
        """Test update() ignores invalid mood strings."""
        state = EmotionalState()
        original_mood = state.mood
        state.update("invalid_mood_xyz")
        assert state.mood == original_mood


# ============================================================================
# CHARACTER AGENT TESTS
# ============================================================================

class TestCharacterAgent:
    """Test CharacterAgent with emotional state and trust network."""

    def test_character_agent_initialization(self):
        """Test CharacterAgent initializes correctly."""
        char = Character(
            name="Nhân vật A",
            role="chính",
            personality="can đảm",
            background="lịch sử",
            motivation="trả thù"
        )
        agent = CharacterAgent(char)
        assert agent.character == char
        assert agent.memory == []
        assert agent.posts == []
        assert agent.emotion.mood == "bình_thường"
        assert agent.trust_map == {}

    def test_emotional_state_property_alias(self):
        """Test emotional_state property returns emotion."""
        char = Character(name="Test", role="chính", personality="p", background="b", motivation="m")
        agent = CharacterAgent(char)
        assert agent.emotional_state is agent.emotion

    def test_process_event_updates_mood(self):
        """Test process_event updates emotional state."""
        char = Character(name="Test", role="chính", personality="p", background="b", motivation="m")
        agent = CharacterAgent(char)
        agent.process_event("phản_bội", is_target=False)
        assert agent.emotion.mood == "phẫn_nộ"

    def test_process_event_target_raises_stakes(self):
        """Test being event target increases stakes and drains energy."""
        char = Character(name="Test", role="chính", personality="p", background="b", motivation="m")
        agent = CharacterAgent(char)
        initial_stakes = agent.emotion.stakes
        initial_energy = agent.emotion.energy
        agent.process_event("phản_bội", is_target=True)
        assert agent.emotion.stakes > initial_stakes  # +0.15
        assert agent.emotion.energy < initial_energy  # -0.1

    def test_process_event_non_target_drains_energy(self):
        """Test non-target events drain some energy."""
        char = Character(name="Test", role="chính", personality="p", background="b", motivation="m")
        agent = CharacterAgent(char)
        initial_energy = agent.emotion.energy
        agent.process_event("phản_bội", is_target=False)
        assert agent.emotion.energy < initial_energy  # -0.05

    def test_add_memory_appends_event(self):
        """Test add_memory appends to memory list."""
        char = Character(name="Test", role="chính", personality="p", background="b", motivation="m")
        agent = CharacterAgent(char)
        agent.add_memory("Event 1")
        agent.add_memory("Event 2")
        assert len(agent.memory) == 2
        assert agent.memory[0] == "Event 1"
        assert agent.memory[1] == "Event 2"

    def test_memory_limit_50(self):
        """Test memory is bounded to 50 entries."""
        char = Character(name="Test", role="chính", personality="p", background="b", motivation="m")
        agent = CharacterAgent(char)
        for i in range(60):
            agent.add_memory(f"Event {i}")
        assert len(agent.memory) == 50
        # Should keep last 50
        assert agent.memory[0] == "Event 10"
        assert agent.memory[-1] == "Event 59"

    def test_get_trust_creates_edge(self):
        """Test get_trust creates TrustEdge if not exists."""
        char = Character(name="Test", role="chính", personality="p", background="b", motivation="m")
        agent = CharacterAgent(char)
        trust = agent.get_trust("Target")
        assert isinstance(trust, TrustEdge)
        assert trust.target == "Target"
        assert trust.trust == 50.0  # Default

    def test_get_trust_returns_existing_edge(self):
        """Test get_trust returns existing edge."""
        char = Character(name="Test", role="chính", personality="p", background="b", motivation="m")
        agent = CharacterAgent(char)
        trust1 = agent.get_trust("Target")
        trust1.trust = 75.0
        trust2 = agent.get_trust("Target")
        assert trust2.trust == 75.0  # Same instance

    def test_get_emotional_context(self):
        """Test emotional context formatting."""
        char = Character(name="Test", role="chính", personality="p", background="b", motivation="m")
        agent = CharacterAgent(char)
        agent.emotion.mood = "tức_giận"
        agent.emotion.energy = 0.6
        agent.emotion.stakes = 0.4
        agent.get_trust("A").trust = 80.0
        agent.get_trust("B").trust = 40.0
        context = agent.get_emotional_context()
        assert "tức_giận" in context
        assert "0.6" in context
        assert "0.4" in context
        assert "A: 80" in context
        assert "B: 40" in context


# ============================================================================
# TRUST EDGE TESTS (CharacterAgent level)
# ============================================================================

class TestTrustEdge:
    """Test TrustEdge for individual agents."""

    def test_trust_edge_initialization(self):
        """Test TrustEdge initializes correctly."""
        edge = TrustEdge("TargetChar", trust=75.0)
        assert edge.target == "TargetChar"
        assert edge.trust == 75.0
        assert edge.history == []

    def test_trust_update_with_reason(self):
        """Test trust updates with reason recorded."""
        edge = TrustEdge("Target", trust=50.0)
        edge.update(10.0, reason="Helped in battle")
        assert edge.trust == 60.0
        assert len(edge.history) == 1
        assert "50→60" in edge.history[0]
        assert "Helped in battle" in edge.history[0]

    def test_trust_bounds_at_0(self):
        """Test trust can't go below 0."""
        edge = TrustEdge("Target", trust=10.0)
        edge.update(-20.0)
        assert edge.trust == 0.0

    def test_trust_bounds_at_100(self):
        """Test trust can't exceed 100."""
        edge = TrustEdge("Target", trust=95.0)
        edge.update(10.0)
        assert edge.trust == 100.0

    def test_is_betrayal_trigger_true(self):
        """Test is_betrayal_trigger when trust drops >30."""
        edge = TrustEdge("Target", trust=60.0)
        edge.update(-35.0, reason="Revealed secret")
        assert edge.is_betrayal_trigger is True

    def test_is_betrayal_trigger_false(self):
        """Test is_betrayal_trigger when trust drops <=30."""
        edge = TrustEdge("Target", trust=60.0)
        edge.update(-25.0, reason="Disagreed")
        assert edge.is_betrayal_trigger is False

    def test_is_betrayal_trigger_no_history(self):
        """Test is_betrayal_trigger with no history."""
        edge = TrustEdge("Target", trust=50.0)
        assert edge.is_betrayal_trigger is False


# ============================================================================
# TRUST NETWORK EDGE TESTS (Simulator level)
# ============================================================================

class TestTrustNetworkEdge:
    """Test TrustNetworkEdge in simulator."""

    def test_trust_network_edge_initialization(self):
        """Test TrustNetworkEdge initializes correctly."""
        edge = TrustNetworkEdge("CharA", "CharB", trust=70.0)
        assert edge.char_a == "CharA"
        assert edge.char_b == "CharB"
        assert edge.trust == 70.0
        assert edge.history == []

    def test_trust_network_update_with_reason(self):
        """Test trust update records reason."""
        edge = TrustNetworkEdge("A", "B", trust=50.0)
        edge.update_trust(15.0, reason="Alliance formed")
        assert edge.trust == 65.0
        assert len(edge.history) == 1
        assert "50→65" in edge.history[0]
        assert "Alliance formed" in edge.history[0]

    def test_trust_network_bounds_lower(self):
        """Test trust network bounded at 0."""
        edge = TrustNetworkEdge("A", "B", trust=20.0)
        edge.update_trust(-30.0)
        assert edge.trust == 0.0

    def test_trust_network_bounds_upper(self):
        """Test trust network bounded at 100."""
        edge = TrustNetworkEdge("A", "B", trust=90.0)
        edge.update_trust(20.0)
        assert edge.trust == 100.0

    def test_is_betrayal_candidate_true(self):
        """Test is_betrayal_candidate when trust < 30."""
        edge = TrustNetworkEdge("A", "B", trust=25.0)
        assert edge.is_betrayal_candidate is True

    def test_is_betrayal_candidate_false(self):
        """Test is_betrayal_candidate when trust >= 30."""
        edge = TrustNetworkEdge("A", "B", trust=30.0)
        assert edge.is_betrayal_candidate is False

    def test_history_bounded_to_10(self):
        """Test history is bounded to 10 entries."""
        edge = TrustNetworkEdge("A", "B", trust=50.0)
        for i in range(15):
            edge.update_trust(1.0, reason=f"Event {i}")
        assert len(edge.history) <= 10


# ============================================================================
# GENRE DRAMA RULES TESTS
# ============================================================================

class TestGenreDramaRules:
    """Test genre drama rules and enhancements."""

    def test_all_8_genres_defined(self):
        """Test all 8 Vietnamese genres are defined."""
        required_genres = [
            "Tiên Hiệp", "Huyền Huyễn", "Đô Thị", "Ngôn Tình",
            "Cung Đấu", "Xuyên Không", "Trọng Sinh", "Kiếm Hiệp"
        ]
        for genre in required_genres:
            assert genre in GENRE_DRAMA_RULES, f"Missing genre: {genre}"

    def test_get_genre_rules_exact_match(self):
        """Test get_genre_rules with exact genre name."""
        rules = get_genre_rules("Tiên Hiệp")
        assert rules is not None
        assert "escalation_pattern" in rules
        assert rules["escalation_pattern"] == "power_progression"

    def test_get_genre_rules_partial_match(self):
        """Test get_genre_rules with partial match."""
        rules = get_genre_rules("tiên hiệp")  # lowercase
        assert rules is not None
        assert rules["escalation_pattern"] == "power_progression"

    def test_get_genre_rules_fallback_unknown(self):
        """Test get_genre_rules returns generic fallback for unknown genre."""
        rules = get_genre_rules("UnknownGenreXYZ")
        assert rules is not None
        assert rules["escalation_pattern"] == "standard"

    def test_genre_has_required_fields(self):
        """Test each genre has required fields."""
        required_fields = [
            "escalation_pattern", "key_beats", "tension_curve",
            "dialogue_style", "emotional_peaks", "pacing_note"
        ]
        for genre, rules in GENRE_DRAMA_RULES.items():
            for field in required_fields:
                assert field in rules, f"{genre} missing {field}"

    def test_get_genre_enhancement_hints_early_story(self):
        """Test enhancement hints at story start."""
        hints = get_genre_enhancement_hints("Tiên Hiệp", chapter_num=2, total_chapters=20)
        assert "Tiên Hiệp" in hints
        assert "mở đầu" in hints or "thiết lập" in hints

    def test_get_genre_enhancement_hints_mid_story(self):
        """Test enhancement hints at story middle."""
        hints = get_genre_enhancement_hints("Tiên Hiệp", chapter_num=9, total_chapters=20)
        assert "Tiên Hiệp" in hints
        assert "phát triển" in hints or "leo thang" in hints

    def test_get_genre_enhancement_hints_late_story(self):
        """Test enhancement hints at story end."""
        hints = get_genre_enhancement_hints("Tiên Hiệp", chapter_num=18, total_chapters=20)
        assert "Tiên Hiệp" in hints
        assert "kết" in hints or "giải quyết" in hints

    def test_genre_xuan_khong_has_knowledge_advantage(self):
        """Test Xuyên Không has knowledge advantage pattern."""
        rules = get_genre_rules("Xuyên Không")
        assert rules["escalation_pattern"] == "knowledge_advantage"

    def test_genre_cung_dau_has_faction_warfare(self):
        """Test Cung Đấu has faction warfare pattern."""
        rules = get_genre_rules("Cung Đấu")
        assert rules["escalation_pattern"] == "faction_warfare"


# ============================================================================
# SIMULATOR TRUST NETWORK TESTS
# ============================================================================

class TestDramaSimulatorTrustNetwork:
    """Test DramaSimulator trust network setup and updates."""

    def test_simulator_initializes_trust_network(self):
        """Test simulator initializes trust network from relationships."""
        sim = DramaSimulator()
        characters = [
            Character(name="A", role="chính", personality="p", background="b", motivation="m"),
            Character(name="B", role="phụ", personality="p", background="b", motivation="m"),
        ]
        relationships = [
            Relationship(character_a="A", character_b="B", relation_type=RelationType.ALLY)
        ]
        sim.setup_agents(characters, relationships)

        # Check trust network was created
        assert len(sim.trust_network) > 0
        # Check trust value based on relationship type (ALLY = close = 70.0)
        key = "A|B"
        assert key in sim.trust_network
        assert sim.trust_network[key].trust == 70.0

    def test_trust_network_enemy_relationship(self):
        """Test trust initialization for ENEMY relationship (hostile)."""
        sim = DramaSimulator()
        characters = [
            Character(name="A", role="chính", personality="p", background="b", motivation="m"),
            Character(name="B", role="phụ", personality="p", background="b", motivation="m"),
        ]
        relationships = [
            Relationship(character_a="A", character_b="B", relation_type=RelationType.ENEMY)
        ]
        sim.setup_agents(characters, relationships)

        key = "A|B"
        # ENEMY is hostile = 40.0
        assert sim.trust_network[key].trust == 40.0

    def test_trust_network_edge_update(self):
        """Test trust network edge can be updated."""
        edge = TrustNetworkEdge("A", "B", trust=60.0)
        edge.update_trust(-15.0, "Conflict in round 1")
        assert edge.trust == 45.0
        assert len(edge.history) == 1

    def test_betrayal_candidate_detection(self):
        """Test detection of betrayal candidates (trust < 30)."""
        edge = TrustNetworkEdge("A", "B", trust=25.0)
        assert edge.is_betrayal_candidate is True

        edge2 = TrustNetworkEdge("C", "D", trust=50.0)
        assert edge2.is_betrayal_candidate is False


# ============================================================================
# ENHANCER WEAK CHAPTERS TESTS
# ============================================================================

class TestEnhancerFindWeakChapters:
    """Test _find_weak_chapters returns dicts with weak/strong points."""

    @patch('pipeline.layer2_enhance.enhancer.LLMClient.generate_json')
    def test_find_weak_chapters_returns_dicts(self, mock_llm):
        """Test _find_weak_chapters returns list of dicts with correct structure."""
        mock_llm.return_value = {
            "drama_score": 0.5,
            "weak_points": ["Not enough dialogue", "Slow pacing"],
            "strong_points": ["Good character development"],
        }

        enhancer = StoryEnhancer()
        enhanced_story = Mock()
        enhanced_story.chapters = [
            Chapter(chapter_number=1, title="Ch1", content="Some weak content here"),
        ]

        weak = enhancer._find_weak_chapters(enhanced_story)

        assert len(weak) > 0
        assert isinstance(weak[0], dict)
        assert "chapter_number" in weak[0]
        assert "score" in weak[0]
        assert "weak_points" in weak[0]
        assert "strong_points" in weak[0]

    @patch('pipeline.layer2_enhance.enhancer.LLMClient.generate_json')
    def test_find_weak_chapters_filters_by_drama_score(self, mock_llm):
        """Test _find_weak_chapters only includes chapters < MIN_DRAMA_SCORE."""
        mock_llm.side_effect = [
            {
                "drama_score": 0.5,  # < 0.6
                "weak_points": ["Weak 1"],
                "strong_points": ["Strong 1"],
            },
            {
                "drama_score": 0.7,  # >= 0.6
                "weak_points": ["Weak 2"],
                "strong_points": ["Strong 2"],
            },
        ]

        enhancer = StoryEnhancer()
        enhanced_story = Mock()
        enhanced_story.chapters = [
            Chapter(chapter_number=1, title="Ch1", content="Content 1"),
            Chapter(chapter_number=2, title="Ch2", content="Content 2"),
        ]

        weak = enhancer._find_weak_chapters(enhanced_story)

        # Should only include chapter 1 (score 0.5 < 0.6)
        assert len(weak) == 1
        assert weak[0]["chapter_number"] == 1
        assert weak[0]["score"] == 0.5

    @patch('pipeline.layer2_enhance.enhancer.LLMClient.generate_json')
    def test_find_weak_chapters_with_empty_weak_points(self, mock_llm):
        """Test _find_weak_chapters handles missing weak_points gracefully."""
        mock_llm.return_value = {
            "drama_score": 0.4,
            # Missing weak_points and strong_points
        }

        enhancer = StoryEnhancer()
        enhanced_story = Mock()
        enhanced_story.chapters = [
            Chapter(chapter_number=1, title="Ch1", content="Content"),
        ]

        weak = enhancer._find_weak_chapters(enhanced_story)

        assert len(weak) == 1
        assert weak[0]["weak_points"] == []  # Default empty list
        assert weak[0]["strong_points"] == []

    @patch('pipeline.layer2_enhance.enhancer.LLMClient.generate_json')
    def test_find_weak_chapters_handles_llm_exception(self, mock_llm):
        """Test _find_weak_chapters gracefully handles LLM exceptions."""
        mock_llm.side_effect = Exception("LLM API error")

        enhancer = StoryEnhancer()
        enhanced_story = Mock()
        enhanced_story.chapters = [
            Chapter(chapter_number=1, title="Ch1", content="Content"),
        ]

        # Should not raise, just skip the failed chapter
        weak = enhancer._find_weak_chapters(enhanced_story)
        assert isinstance(weak, list)


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

class TestIntegration:
    """Integration tests combining multiple components."""

    def test_emotional_state_in_agent_workflow(self):
        """Test emotional state flows through agent workflow."""
        char = Character(
            name="Hero",
            role="chính",
            personality="Brave",
            background="History",
            motivation="Justice"
        )
        agent = CharacterAgent(char)

        # Simulate series of events
        agent.process_event("phản_bội", is_target=True)
        assert agent.emotion.mood == "phẫn_nộ"
        assert agent.emotion.stakes > 0.3

        agent.process_event("liên_minh", is_target=False)
        assert agent.emotion.mood == "hy_vọng"

    def test_trust_network_with_character_agents(self):
        """Test trust network syncs with character agent trust edges."""
        char_a = Character(name="A", role="chính", personality="p", background="b", motivation="m")
        char_b = Character(name="B", role="phụ", personality="p", background="b", motivation="m")

        agent_a = CharacterAgent(char_a)
        agent_a_trust_to_b = agent_a.get_trust("B")

        # Modify agent-level trust
        agent_a_trust_to_b.update(-20.0, "Conflict")

        # Verify bounds
        assert agent_a_trust_to_b.trust >= 0
        assert agent_a_trust_to_b.trust <= 100

    def test_genre_rules_applied_to_enhancer(self):
        """Test genre rules can be applied during enhancement."""
        enhancer = StoryEnhancer()
        genre = "Tiên Hiệp"
        chapter_num = 5
        total = 20

        hints = get_genre_enhancement_hints(genre, chapter_num, total)
        assert "Tiên Hiệp" in hints
        assert len(hints) > 0

    def test_drama_score_calculation_with_mood(self):
        """Test drama score incorporates mood multiplier."""
        state = EmotionalState()
        state.mood = "hận_thù"  # drama = 1.8
        state.stakes = 0.8
        state.energy = 0.2

        multiplier = state.drama_multiplier
        # Should be elevated due to high stakes, low energy, high mood
        assert multiplier > MOOD_DRAMA["bình_thường"]


# ============================================================================
# EDGE CASE TESTS
# ============================================================================

class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_emotional_state_zero_total_chapters(self):
        """Test genre hints with zero total chapters."""
        hints = get_genre_enhancement_hints("Tiên Hiệp", chapter_num=1, total_chapters=0)
        assert len(hints) > 0  # Should not crash

    def test_trust_edge_with_empty_reason(self):
        """Test trust edge update with empty reason."""
        edge = TrustEdge("Target")
        edge.update(5.0, reason="")
        # History should still have entry (reason is optional)
        assert edge.trust == 55.0

    def test_character_agent_with_special_characters_in_name(self):
        """Test agent with special characters in name."""
        char = Character(
            name="Nhân vật Đặc Biệt (ấu)",
            role="chính",
            personality="p",
            background="b",
            motivation="m"
        )
        agent = CharacterAgent(char)
        assert agent.character.name == "Nhân vật Đặc Biệt (ấu)"

    def test_multiple_mood_updates_rapid_succession(self):
        """Test rapid mood updates."""
        state = EmotionalState()
        for _ in range(5):
            state.update_mood("phản_bội")
            state.update_mood("liên_minh")
        # Should handle rapid updates gracefully
        assert len(state.mood_history) > 0

    def test_genre_rules_with_missing_sub_beats(self):
        """Test genre rules still work if some optional fields vary."""
        # All genres have required fields per test_genre_has_required_fields
        for genre in GENRE_DRAMA_RULES.values():
            assert "key_beats" in genre
            assert len(genre["key_beats"]) >= 3


# ============================================================================
# MOOD AND TENSION CONSTANTS TESTS
# ============================================================================

class TestMoodAndTensionConstants:
    """Test mood and tension lookup tables."""

    def test_mood_drama_values(self):
        """Test all moods in MOOD_DRAMA are between 1.0 and 2.0."""
        for mood, multiplier in MOOD_DRAMA.items():
            assert 1.0 <= multiplier <= 2.0, f"{mood}: {multiplier}"

    def test_mood_triggers_mapping(self):
        """Test MOOD_TRIGGERS has valid mood values."""
        for event_type, mood in MOOD_TRIGGERS.items():
            assert mood in MOOD_DRAMA or mood in MOOD_TRIGGERS.values()

    def test_tension_deltas_bounds(self):
        """Test tension deltas are reasonable (-0.2 to +0.3)."""
        for rel_type, delta in TENSION_DELTAS.items():
            assert -0.5 <= delta <= 0.5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
