"""Contract Gate — validate enhanced chapters against ChapterContract, rewrite if critical.

Pure-Python verification; single LLM rewrite call max per chapter (gated by severity).
"""

import logging
from typing import NamedTuple

from models.narrative_schemas import ChapterContract
from models.schemas import Chapter

logger = logging.getLogger(__name__)


class ContractFailure(NamedTuple):
    field: str
    expected: str
    actual: str
    severity: str  # "critical" | "warning"


def _tokens(text: str) -> set[str]:
    return {w.strip(".,!?;:\"'()[]").lower() for w in (text or "").split() if w.strip()}


def _contains_ci(content: str, needle: str) -> bool:
    return bool(needle) and needle.casefold() in content.casefold()


def verify_contract(
    chapter: Chapter,
    contract: ChapterContract,
    draft_threads: list | None = None,
) -> list[ContractFailure]:
    """Pure-Python validation of chapter against its contract. Returns list of failures."""
    failures: list[ContractFailure] = []
    content = chapter.content or ""
    summary = getattr(chapter, "structured_summary", None)

    # must_mention_characters — critical
    for name in contract.must_mention_characters or []:
        if not _contains_ci(content, name):
            failures.append(ContractFailure(
                field="must_mention_characters",
                expected=name, actual="not found in content",
                severity="critical",
            ))

    # must_advance_threads — critical if thread urgency >= 4, else warning
    threads_advanced = set()
    if summary is not None:
        try:
            threads_advanced = set(getattr(summary, "threads_advanced", []) or [])
        except Exception:
            threads_advanced = set()

    thread_urgency_map: dict[str, int] = {}
    if draft_threads:
        for t in draft_threads:
            tid = getattr(t, "thread_id", "")
            if tid:
                thread_urgency_map[tid] = getattr(t, "urgency", 3) or 3

    for tid in contract.must_advance_threads or []:
        if tid in threads_advanced:
            continue
        # Fallback: substring match on thread_id tokens in content
        tid_tokens = [tok for tok in tid.replace("_", " ").split() if len(tok) >= 3]
        if tid_tokens and any(tok.lower() in content.lower() for tok in tid_tokens):
            continue
        severity = "critical" if thread_urgency_map.get(tid, 3) >= 4 else "warning"
        failures.append(ContractFailure(
            field="must_advance_threads",
            expected=tid, actual="no evidence of advancement",
            severity=severity,
        ))

    # must_plant_seeds — warning
    for seed in contract.must_plant_seeds or []:
        if not _contains_ci(content, seed):
            failures.append(ContractFailure(
                field="must_plant_seeds",
                expected=seed, actual="not planted",
                severity="warning",
            ))

    # must_payoff — critical
    for payoff in contract.must_payoff or []:
        if not _contains_ci(content, payoff):
            failures.append(ContractFailure(
                field="must_payoff",
                expected=payoff, actual="missed",
                severity="critical",
            ))

    # pacing_type — warning if mismatch with structured_summary
    if contract.pacing_type and summary is not None:
        actual_pacing = getattr(summary, "pacing_type", "") or ""
        if actual_pacing and actual_pacing != contract.pacing_type:
            failures.append(ContractFailure(
                field="pacing_type",
                expected=contract.pacing_type, actual=actual_pacing,
                severity="warning",
            ))

    # emotional_endpoint — warning (fuzzy token-overlap ≥ 0.4)
    if contract.emotional_endpoint and summary is not None:
        actual_arc = (
            getattr(summary, "actual_emotional_arc", "")
            or getattr(summary, "emotional_endpoint", "")
            or ""
        )
        if actual_arc:
            a = _tokens(contract.emotional_endpoint)
            b = _tokens(actual_arc)
            if a and b:
                overlap = len(a & b) / max(1, min(len(a), len(b)))
                if overlap < 0.4:
                    failures.append(ContractFailure(
                        field="emotional_endpoint",
                        expected=contract.emotional_endpoint, actual=actual_arc[:80],
                        severity="warning",
                    ))

    # character_arc_targets — warning if char missing from character_developments
    if contract.character_arc_targets and summary is not None:
        devs = getattr(summary, "character_developments", {}) or {}
        dev_names = set()
        if isinstance(devs, dict):
            dev_names = {k.lower() for k in devs.keys()}
        elif isinstance(devs, list):
            for d in devs:
                n = getattr(d, "character", "") or (d.get("character", "") if isinstance(d, dict) else "")
                if n:
                    dev_names.add(n.lower())
        for char_name in contract.character_arc_targets.keys():
            if char_name.lower() not in dev_names:
                failures.append(ContractFailure(
                    field="character_arc_targets",
                    expected=char_name, actual="no development recorded",
                    severity="warning",
                ))

    return failures


