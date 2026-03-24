"""Package pipeline.agents - đăng ký và quản lý tất cả agent đánh giá."""
from pipeline.agents.agent_registry import AgentRegistry

_agents_registered = False


def register_all_agents():
    """Auto-discover và đăng ký tất cả agent vào registry.
    EditorInChiefAgent luôn được đăng ký cuối cùng vì cần tổng hợp từ các agent khác.
    Hàm này an toàn để gọi nhiều lần (idempotent).
    """
    global _agents_registered
    if _agents_registered:
        return
    AgentRegistry().auto_discover()
    _agents_registered = True
