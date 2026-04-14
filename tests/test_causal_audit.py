"""Phase B — Causal Accountability tests."""

from unittest.mock import MagicMock


from pipeline.layer2_enhance.causal_chain import (
    CausalEvent, CausalGraph, record_revelation_event, audit_revelation_causality,
)
from pipeline.layer2_enhance.knowledge_system import (
    KnowledgeRegistry, KnowledgeItem, RevealEntry,
)


def _make_event(round_num, chars, etype="xung_đột", desc="e", drama=0.5):
    return MagicMock(
        round_number=round_num,
        event_type=etype,
        characters_involved=chars,
        description=desc,
        drama_score=drama,
        cause_event_id="",
    )


def _make_post(name, content="", target="", round_num=1):
    return MagicMock(
        agent_name=name,
        content=content,
        target=target,
        round_number=round_num,
        action_type="post",
        sentiment="",
    )


def test_causal_event_defaults():
    ev = CausalEvent(event_id="x")
    assert ev.cause_event_id == ""
    assert ev.event_round == 0
    assert ev.consequences == []


def test_reveal_entry_schema():
    e = RevealEntry(char="A", round=3, source="revealed", event_id="evt_1")
    assert e.char == "A" and e.round == 3
    assert e.source == "revealed" and e.event_id == "evt_1"


def test_knowledge_item_reveal_log_default():
    it = KnowledgeItem(fact_id="x", content="c")
    assert it.reveal_log == []
    assert it.revealed_round == 0


def test_reveal_to_appends_log_and_sets_round():
    reg = KnowledgeRegistry()
    reg.items["s1"] = KnowledgeItem(fact_id="s1", content="c", known_by=["A"], is_secret=True)
    entry = reg.reveal_to("s1", "B", round_num=3, source="revealed")
    assert entry is not None and entry.char == "B" and entry.round == 3
    item = reg.items["s1"]
    assert "B" in item.known_by
    assert item.revealed_round == 3
    assert len(item.reveal_log) == 1
    assert item.reveal_log[0].source == "revealed"


def test_reveal_to_preserves_order_across_multiple_reveals():
    reg = KnowledgeRegistry()
    reg.items["s1"] = KnowledgeItem(fact_id="s1", content="c", known_by=["A"])
    reg.reveal_to("s1", "B", round_num=1)
    reg.reveal_to("s1", "C", round_num=2)
    reg.reveal_to("s1", "D", round_num=3)
    log = reg.items["s1"].reveal_log
    assert [e.char for e in log] == ["B", "C", "D"]
    assert [e.round for e in log] == [1, 2, 3]


def test_reveal_to_noop_on_unknown_fact():
    reg = KnowledgeRegistry()
    assert reg.reveal_to("missing", "X", 1) is None


def test_infer_cause_relaxed_for_revelation():
    g = CausalGraph()
    e1 = _make_event(1, ["A", "B"], etype="xung_đột")
    id1 = g.add_event(e1)
    # Revelation in round 3 sharing only "A" with e1 — should still link (1-char overlap, 2-round lookback)
    e2 = _make_event(3, ["A", "C"], etype="tiết_lộ")
    id2 = g.add_event(e2)
    assert g.events[id2].cause_event_id == id1


def test_infer_cause_strict_for_non_revelation():
    g = CausalGraph()
    e1 = _make_event(1, ["A", "B"])
    g.add_event(e1)
    # Non-revelation with 1-char overlap → no link
    e2 = _make_event(2, ["A", "C"])
    id2 = g.add_event(e2)
    assert g.events[id2].cause_event_id == ""


def test_record_revelation_event_links_to_prior():
    g = CausalGraph()
    reg = KnowledgeRegistry()
    reg.items["secret_M"] = KnowledgeItem(fact_id="secret_M", content="c", known_by=["M"], is_secret=True)
    # first reveal → records event, prior_id empty
    id1 = record_revelation_event(g, reg, "secret_M", "M", "A", round_num=1)
    assert id1 and id1 in g.events
    reg.items["secret_M"].reveal_log.append(RevealEntry(char="A", round=1, event_id=id1))
    # second reveal → should link cause to id1
    id2 = record_revelation_event(g, reg, "secret_M", "A", "B", round_num=2)
    assert id2 and g.events[id2].cause_event_id == id1
    assert g.events[id2].event_type == "tiết_lộ"


def test_record_revelation_event_unknown_fact():
    g = CausalGraph()
    reg = KnowledgeRegistry()
    eid = record_revelation_event(g, reg, "no_such", "A", "B", 1)
    # No prior reveal → event still created, but cause_event_id empty
    assert eid in g.events
    assert g.events[eid].cause_event_id == ""


