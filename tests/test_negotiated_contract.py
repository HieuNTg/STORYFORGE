"""Sprint 1 P5 — NegotiatedChapterContract unification tests."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from models.handoff_schemas import NegotiatedChapterContract
from models.narrative_schemas import ChapterContract
from models.schemas import Chapter
from pipeline.handoff_gate import reconcile_contract
from pipeline.layer2_enhance.contract_gate import (
    ContractFailure,
    should_rewrite,
    verify_contract,
)


def _ch(num=1, content=""):
    return Chapter(
        chapter_number=num, title=f"C{num}", content=content,
        word_count=len(content.split()),
    )


class TestBuildL1OnlyPortion:
    def test_l1_portion_only_l2_empty(self):
        c = NegotiatedChapterContract(
            chapter_num=3, pacing_type="rising",
            threads_advance=["t1"], seeds_plant=["s1"], payoffs_required=["f1"],
        )
        assert c.chapter_num == 3
        assert c.threads_advance == ["t1"]
        assert c.drama_target == 0.0
        assert c.escalation_events == []
        assert c.reconciled is False


class TestFillL2Portion:
    def test_filling_l2_preserves_l1(self):
        c = NegotiatedChapterContract(
            chapter_num=5, pacing_type="climax",
            threads_advance=["thread_revenge"], payoffs_required=["bí mật"],
            must_mention_characters=["Lan", "Bình"],
        )
        filled = c.model_copy(update={
            "drama_target": 0.85,
            "escalation_events": ["đối đầu", "tiết lộ"],
            "causal_refs": ["bí mật"],
        })
        assert filled.threads_advance == ["thread_revenge"]
        assert filled.must_mention_characters == ["Lan", "Bình"]
        assert filled.payoffs_required == ["bí mật"]
        assert filled.drama_target == pytest.approx(0.85)
        assert "đối đầu" in filled.escalation_events


class TestReconcileAfterL2Fill:
    def test_cooldown_clamps_high_drama(self):
        c = NegotiatedChapterContract(
            chapter_num=10, pacing_type="cooldown",
            drama_target=0.9,
        )
        out = reconcile_contract(c)
        assert out.reconciled is True
        assert out.drama_target == pytest.approx(0.4)
        assert any("clamped" in w for w in out.reconciliation_warnings)

    def test_climax_raises_low_drama(self):
        c = NegotiatedChapterContract(
            chapter_num=8, pacing_type="climax",
            drama_target=0.5,
        )
        out = reconcile_contract(c)
        assert out.drama_target == pytest.approx(0.75)
        assert any("raised" in w for w in out.reconciliation_warnings)

    def test_payoffs_without_causal_refs_warns(self):
        c = NegotiatedChapterContract(
            chapter_num=4, pacing_type="rising",
            payoffs_required=["bí_mật_gia_đình"],
            causal_refs=["sự_kiện_khác"],
        )
        out = reconcile_contract(c)
        assert any("payoffs_required" in w for w in out.reconciliation_warnings)

    def test_idempotent_when_aligned(self):
        c = NegotiatedChapterContract(
            chapter_num=2, pacing_type="rising",
            payoffs_required=["seed1"], causal_refs=["seed1"],
            drama_target=0.6,
        )
        out = reconcile_contract(c)
        assert out.reconciled is True
        assert out.drama_target == pytest.approx(0.6)
        assert out.reconciliation_warnings == []


class TestVerifyContract:
    def test_payoff_missing_is_critical(self):
        contract = ChapterContract(chapter_number=1, must_payoff=["bí mật gia đình"])
        ch = _ch(content="Chương về chuyện hoàn toàn khác.")
        fails = verify_contract(ch, contract)
        assert any(f.field == "must_payoff" and f.severity == "critical" for f in fails)


class TestShouldRewriteSinglePayoffCritical:
    def test_single_must_payoff_critical_triggers_rewrite(self):
        # Audit fix L2#5: single must_payoff critical should rewrite.
        fails = [ContractFailure("must_payoff", "bí mật", "missed", "critical")]
        assert should_rewrite(fails) is True

    def test_single_other_critical_does_not_trigger(self):
        fails = [ContractFailure("must_mention_characters", "Lan", "missing", "critical")]
        assert should_rewrite(fails) is False

    def test_legacy_two_criticals_still_triggers(self):
        fails = [
            ContractFailure("must_mention_characters", "Lan", "missing", "critical"),
            ContractFailure("must_advance_threads", "t1", "missing", "critical"),
        ]
        assert should_rewrite(fails) is True


class TestSnapshot3Chapter:
    def test_snapshot_three_chapter_story(self):
        contracts = [
            NegotiatedChapterContract(
                chapter_num=i, pacing_type=p,
                threads_advance=[f"t{i}"], must_mention_characters=["Hoa", "Minh"],
                payoffs_required=[f"f{i}"] if i == 3 else [],
            )
            for i, p in [(1, "setup"), (2, "rising"), (3, "climax")]
        ]
        # Fill L2 portion
        filled = []
        for c in contracts:
            l2 = {
                "drama_target": 0.4 if c.pacing_type == "setup"
                                else 0.6 if c.pacing_type == "rising"
                                else 0.85,
                "escalation_events": [f"event_ch{c.chapter_num}"],
                "causal_refs": list(c.payoffs_required),
            }
            filled.append(reconcile_contract(c.model_copy(update=l2)))
        assert len(filled) == 3
        assert all(c.reconciled for c in filled)
        assert filled[2].drama_target == pytest.approx(0.85)
        assert filled[2].causal_refs == ["f3"]
        # Climax with payoffs+causal_refs aligned → no payoff warning.
        assert not any("payoffs_required" in w for w in filled[2].reconciliation_warnings)


class TestLegacyChapterContractToNegotiated:
    def test_round_trip(self):
        legacy = ChapterContract(
            chapter_number=7,
            must_advance_threads=["t1"],
            must_payoff=["payoff1"],
            must_mention_characters=["Hoa"],
            pacing_type="climax",
            emotional_endpoint="bùng nổ",
        )
        nc = legacy.to_negotiated()
        assert nc.chapter_num == 7
        assert nc.threads_advance == ["t1"]
        assert nc.payoffs_required == ["payoff1"]
        assert nc.pacing_type == "climax"
        assert nc.emotional_endpoint == "bùng nổ"
