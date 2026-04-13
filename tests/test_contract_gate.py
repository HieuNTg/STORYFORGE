"""Phase E — Contract Gate tests."""

from unittest.mock import MagicMock

from models.narrative_schemas import ChapterContract
from models.schemas import Chapter, PlotThread, StructuredSummary
from pipeline.layer2_enhance.contract_gate import (
    ContractFailure,
    apply_contract_gate,
    enforce_gate,
    should_rewrite,
    verify_contract,
)


def _ch(num=1, content="", summary=None, contract=None):
    ch = Chapter(
        chapter_number=num, title=f"C{num}", content=content,
        word_count=len(content.split()), structured_summary=summary,
    )
    if contract is not None:
        ch.contract = contract
    return ch


def _thread(tid, urgency=5, involved=("A",), status="open"):
    return PlotThread(
        thread_id=tid, description="d", planted_chapter=1,
        status=status, involved_characters=list(involved),
        last_mentioned_chapter=1, urgency=urgency,
    )


def test_verify_must_mention_character_missing_is_critical():
    contract = ChapterContract(chapter_number=1, must_mention_characters=["Lan"])
    ch = _ch(content="Hôm nay trời đẹp, Bình đi dạo phố.")
    fails = verify_contract(ch, contract)
    assert len(fails) == 1
    assert fails[0].field == "must_mention_characters"
    assert fails[0].severity == "critical"


def test_verify_must_mention_character_present_passes():
    contract = ChapterContract(chapter_number=1, must_mention_characters=["Lan"])
    ch = _ch(content="Lan bước vào quán cà phê.")
    assert verify_contract(ch, contract) == []


def test_verify_must_payoff_missing_is_critical():
    contract = ChapterContract(chapter_number=1, must_payoff=["bí mật gia đình"])
    ch = _ch(content="Chương này nói về chuyện khác.")
    fails = verify_contract(ch, contract)
    assert any(f.field == "must_payoff" and f.severity == "critical" for f in fails)


def test_verify_must_plant_seeds_missing_is_warning():
    contract = ChapterContract(chapter_number=1, must_plant_seeds=["mảnh ghép bị mất"])
    ch = _ch(content="Chương không gieo gì cả.")
    fails = verify_contract(ch, contract)
    assert len(fails) == 1
    assert fails[0].severity == "warning"


def test_must_advance_threads_urgency_gte_4_is_critical():
    contract = ChapterContract(chapter_number=1, must_advance_threads=["thread_revenge"])
    ch = _ch(content="Nội dung không liên quan.")
    threads = [_thread("thread_revenge", urgency=5)]
    fails = verify_contract(ch, contract, threads)
    assert any(f.field == "must_advance_threads" and f.severity == "critical" for f in fails)


def test_must_advance_threads_low_urgency_is_warning():
    contract = ChapterContract(chapter_number=1, must_advance_threads=["thread_minor"])
    ch = _ch(content="Không đề cập.")
    threads = [_thread("thread_minor", urgency=2)]
    fails = verify_contract(ch, contract, threads)
    assert any(f.field == "must_advance_threads" and f.severity == "warning" for f in fails)


def test_must_advance_threads_satisfied_via_structured_summary():
    contract = ChapterContract(chapter_number=1, must_advance_threads=["thread_revenge"])
    summary = StructuredSummary(threads_advanced=["thread_revenge"])
    ch = _ch(content="x", summary=summary)
    threads = [_thread("thread_revenge", urgency=5)]
    assert verify_contract(ch, contract, threads) == []


def test_must_advance_threads_satisfied_via_content_fallback():
    contract = ChapterContract(chapter_number=1, must_advance_threads=["thread_revenge"])
    ch = _ch(content="Kế hoạch revenge đang tiến triển.")
    threads = [_thread("thread_revenge", urgency=5)]
    assert verify_contract(ch, contract, threads) == []


def test_pacing_mismatch_is_warning():
    contract = ChapterContract(chapter_number=1, pacing_type="rising")
    summary = StructuredSummary()
    # Need to set pacing_type dynamically since schema doesn't declare it; use actual field
    object.__setattr__(summary, "pacing_type", "cooldown")
    ch = _ch(content="x", summary=summary)
    fails = verify_contract(ch, contract)
    assert any(f.field == "pacing_type" and f.severity == "warning" for f in fails)


def test_should_rewrite_two_criticals():
    fails = [
        ContractFailure("must_mention_characters", "Lan", "missing", "critical"),
        ContractFailure("must_payoff", "x", "missing", "critical"),
    ]
    assert should_rewrite(fails) is True


