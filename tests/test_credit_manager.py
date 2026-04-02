"""Tests for CreditManager."""

from models.schemas import UserProfile
from services.credit_manager import CreditManager, TIER_LIMITS


def make_profile(**kwargs) -> UserProfile:
    defaults = dict(user_id="test1", username="tester", credits=20, tier="free", total_stories_created=0)
    defaults.update(kwargs)
    return UserProfile(**defaults)


class TestCheckCredits:
    def test_enough_credits_returns_true(self):
        cm = CreditManager()
        profile = make_profile(credits=20)
        allowed, msg = cm.check_credits(profile, "story_generation")  # costs 5
        assert allowed is True
        assert msg == ""

    def test_insufficient_credits_returns_false(self):
        cm = CreditManager()
        profile = make_profile(credits=2)
        allowed, msg = cm.check_credits(profile, "story_generation")  # costs 5
        assert allowed is False
        assert "credits" in msg.lower() or "credit" in msg

    def test_free_action_always_allowed(self):
        cm = CreditManager()
        profile = make_profile(credits=0)
        allowed, msg = cm.check_credits(profile, "pdf_export")
        assert allowed is True
        assert msg == ""

    def test_share_is_free(self):
        cm = CreditManager()
        profile = make_profile(credits=0)
        allowed, _ = cm.check_credits(profile, "share")
        assert allowed is True

    def test_studio_tier_unlimited(self):
        cm = CreditManager()
        profile = make_profile(credits=0, tier="studio")
        allowed, msg = cm.check_credits(profile, "story_generation")
        assert allowed is True

    def test_unknown_action_costs_1(self):
        cm = CreditManager()
        profile = make_profile(credits=0)
        allowed, msg = cm.check_credits(profile, "unknown_action")
        assert allowed is False  # 0 credits < 1


class TestDeductCredits:
    def test_deduct_reduces_balance(self):
        cm = CreditManager()
        profile = make_profile(credits=20)
        success, msg = cm.deduct_credits(profile, "story_generation")  # costs 5
        assert success is True
        assert profile.credits == 15

    def test_story_generation_increments_counter(self):
        cm = CreditManager()
        profile = make_profile(credits=20, total_stories_created=3)
        cm.deduct_credits(profile, "story_generation")
        assert profile.total_stories_created == 4

    def test_non_story_action_does_not_increment_counter(self):
        cm = CreditManager()
        profile = make_profile(credits=20, total_stories_created=3)
        cm.deduct_credits(profile, "tts_export")
        assert profile.total_stories_created == 3

    def test_deduct_fails_when_insufficient(self):
        cm = CreditManager()
        profile = make_profile(credits=2)
        success, msg = cm.deduct_credits(profile, "story_generation")
        assert success is False
        assert profile.credits == 2  # unchanged

    def test_free_action_does_not_deduct(self):
        cm = CreditManager()
        profile = make_profile(credits=5)
        success, msg = cm.deduct_credits(profile, "pdf_export")
        assert success is True
        assert profile.credits == 5


class TestChapterLimit:
    def test_within_free_limit(self):
        cm = CreditManager()
        profile = make_profile(tier="free")
        allowed, msg = cm.check_chapter_limit(profile, 5)
        assert allowed is True

    def test_exceeds_free_limit(self):
        cm = CreditManager()
        profile = make_profile(tier="free")
        allowed, msg = cm.check_chapter_limit(profile, 15)  # free max=10
        assert allowed is False
        assert "10" in msg

    def test_studio_no_chapter_limit(self):
        cm = CreditManager()
        profile = make_profile(tier="studio")
        allowed, msg = cm.check_chapter_limit(profile, 1000)
        assert allowed is True

    def test_pro_limit_enforced(self):
        cm = CreditManager()
        profile = make_profile(tier="pro")
        allowed, _ = cm.check_chapter_limit(profile, 31)  # pro max=30
        assert allowed is False


class TestGetTierInfo:
    def test_free_tier_info(self):
        cm = CreditManager()
        info = cm.get_tier_info("free")
        assert info["monthly_credits"] == 20
        assert info["max_chapters"] == 10

    def test_unknown_tier_defaults_to_free(self):
        cm = CreditManager()
        info = cm.get_tier_info("nonexistent")
        assert info == TIER_LIMITS["free"]

    def test_returns_copy_not_reference(self):
        cm = CreditManager()
        info = cm.get_tier_info("free")
        info["monthly_credits"] = 999
        assert TIER_LIMITS["free"]["monthly_credits"] == 20
