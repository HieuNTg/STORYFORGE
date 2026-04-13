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
        """Suy luận cause_id bằng cách tìm sự kiện có chung nhân vật trong vòng liền trước.

        Revelation events (tiết_lộ) relaxed: 1-char overlap, 2-round lookback — lone
        discoveries often have only the revealer in common with prior reveal.
        """
        is_revelation = getattr(event, "event_type", "") == "tiết_lộ"
        chars = set(event.characters_involved)
        best_id = ""
        best_overlap = 0 if is_revelation else 1  # rev: ≥1 overlap; others: ≥2
        round_lookback = 2 if is_revelation else 1

        for eid, cev in sorted(self.events.items(),
                               key=lambda x: x[1].event_round, reverse=True):
            if cev.event_round < event.round_number - round_lookback:
                break
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


def record_revelation_event(
    graph: "CausalGraph",
    registry,
    fact_id: str,
    revealer: str,
    receiver: str,
    round_num: int,
) -> str:
    """Record a revelation as an explicit CausalEvent linked to prior reveal of same fact.

    Returns the new event_id, or "" if graph/registry invalid.
    """
    if graph is None or registry is None:
        return ""
    try:
        prior_id = ""
        fact = registry.items.get(fact_id) if hasattr(registry, "items") else None
        if fact is not None:
            log = getattr(fact, "reveal_log", []) or []
            for entry in reversed(log):
                eid = getattr(entry, "event_id", "") or ""
                if eid and eid in graph.events:
                    prior_id = eid
                    break

        synthetic = type("SimEvt", (), {})()
        synthetic.round_number = round_num
        synthetic.event_type = "tiết_lộ"
        synthetic.characters_involved = [revealer, receiver] if revealer != receiver else [revealer]
        synthetic.description = f"{revealer} tiết lộ '{fact_id}' cho {receiver}"
        synthetic.drama_score = 0.6

        new_id = graph.add_event(synthetic, cause_id=prior_id)
        return new_id
    except Exception as e:
        logger.debug(f"record_revelation_event failed for {fact_id}: {e}")
        return ""


def audit_revelation_causality(
    llm_client,
    graph: "CausalGraph",
    registry,
    enhanced_chapters: list,
    enabled: bool = True,
) -> list[dict]:
    """Scan enhanced chapters for revelation claims that contradict registry state.

    Returns list of {chapter_number, fact_id, msg, severity, sentence} flags.
    LLM call per chapter (cheap tier). Pure-Python cross-ref.
    """
    from services.prompts import CAUSAL_AUDIT_EXTRACT

    if not enabled or registry is None or not enhanced_chapters:
        return []

    items = getattr(registry, "items", {}) or {}
    if not items:
        return []

    violations: list[dict] = []
    # Cap audit to 40 chapters to bound LLM cost on long stories
    for ch in enhanced_chapters[:40]:
        ch_num = getattr(ch, "chapter_number", 0)
        content = (getattr(ch, "content", "") or "")[:6000]
        if not content:
            continue
        try:
            result = llm_client.generate_json(
                system_prompt="Trích xuất các lời khẳng định 'X biết/phát hiện/được kể Y'. Trả về JSON.",
                user_prompt=CAUSAL_AUDIT_EXTRACT.format(content=content),
                temperature=0.1,
                max_tokens=500,
                model_tier="cheap",
            )
            mentions = result.get("fact_mentions", []) if isinstance(result, dict) else []
        except Exception as e:
            logger.debug(f"audit LLM ch{ch_num} failed: {e}")
            continue

        for m in mentions[:8]:
            fact_text = (m.get("fact") or "").strip().lower()
            claimed = (m.get("claimed_source") or "").strip()
            sentence = (m.get("sentence") or "").strip()
            if not fact_text or not claimed:
                continue
            if sentence and sentence not in content:
                continue
            matched_fact = None
            for item in items.values():
                item_content = (getattr(item, "content", "") or "").lower()
                if not item_content:
                    continue
                tokens_a = set(fact_text.split())
                tokens_b = set(item_content.split())
                if not tokens_a or not tokens_b:
                    continue
                overlap = len(tokens_a & tokens_b) / max(1, min(len(tokens_a), len(tokens_b)))
                if overlap >= 0.5:
                    matched_fact = item
                    break
            if matched_fact is None:
                continue
            known_by = getattr(matched_fact, "known_by", []) or []
            log = getattr(matched_fact, "reveal_log", []) or []
            if claimed not in known_by:
                violations.append({
                    "chapter_number": ch_num,
                    "fact_id": matched_fact.fact_id,
                    "msg": f"Text claims '{claimed}' knows '{matched_fact.fact_id}' but registry has no record",
                    "severity": "critical",
                    "sentence": sentence[:200],
                })
                continue
            if log:
                first_revealer = getattr(log[0], "char", "")
                if first_revealer and claimed != first_revealer and claimed not in {getattr(e, "char", "") for e in log[:2]}:
                    violations.append({
                        "chapter_number": ch_num,
                        "fact_id": matched_fact.fact_id,
                        "msg": f"Text attributes '{matched_fact.fact_id}' to {claimed}; earliest revealer was {first_revealer}",
                        "severity": "warning",
                        "sentence": sentence[:200],
                    })

    return violations