def test_should_rewrite_one_critical_two_warnings():
    fails = [
        ContractFailure("must_payoff", "x", "missing", "critical"),
        ContractFailure("must_plant_seeds", "a", "missing", "warning"),
        ContractFailure("pacing_type", "rising", "cooldown", "warning"),
    ]
    assert should_rewrite(fails) is True


def test_should_rewrite_one_critical_only():
    fails = [ContractFailure("must_payoff", "x", "missing", "critical")]
    assert should_rewrite(fails) is False


def test_should_rewrite_all_warnings():
    fails = [
        ContractFailure("must_plant_seeds", "a", "missing", "warning"),
        ContractFailure("pacing_type", "rising", "cooldown", "warning"),
        ContractFailure("must_plant_seeds", "b", "missing", "warning"),
    ]
    assert should_rewrite(fails) is False


def test_enforce_gate_skips_when_threshold_not_met():
    llm = MagicMock()
    ch = _ch(content="gốc")
    contract = ChapterContract(chapter_number=1)
    fails = [ContractFailure("must_payoff", "x", "missing", "critical")]  # only 1 crit
    result = enforce_gate(llm, ch, contract, fails)
    assert result is ch
    llm.generate.assert_not_called()


def test_enforce_gate_rewrites_and_commits_when_improved():
    llm = MagicMock()
    llm.generate.return_value = "Lan và Bình trò chuyện. Bí mật được tiết lộ."
    contract = ChapterContract(
        chapter_number=1,
        must_mention_characters=["Lan", "Bình"],
        must_payoff=["bí mật"],
    )
    ch = _ch(content="Không có gì.")
    fails = verify_contract(ch, contract)
    assert should_rewrite(fails)
    result = enforce_gate(llm, ch, contract, fails)
    assert result is not ch
    assert "Lan" in result.content and "Bình" in result.content
    assert result.enhancement_changelog
    llm.generate.assert_called_once()


def test_enforce_gate_reverts_when_rewrite_regresses():
    llm = MagicMock()
    llm.generate.return_value = "Nội dung rỗng không giải quyết gì."
    contract = ChapterContract(
        chapter_number=1,
        must_mention_characters=["Lan", "Bình"],
        must_payoff=["bí mật", "kho báu"],
    )
    ch = _ch(content="Lan nói về kho báu.")  # partial: has Lan + kho báu (1 crit miss: Bình + bí mật = 2 miss pre)
    fails = verify_contract(ch, contract)
    pre_crit = sum(1 for f in fails if f.severity == "critical")
    assert pre_crit >= 2
    result = enforce_gate(llm, ch, contract, fails)
    # Rewrite has NO "Lan", "Bình", "bí mật", "kho báu" → post_crit=4 > pre_crit → revert
    assert result is ch


def test_enforce_gate_llm_failure_non_fatal():
    llm = MagicMock()
    llm.generate.side_effect = Exception("API down")
    contract = ChapterContract(
        chapter_number=1,
        must_mention_characters=["Lan"],
        must_payoff=["bí mật"],
    )
    ch = _ch(content="Không có gì.")
    fails = verify_contract(ch, contract)
    result = enforce_gate(llm, ch, contract, fails)
    assert result is ch


def test_apply_contract_gate_disabled():
    enhanced = MagicMock()
    stats = apply_contract_gate(MagicMock(), enhanced, None, enabled=False)
    assert stats == {"enabled": False, "chapters_checked": 0, "rewrites": 0}


def test_apply_contract_gate_skips_chapters_without_contract():
    llm = MagicMock()
    enhanced = MagicMock()
    enhanced.chapters = [_ch(num=1, content="x")]  # no contract
    stats = apply_contract_gate(llm, enhanced, None, enabled=True)
    assert stats["chapters_checked"] == 1
    assert stats["rewrites"] == 0
    llm.generate.assert_not_called()


def test_apply_contract_gate_counts_total_failures():
    llm = MagicMock()
    llm.generate.return_value = "Lan và Bình nói về bí mật."
    contract = ChapterContract(
        chapter_number=1,
        must_mention_characters=["Lan", "Bình"],
        must_payoff=["bí mật"],
    )
    ch = _ch(num=1, content="Nội dung trống", contract=contract)
    enhanced = MagicMock()
    enhanced.chapters = [ch]
    stats = apply_contract_gate(llm, enhanced, None, enabled=True)
    assert stats["enabled"] is True
    assert stats["chapters_checked"] == 1
    assert stats["total_failures"] >= 3
    assert stats["rewrites"] == 1
