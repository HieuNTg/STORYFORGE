"""Đồ thị nhân quả sự kiện — thay thế danh sách phẳng bằng chuỗi nguyên nhân-hệ quả."""

import logging
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class CausalEvent(BaseModel):
    event_id: str
    cause_event_id: str = ""  # Rỗng = sự kiện gốc
    event_round: int = 0
    event_type: str = ""
    characters_involved: list[str] = Field(default_factory=list)
    description: str = ""
    drama_score: float = 0.5
    consequences: list[str] = Field(default_factory=list)
    forces_choice_for: list[str] = Field(default_factory=list)  # Nhân vật bị buộc phải quyết định


class CausalGraph:
    """Lưu trữ và truy vấn chuỗi nhân quả của sự kiện mô phỏng."""

    def __init__(self):
        self.events: dict[str, CausalEvent] = {}
        self._last_event_by_chars: dict[str, str] = {}  # char_key → event_id

    def add_event(self, event, cause_id: str = "") -> str:
        """Thêm sự kiện vào đồ thị, trả về event_id được tạo."""
        event_id = f"evt_{event.round_number}_{len(self.events)}"

        # Nếu không có cause_id, thử tìm sự kiện liên quan trước đó
        if not cause_id:
            cause_id = self._infer_cause(event)

        causal_event = CausalEvent(
            event_id=event_id,
            cause_event_id=cause_id,
            event_round=event.round_number,
            event_type=event.event_type,
            characters_involved=list(event.characters_involved),
            description=event.description,
            drama_score=event.drama_score,
        )
        self.events[event_id] = causal_event

        # Cập nhật index nhân vật → event_id gần nhất
        for char in event.characters_involved:
            self._last_event_by_chars[char] = event_id

        # Liên kết ngược: thêm event_id vào consequences của cause
        if cause_id and cause_id in self.events:
            self.events[cause_id].consequences.append(event_id)

        # Ghi lại vào SimulationEvent gốc nếu có thể
        try:
            event.cause_event_id = cause_id
        except Exception:
            pass

        logger.debug(f"Thêm sự kiện '{event_id}' (cause: '{cause_id or 'gốc'}')")
        return event_id

    def _infer_cause(self, event) -> str:
        """Suy luận cause_id bằng cách tìm sự kiện có chung 2+ nhân vật trong cùng/vòng liền trước."""
        chars = set(event.characters_involved)
        best_id = ""
        best_overlap = 1  # Cần ít nhất 2 nhân vật chung

        for eid, cev in sorted(self.events.items(),
                               key=lambda x: x[1].event_round, reverse=True):
            if cev.event_round < event.round_number - 1:
                break  # Chỉ xét trong 1 vòng gần nhất
            overlap = len(chars & set(cev.characters_involved))
            if overlap > best_overlap:
                best_overlap = overlap
                best_id = eid

        return best_id

    def add_consequence(self, event_id: str, consequence: str) -> None:
        event = self.events.get(event_id)
        if event:
            event.consequences.append(consequence)

    def get_chain(self, event_id: str) -> list[CausalEvent]:
        """Đi ngược từ sự kiện đến nguyên nhân gốc, trả về chuỗi."""
        chain: list[CausalEvent] = []
        visited: set[str] = set()
        current_id = event_id
        while current_id and current_id not in visited:
            visited.add(current_id)
            event = self.events.get(current_id)
            if event is None:
                break
            chain.append(event)
            current_id = event.cause_event_id
        chain.reverse()
        return chain

    def get_roots(self) -> list[CausalEvent]:
        """Sự kiện không có nguyên nhân (nguyên nhân gốc)."""
        return [e for e in self.events.values() if not e.cause_event_id]

    def format_causal_text(self) -> str:
        """Định dạng cho prompt enhancer: 'A → kích hoạt B → buộc C phải chọn'."""
        if not self.events:
            return ""

        chains = self.get_top_chains(n=5)
        lines = []
        for chain in chains:
            if not chain:
                continue
            parts = []
            for cev in chain:
                chars = ", ".join(cev.characters_involved[:2])
                desc_short = cev.description[:60].rstrip()
                if cev.forces_choice_for:
                    forced = ", ".join(cev.forces_choice_for)
                    parts.append(f"[{chars}] {desc_short} (buộc {forced} chọn)")
                else:
                    parts.append(f"[{chars}] {desc_short}")
            lines.append(" → ".join(parts))

        return "\n".join(f"- {line}" for line in lines)

    def get_top_chains(self, n: int = 5) -> list[list[CausalEvent]]:
        """Trả về N chuỗi có tổng drama_score cao nhất."""
        # Mỗi sự kiện lá (không có hậu quả) là đuôi của 1 chuỗi
        leaves = [e for e in self.events.values() if not e.consequences]
        if not leaves:
            leaves = list(self.events.values())

        chains = []
        for leaf in leaves:
            chain = self.get_chain(leaf.event_id)
            chains.append(chain)

        # Sắp xếp theo tổng drama_score giảm dần
        chains.sort(key=lambda c: sum(e.drama_score for e in c), reverse=True)
        return chains[:n]
