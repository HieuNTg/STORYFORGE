"""Test new Pydantic models added in Phase 1."""
import pytest
from pydantic import ValidationError
from models.schemas import (
    EscalationPattern, ImagePrompt, UserProfile,
    ReadingStats, ShareableStory,
)


def test_escalation_pattern_defaults():
    p = EscalationPattern(pattern_type="betrayal")
    assert p.trigger_tension == 0.6
    assert p.intensity_multiplier == 1.5
    assert p.characters_required == 2


def test_escalation_pattern_validation():
    with pytest.raises(ValidationError):
        EscalationPattern(pattern_type="test", trigger_tension=2.0)  # >1


def test_image_prompt_defaults():
    ip = ImagePrompt(chapter_number=1, dalle_prompt="test", sd_prompt="test")
    assert ip.style == "cinematic"
    assert ip.negative_prompt == ""
    assert ip.characters_in_scene == []


def test_user_profile_required():
    with pytest.raises(ValidationError):
        UserProfile()  # missing user_id and username


def test_user_profile_creation():
    u = UserProfile(user_id="abc", username="alice")
    assert u.usage_count == 0
    assert u.story_ids == []


def test_reading_stats_defaults():
    rs = ReadingStats()
    assert rs.total_words == 0
    assert rs.estimated_reading_minutes == 0


def test_shareable_story():
    ss = ShareableStory(share_id="abc123", story_title="My Story")
    assert ss.share_id == "abc123"
    assert ss.expires_at == ""