def should_rewrite(failures: list[ContractFailure]) -> bool:
    """Rewrite when payoff missed (any single must_payoff critical), OR ≥ 2
    critical, OR ≥ 1 critical + ≥ 2 warnings.

    Audit finding L2#5: a single `must_payoff` critical is a contract breach
    significant enough to trigger rewrite on its own — payoffs cannot be
    deferred to "the next chapter" without breaking foreshadowing chains.
    """
    crit = sum(1 for f in failures if f.severity == "critical")
    warn = sum(1 for f in failures if f.severity == "warning")
    payoff_missed = any(
        f.severity == "critical" and f.field == "must_payoff" for f in failures
    )
    return payoff_missed or crit >= 2 or (crit >= 1 and warn >= 2)


def _format_missed(failures: list[ContractFailure]) -> str:
    lines = []
    for f in failures:
        tag = "[CRITICAL]" if f.severity == "critical" else "[WARN]"
        lines.append(f"- {tag} {f.field}: cần '{f.expected}' — {f.actual}")
    return "\n".join(lines) or "(không có)"


def enforce_gate(
    llm,
    chapter: Chapter,
    contract: ChapterContract,
    failures: list[ContractFailure],
    max_retries: int = 1,
    draft_threads: list | None = None,
    idea: str = "",
    idea_summary: str = "",
) -> Chapter:
    """Rewrite chapter once to address contract failures. Non-fatal on LLM error."""
    if not failures or not should_rewrite(failures) or max_retries <= 0:
        return chapter

    from services.prompts import CONTRACT_REWRITE
    from services.text_utils import build_idea_header

    missed = _format_missed(failures)
    original_content = chapter.content or ""
    target_words = max(500, chapter.word_count or len(original_content.split()))
    idea_header = build_idea_header(idea, idea_summary) if idea else ""

    try:
        rewritten = llm.generate(
            system_prompt=(
                "Bạn là nhà văn sửa chương để đáp ứng hợp đồng chương. "
                "BẮT BUỘC: Viết hoàn toàn bằng tiếng Việt, giữ nguyên giọng văn."
            ),
            user_prompt=CONTRACT_REWRITE.format(
                user_story_idea_header=idea_header,
                missed_items=missed,
                content=original_content[:6000],
                word_count=target_words,
            ),
            max_tokens=8192,
        )
    except Exception as e:
        logger.warning(f"[contract_gate] LLM rewrite ch{chapter.chapter_number} failed: {e}")
        return chapter

    if not rewritten or not rewritten.strip():
        logger.warning(f"[contract_gate] empty rewrite ch{chapter.chapter_number}, keeping original")
        return chapter

    # Re-verify; revert if rewrite made things worse
    new_chapter = chapter.model_copy(update={
        "content": rewritten,
        "word_count": len(rewritten.split()),
    })
    post_failures = verify_contract(new_chapter, contract, draft_threads)
    post_crit = sum(1 for f in post_failures if f.severity == "critical")
    pre_crit = sum(1 for f in failures if f.severity == "critical")
    if post_crit > pre_crit:
        logger.info(
            f"[contract_gate] rewrite ch{chapter.chapter_number} regressed "
            f"(pre_crit={pre_crit} → post_crit={post_crit}); reverting"
        )
        return chapter
    # Voice re-validation: revert if rewritten chapter drops voice score below floor
    if not _post_gate_validate(new_chapter, chapter):
        logger.info(
            f"[contract_gate] rewrite ch{chapter.chapter_number} failed voice re-validation; reverting"
        )
        return chapter
    new_chapter.enhancement_changelog.append(
        f"[contract_gate] rewrote for {len(failures)} failures "
        f"({pre_crit} critical → {post_crit} remaining)"
    )
    return new_chapter


