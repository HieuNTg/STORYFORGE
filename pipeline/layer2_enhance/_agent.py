"""Agent nhân vật và hằng số tension cho mô phỏng kịch tính."""

from models.schemas import Character, AgentPost

# Ánh xạ loại quan hệ → thay đổi tension
TENSION_DELTAS = {
    "đồng_minh": -0.1,
    "liên_minh": -0.1,
    "đối_thủ": 0.2,
    "kẻ_thù": 0.3,
    "phản_bội": 0.3,
    "tình_nhân": -0.15,
    "sư_phụ": -0.05,
    "gia_đình": -0.1,
    "chưa_rõ": 0.0,
}


class CharacterAgent:
    """Agent đại diện cho một nhân vật trong mô phỏng."""

    def __init__(self, character: Character):
        self.character = character
        self.memory: list[str] = []
        self.posts: list[AgentPost] = []

    def add_memory(self, event: str):
        self.memory.append(event)
        # Giới hạn bộ nhớ - tăng lên 50 để giữ ngữ cảnh tốt hơn
        if len(self.memory) > 50:
            self.memory = self.memory[-50:]
