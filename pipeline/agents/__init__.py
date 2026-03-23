"""Package pipeline.agents - đăng ký và quản lý tất cả agent đánh giá."""
from pipeline.agents.agent_registry import AgentRegistry
from pipeline.agents.editor_in_chief import EditorInChiefAgent
from pipeline.agents.character_specialist import CharacterSpecialistAgent
from pipeline.agents.dialogue_expert import DialogueExpertAgent
from pipeline.agents.drama_critic import DramaCriticAgent
from pipeline.agents.continuity_checker import ContinuityCheckerAgent

_agents_registered = False


def register_all_agents():
    """Đăng ký tất cả 5 agent vào registry theo đúng thứ tự.
    EditorInChiefAgent được đăng ký cuối cùng vì cần tổng hợp từ các agent khác.
    Hàm này an toàn để gọi nhiều lần (idempotent).
    """
    global _agents_registered
    if _agents_registered:
        return
    registry = AgentRegistry()
    registry.register(ContinuityCheckerAgent())
    registry.register(CharacterSpecialistAgent())
    registry.register(DialogueExpertAgent())
    registry.register(DramaCriticAgent())
    # Biên Tập Trưởng chạy sau cùng trong mỗi vòng để tổng hợp
    registry.register(EditorInChiefAgent())
    _agents_registered = True
