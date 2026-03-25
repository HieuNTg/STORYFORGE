"""Onboarding wizard — guides first-time users through StoryForge setup."""

import json
import os
import logging

logger = logging.getLogger(__name__)

ONBOARDING_FILE = "data/onboarding_state.json"

# Wizard steps
STEPS = [
    {
        "id": "welcome",
        "title": "Chào mừng đến StoryForge!",
        "description": "StoryForge tự động tạo truyện kịch tính bằng AI. Hãy bắt đầu với 3 bước đơn giản.",
        "action": None,
    },
    {
        "id": "api_setup",
        "title": "Bước 1: Kết nối AI",
        "description": "Nhập API key để kết nối với LLM. Hỗ trợ OpenAI, DeepSeek, Gemini, Groq, và nhiều hơn.",
        "action": "settings",  # Navigate to settings tab
    },
    {
        "id": "first_story",
        "title": "Bước 2: Tạo truyện đầu tiên",
        "description": "Chọn thể loại, nhập ý tưởng, và để AI viết cho bạn. Bắt đầu với 3 chương ngắn để thử.",
        "action": "pipeline",  # Navigate to pipeline tab
        "recommended_settings": {
            "num_chapters": 3,
            "word_count": 1500,
            "num_characters": 3,
        },
    },
    {
        "id": "explore",
        "title": "Bước 3: Khám phá",
        "description": "Sau khi có truyện, thử xuất file, xem đánh giá chất lượng, hoặc tăng lên preset Nâng cao.",
        "action": None,
    },
]


class OnboardingManager:
    """Manage onboarding wizard state for users."""

    def __init__(self):
        self._state = self._load()

    def _load(self) -> dict:
        if os.path.exists(ONBOARDING_FILE):
            try:
                with open(ONBOARDING_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (OSError, json.JSONDecodeError):
                pass
        return {"completed": False, "current_step": 0, "skipped": False}

    def _save(self):
        os.makedirs(os.path.dirname(ONBOARDING_FILE), exist_ok=True)
        with open(ONBOARDING_FILE, "w", encoding="utf-8") as f:
            json.dump(self._state, f, ensure_ascii=False, indent=2)

    @property
    def is_completed(self) -> bool:
        return self._state.get("completed", False) or self._state.get("skipped", False)

    @property
    def current_step(self) -> int:
        return self._state.get("current_step", 0)

    def get_current_step_info(self) -> dict:
        idx = self.current_step
        if idx >= len(STEPS):
            return STEPS[-1]
        return STEPS[idx]

    def advance(self) -> dict:
        self._state["current_step"] = min(self.current_step + 1, len(STEPS) - 1)
        if self._state["current_step"] >= len(STEPS) - 1:
            self._state["completed"] = True
        self._save()
        return self.get_current_step_info()

    def skip(self):
        self._state["skipped"] = True
        self._state["completed"] = True
        self._save()

    def reset(self):
        self._state = {"completed": False, "current_step": 0, "skipped": False}
        self._save()
