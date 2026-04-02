"""Test drama escalation and feedback loop."""
from models.schemas import Relationship, RelationType
from pipeline.layer2_enhance.simulator import DramaSimulator, ESCALATION_PATTERNS


def test_escalation_patterns_exist():
    assert len(ESCALATION_PATTERNS) >= 5


def test_check_escalation_high_tension():
    sim = DramaSimulator()
    sim.relationships = [
        Relationship(
            character_a="A", character_b="B",
            relation_type=RelationType.RIVAL,
            tension=0.8, intensity=0.7,
        )
    ]
    patterns = sim._check_escalation(round_num=1)
    assert len(patterns) > 0
    types = [p.pattern_type for p in patterns]
    # At tension 0.8, should trigger patterns with threshold <= 0.8
    assert any(t in types for t in ESCALATION_PATTERNS.keys())


def test_check_escalation_low_tension():
    sim = DramaSimulator()
    sim.relationships = [
        Relationship(
            character_a="A", character_b="B",
            relation_type=RelationType.ALLY,
            tension=0.1, intensity=0.3,
        )
    ]
    patterns = sim._check_escalation(round_num=1)
    assert len(patterns) == 0


def test_check_escalation_deduplicates():
    sim = DramaSimulator()
    sim.relationships = [
        Relationship(character_a="A", character_b="B", relation_type=RelationType.ENEMY, tension=0.9),
        Relationship(character_a="C", character_b="D", relation_type=RelationType.ENEMY, tension=0.9),
    ]
    patterns = sim._check_escalation(round_num=1)
    types = [p.pattern_type for p in patterns]
    # Each pattern type should appear at most once (deduplication)
    assert len(types) == len(set(types))


def test_betrayal_triggers_for_ally_high_tension():
    """Betrayal should trigger when relationship is ALLY and tension is high."""
    sim = DramaSimulator()
    sim.relationships = [
        Relationship(
            character_a="A", character_b="B",
            relation_type=RelationType.ALLY,
            tension=0.9, intensity=0.8,
        )
    ]
    patterns = sim._check_escalation(round_num=1)
    types = [p.pattern_type for p in patterns]
    assert "phản_bội" in types


def test_betrayal_does_not_trigger_for_enemy_high_tension():
    """Betrayal should NOT trigger when relationship is ENEMY, even with high tension."""
    sim = DramaSimulator()
    sim.relationships = [
        Relationship(
            character_a="A", character_b="B",
            relation_type=RelationType.ENEMY,
            tension=0.9, intensity=0.8,
        )
    ]
    patterns = sim._check_escalation(round_num=1)
    types = [p.pattern_type for p in patterns]
    assert "phản_bội" not in types


def test_revelation_triggers_for_any_relationship():
    """Revelation (tiết_lộ) should trigger regardless of relationship type."""
    for rel_type in RelationType:
        sim = DramaSimulator()
        sim.relationships = [
            Relationship(
                character_a="A", character_b="B",
                relation_type=rel_type,
                tension=0.9, intensity=0.5,
            )
        ]
        patterns = sim._check_escalation(round_num=1)
        types = [p.pattern_type for p in patterns]
        assert "tiết_lộ" in types, f"tiết_lộ should trigger for {rel_type}"


def test_enhancer_constants():
    from pipeline.layer2_enhance.enhancer import MAX_REENHANCE_ROUNDS, MIN_DRAMA_SCORE
    assert MAX_REENHANCE_ROUNDS == 2
    assert MIN_DRAMA_SCORE == 0.6


def test_enhancer_has_feedback_method():
    from pipeline.layer2_enhance.enhancer import StoryEnhancer
    enhancer = StoryEnhancer()
    assert hasattr(enhancer, 'enhance_chapter')
