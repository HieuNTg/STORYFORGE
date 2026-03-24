"""Credit management for StoryForge usage tracking."""

import logging
from typing import Optional
from models.schemas import UserProfile

logger = logging.getLogger(__name__)

# Credit costs per action
CREDIT_COSTS = {
    "story_generation": 5,    # Full pipeline run
    "layer2_enhance": 2,      # Re-enhance only
    "tts_export": 1,          # TTS audio export
    "image_generation": 1,    # Per image
    "pdf_export": 0,          # Free
    "share": 0,               # Free
}

# Tier limits
TIER_LIMITS = {
    "free": {"monthly_credits": 20, "max_chapters": 10, "max_words": 5000},
    "pro": {"monthly_credits": 100, "max_chapters": 30, "max_words": 50000},
    "studio": {"monthly_credits": -1, "max_chapters": -1, "max_words": -1},  # -1 = unlimited
}


class CreditManager:
    """Manage user credits and usage limits."""

    def __init__(self, user_manager=None):
        self.user_manager = user_manager

    def check_credits(self, profile: UserProfile, action: str) -> tuple[bool, str]:
        """Check if user has enough credits. Returns (allowed, message)."""
        cost = CREDIT_COSTS.get(action, 1)
        if cost == 0:
            return True, ""

        tier = TIER_LIMITS.get(profile.tier, TIER_LIMITS["free"])
        if tier["monthly_credits"] == -1:
            return True, ""  # Unlimited

        if profile.credits < cost:
            return False, f"Không đủ credits. Cần {cost}, còn {profile.credits}."

        return True, ""

    def deduct_credits(self, profile: UserProfile, action: str) -> tuple[bool, str]:
        """Deduct credits for an action. Returns (success, message)."""
        allowed, msg = self.check_credits(profile, action)
        if not allowed:
            return False, msg

        cost = CREDIT_COSTS.get(action, 1)
        if cost > 0:
            profile.credits -= cost
            profile.total_stories_created += (1 if action == "story_generation" else 0)
            logger.info(f"Deducted {cost} credits from {profile.username}. Remaining: {profile.credits}")

        return True, f"Trừ {cost} credits. Còn lại: {profile.credits}"

    def get_tier_info(self, tier: str) -> dict:
        """Get tier limits info."""
        return TIER_LIMITS.get(tier, TIER_LIMITS["free"]).copy()

    def check_chapter_limit(self, profile: UserProfile, requested_chapters: int) -> tuple[bool, str]:
        """Check if chapter count is within tier limit."""
        tier = TIER_LIMITS.get(profile.tier, TIER_LIMITS["free"])
        max_ch = tier["max_chapters"]
        if max_ch == -1:
            return True, ""
        if requested_chapters > max_ch:
            return False, f"Tier {profile.tier}: tối đa {max_ch} chương. Nâng cấp để mở khóa."
        return True, ""