def apply_contract_gate(
    llm,
    enhanced_story,
    draft_threads: list | None = None,
    enabled: bool = True,
    draft=None,
) -> dict:
    """Apply gate to all chapters; return summary stats.

    `draft` (optional) supplies the author's original_idea so contract rewrites
    don't drift proper nouns / gimmicks back to genre default.
    """
    if not enabled or enhanced_story is None:
        return {"enabled": False, "chapters_checked": 0, "rewrites": 0}

    _idea = getattr(draft, "original_idea", "") or "" if draft is not None else ""
    _idea_summary = getattr(draft, "idea_summary_for_chapters", "") or "" if draft is not None else ""

    rewrites = 0
    total_failures = 0
    for idx, ch in enumerate(enhanced_story.chapters):
        contract = getattr(ch, "contract", None)
        if not contract:
            continue
        failures = verify_contract(ch, contract, draft_threads)
        total_failures += len(failures)
        if should_rewrite(failures):
            try:
                new_ch = enforce_gate(
                    llm, ch, contract, failures,
                    max_retries=1, draft_threads=draft_threads,
                    idea=_idea, idea_summary=_idea_summary,
                )
                if new_ch is not ch:
                    enhanced_story.chapters[idx] = new_ch
                    rewrites += 1
            except Exception as e:
                logger.warning(f"[contract_gate] ch{ch.chapter_number} exception: {e}")
        else:
            if failures:
                ch.enhancement_changelog.append(
                    f"[contract_gate] {len(failures)} non-critical failures logged"
                )
    return {
        "enabled": True,
        "chapters_checked": len(enhanced_story.chapters),
        "rewrites": rewrites,
        "total_failures": total_failures,
    }


def _post_gate_validate(new_chapter: Chapter, original_chapter: Chapter) -> bool:
    """Return True (keep rewrite) or False (revert) based on voice score of rewritten chapter.

    Reads voice_binary_revert_floor from PipelineConfig. If voice validation raises,
    logs and returns False (reverts) — idempotent and bounded.
    Lane classifier check deferred to P1 (lane_classifier.py unwired+untested).
    """
    try:
        from config.config import ConfigManager
        cfg = ConfigManager().load().pipeline
        revert_floor = float(getattr(cfg, "voice_binary_revert_floor", 0.5))
    except Exception:
        revert_floor = 0.5

    try:
        voice_contract = getattr(new_chapter, "voice_contract", None)
        if voice_contract is None:
            # No voice contract on this chapter — nothing to validate, keep the rewrite
            return True

        from pipeline.layer2_enhance.chapter_contract import validate_chapter_voice
        from services.llm_client import LLMClient
        llm = LLMClient()
        validation = validate_chapter_voice(llm, new_chapter.content or "", voice_contract)
        if validation.overall_compliance < revert_floor:
            logger.info(
                "[contract_gate] ch%d voice compliance=%.2f < floor=%.2f → revert",
                new_chapter.chapter_number, validation.overall_compliance, revert_floor,
            )
            return False
        return True
    except Exception as exc:
        logger.warning(
            "[contract_gate] _post_gate_validate ch%d raised %s — treating as fail, reverting",
            new_chapter.chapter_number, exc,
        )
        return False