def test_witness_propagation_within_window():
    reg = KnowledgeRegistry()
    reg.items["s1"] = KnowledgeItem(
        fact_id="s1", content="kho vàng ẩn giấu phía bắc rừng",
        known_by=["M"], is_secret=True, dramatic_irony=False,
    )
    post = _make_post("M", content="kho vàng ẩn giấu phía bắc", target="A", round_num=2)
    witness_post = _make_post("W", content="hỏi thăm", target="", round_num=2)
    reg.check_revelation_triggers(
        [post, witness_post], round_num=2, all_posts=[post, witness_post],
    )
    item = reg.items["s1"]
    assert "A" in item.known_by
    assert "W" in item.known_by
    w_entries = [e for e in item.reveal_log if e.char == "W"]
    assert w_entries and w_entries[0].source == "witness"


def test_witness_propagation_skipped_for_dramatic_irony():
    reg = KnowledgeRegistry()
    reg.items["s1"] = KnowledgeItem(
        fact_id="s1", content="kho vàng ẩn giấu phía bắc rừng",
        known_by=["M"], is_secret=True, dramatic_irony=True,
    )
    post = _make_post("M", content="kho vàng ẩn giấu phía bắc", target="A", round_num=2)
    witness_post = _make_post("W", content="x", target="", round_num=2)
    reg.check_revelation_triggers(
        [post, witness_post], round_num=2, all_posts=[post, witness_post],
    )
    item = reg.items["s1"]
    assert "A" in item.known_by
    assert "W" not in item.known_by  # dramatic_irony blocks witness spill


def test_witness_cap_at_3():
    reg = KnowledgeRegistry()
    reg.items["s1"] = KnowledgeItem(
        fact_id="s1", content="kho vàng ẩn giấu phía bắc rừng",
        known_by=["M"], is_secret=True, dramatic_irony=False,
    )
    post = _make_post("M", content="kho vàng ẩn giấu phía bắc", target="A", round_num=2)
    witnesses = [_make_post(f"W{i}", content="x", round_num=2) for i in range(6)]
    reg.check_revelation_triggers(
        [post] + witnesses, round_num=2, all_posts=[post] + witnesses,
    )
    item = reg.items["s1"]
    witness_names = {e.char for e in item.reveal_log if e.source == "witness"}
    assert len(witness_names) <= 3


def test_audit_skipped_when_flag_off():
    violations = audit_revelation_causality(
        llm_client=MagicMock(), graph=None, registry=None, enhanced_chapters=[], enabled=False,
    )
    assert violations == []


def test_audit_empty_registry_returns_empty():
    reg = KnowledgeRegistry()
    violations = audit_revelation_causality(
        llm_client=MagicMock(), graph=None, registry=reg, enhanced_chapters=[MagicMock()],
    )
    assert violations == []


def test_audit_flags_unknown_claimed_source():
    reg = KnowledgeRegistry()
    reg.items["secret_M"] = KnowledgeItem(
        fact_id="secret_M", content="kho vàng ẩn giấu phía bắc",
        known_by=["M"], is_secret=True,
    )
    ch = MagicMock(chapter_number=1, content="Z nói với B về kho vàng ẩn giấu phía bắc")
    llm = MagicMock()
    llm.generate_json.return_value = {
        "fact_mentions": [{
            "fact": "kho vàng ẩn giấu phía bắc",
            "claimed_source": "Z",
            "sentence": "Z nói với B về kho vàng ẩn giấu phía bắc",
        }]
    }
    violations = audit_revelation_causality(llm, CausalGraph(), reg, [ch])
    assert len(violations) == 1
    assert violations[0]["severity"] == "critical"
    assert "Z" in violations[0]["msg"]


def test_audit_accepts_revealer_within_first_two():
    reg = KnowledgeRegistry()
    item = KnowledgeItem(
        fact_id="secret_M", content="kho vàng ẩn giấu phía bắc",
        known_by=["M", "A", "B"], is_secret=True,
    )
    item.reveal_log = [
        RevealEntry(char="A", round=1, source="revealed"),
        RevealEntry(char="B", round=2, source="revealed"),
    ]
    reg.items["secret_M"] = item
    ch = MagicMock(chapter_number=2, content="B nói với C về kho vàng ẩn giấu phía bắc")
    llm = MagicMock()
    llm.generate_json.return_value = {
        "fact_mentions": [{
            "fact": "kho vàng ẩn giấu phía bắc",
            "claimed_source": "B",
            "sentence": "B nói với C về kho vàng ẩn giấu phía bắc",
        }]
    }
    violations = audit_revelation_causality(llm, CausalGraph(), reg, [ch])
    # B is in reveal_log (position 2) — within first 2, so not flagged as wrong
    assert violations == []


def test_audit_ignores_mentions_not_in_content():
    reg = KnowledgeRegistry()
    reg.items["s1"] = KnowledgeItem(
        fact_id="s1", content="kho vàng ẩn giấu", known_by=["M"], is_secret=True,
    )
    ch = MagicMock(chapter_number=1, content="some other chapter text")
    llm = MagicMock()
    llm.generate_json.return_value = {
        "fact_mentions": [{
            "fact": "kho vàng ẩn giấu", "claimed_source": "Z",
            "sentence": "phantom sentence not in content",
        }]
    }
    violations = audit_revelation_causality(llm, CausalGraph(), reg, [ch])
    assert violations == []
