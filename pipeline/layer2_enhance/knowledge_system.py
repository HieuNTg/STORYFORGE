"""Hệ thống tri thức nhân vật — theo dõi ai biết gì trong mô phỏng."""

import logging
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class RevealEntry(BaseModel):
    char: str
    round: int = 0
    source: str = ""  # "initial" | "revealed" | "witnessed" | "witness"
    event_id: str = ""  # Linked CausalEvent id if recorded


class KnowledgeItem(BaseModel):
    fact_id: str
    content: str
    known_by: list[str] = Field(default_factory=list)
    source: str = "initial"  # "initial" | "revealed" | "witnessed"
    revealed_round: int = 0  # Latest reveal round (kept for back-compat)
    reveal_log: list[RevealEntry] = Field(default_factory=list)
    is_secret: bool = False
    dramatic_irony: bool = False  # Reader knows, some characters don't


class KnowledgeRegistry:
    """Quản lý trạng thái tri thức per-character trong mô phỏng."""

    def __init__(self):
        self.items: dict[str, KnowledgeItem] = {}

    def register_secret(self, character) -> None:
        """Đăng ký Character.secret như một KnowledgeItem chỉ nhân vật đó biết."""
        secret = getattr(character, "secret", "") or ""
        if not secret.strip():
            return
        fact_id = f"secret_{character.name}"
        item = KnowledgeItem(
            fact_id=fact_id,
            content=secret,
            known_by=[character.name],
            source="initial",
            is_secret=True,
            dramatic_irony=True,  # Reader sees all
        )
        item.reveal_log.append(RevealEntry(char=character.name, round=0, source="initial"))
        self.items[fact_id] = item
        logger.debug(f"Đã đăng ký bí mật cho '{character.name}': {secret[:50]}")

    def register_initial_knowledge(self, characters: list, relationships: list) -> None:
        """Đăng ký tri thức ban đầu từ mối quan hệ — cả hai bên đều biết."""
        for rel in relationships:
            fact_id = f"rel_{rel.character_a}_{rel.character_b}"
            content = (
                f"{rel.character_a} và {rel.character_b} có quan hệ "
                f"{rel.relation_type.value} (cường độ: {rel.intensity:.1f})"
            )
            self.items[fact_id] = KnowledgeItem(
                fact_id=fact_id,
                content=content,
                known_by=[rel.character_a, rel.character_b],
                source="initial",
                is_secret=False,
            )

    def character_knows(self, char_name: str, fact_id: str) -> bool:
        item = self.items.get(fact_id)
        if item is None:
            return False
        return char_name in item.known_by

    def reveal_to(
        self,
        fact_id: str,
        char_name: str,
        round_num: int,
        source: str = "revealed",
        event_id: str = "",
    ) -> "RevealEntry | None":
        """Tiết lộ một sự thật cho nhân vật. Cập nhật known_by + reveal_log."""
        item = self.items.get(fact_id)
        if item is None:
            return None
        if char_name not in item.known_by:
            item.known_by.append(char_name)
            item.revealed_round = round_num
            logger.debug(f"Bí mật '{fact_id}' được tiết lộ cho '{char_name}' ở vòng {round_num}")
        entry = RevealEntry(char=char_name, round=round_num, source=source, event_id=event_id)
        item.reveal_log.append(entry)
        return entry

    def get_visible_posts(self, char_name: str, all_posts: list, limit: int = 5) -> list:
        """Lọc posts: loại bỏ những post trực tiếp tiết lộ bí mật mà nhân vật chưa biết.

        Chiến lược bảo thủ: chỉ lọc posts có từ khóa bí mật rõ ràng.
        """
        secret_items = [
            item for item in self.items.values()
            if item.is_secret and char_name not in item.known_by
        ]
        if not secret_items:
            # Không có bí mật cần lọc — trả về bình thường
            recent = [p for p in all_posts[-20:] if p.agent_name != char_name][-limit:]
            return recent

        # Lấy các từ khóa của bí mật
        secret_keywords: list[str] = []
        for item in secret_items:
            words = [w.strip(".,!?") for w in item.content.split() if len(w) > 4]
            secret_keywords.extend(words[:3])  # Top 3 từ quan trọng nhất

        visible = []
        for post in all_posts[-20:]:
            if post.agent_name == char_name:
                continue
            # Kiểm tra xem post có tiết lộ bí mật hay không
            content_lower = post.content.lower()
            reveals_secret = any(kw.lower() in content_lower for kw in secret_keywords)
            # Chỉ lọc nếu người đăng BIẾT bí mật đó (tức là đang tiết lộ)
            if reveals_secret:
                poster_knows = any(
                    post.agent_name in item.known_by
                    for item in secret_items
                    if any(kw.lower() in content_lower for kw in [
                        w.strip(".,!?") for w in item.content.split() if len(w) > 4
                    ][:3])
                )
                if poster_knows:
                    continue  # Lọc bỏ post này
            visible.append(post)

        return visible[-limit:]

    def get_knowledge_context(self, char_name: str) -> str:
        """Định dạng những gì nhân vật biết để đưa vào prompt."""
        known_facts = [
            item for item in self.items.values()
            if char_name in item.known_by
        ]
        if not known_facts:
            return "Không có thông tin đặc biệt."

        lines = []
        for item in known_facts:
            prefix = "[BÍ MẬT]" if item.is_secret else "[ĐÃ BIẾT]"
            lines.append(f"{prefix} {item.content}")
        return "\n".join(lines)

    def check_revelation_triggers(
        self,
        posts: list,
        round_num: int,
        all_posts: list | None = None,
    ) -> list[dict]:
        """Phát hiện khi một post tiết lộ bí mật. Trả về danh sách sự kiện tiết lộ.

        Witness propagation: chars posting in round ±1 also gain knowledge (source='witness'),
        capped at 3 per revelation. Skipped for dramatic_irony facts (reader-only secrets).
        """
        revelations = []
        secret_items = [item for item in self.items.values() if item.is_secret]
        window = all_posts if all_posts is not None else posts
        witnesses_by_round: dict[int, set[str]] = {}
        try:
            for p in window:
                r = getattr(p, "round_number", round_num)
                if abs(r - round_num) > 1:
                    continue
                name = getattr(p, "agent_name", "")
                if name:
                    witnesses_by_round.setdefault(r, set()).add(name)
        except Exception:
            witnesses_by_round = {}

        for post in posts:
            content_lower = post.content.lower()
            for item in secret_items:
                keywords = [w.strip(".,!?").lower() for w in item.content.split() if len(w) >= 4]
                if not keywords:
                    continue
                match_count = sum(1 for kw in keywords[:5] if kw in content_lower)
                if match_count < 2:
                    continue
                if post.target and post.target not in item.known_by:
                    self.reveal_to(item.fact_id, post.target, round_num, source="revealed")
                    revelations.append({
                        "fact_id": item.fact_id,
                        "revealed_to": post.target,
                        "round": round_num,
                        "by": post.agent_name,
                    })
                    logger.info(
                        f"Tiết lộ bí mật '{item.fact_id}': "
                        f"{post.agent_name} → {post.target} (vòng {round_num})"
                    )
                    if not item.dramatic_irony:
                        seen = {post.agent_name, post.target}
                        added = 0
                        for r, names in witnesses_by_round.items():
                            for w in names:
                                if added >= 3:
                                    break
                                if w and w not in seen and w not in item.known_by:
                                    self.reveal_to(item.fact_id, w, round_num, source="witness")
                                    seen.add(w)
                                    added += 1
                            if added >= 3:
                                break

        return revelations
