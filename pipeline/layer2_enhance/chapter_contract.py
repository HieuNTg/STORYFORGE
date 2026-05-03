"""Sprint 1 Task 3 — Simulator → Enhancer contract enforcement.

Simulator emits a DramaContract per chapter (drama target + required
escalations / subtext / causal refs). Enhancer runs scene enhancement,
then cheap-LLM validates the enhanced chapter against the contract. If
validation fails and retry is enabled, enhancement re-runs once with a
hint derived from the failed validation.

Keeps the existing `enhance_chapter_by_scenes(...)` API intact; retry
hints flow through a thin wrapper rather than threading new kwargs
through the whole scene-enhancement chain.
"""
from __future__ import annotations

import logging

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class DramaContract(BaseModel):
    """Contract from simulator to enhancer for a single chapter."""
    chapter_number: int
    drama_target: float = Field(default=0.6, ge=0.0, le=1.0)
    drama_tolerance: float = Field(default=0.15, ge=0.0, le=1.0)
    required_escalations: list[str] = Field(default_factory=list)
    required_subtext: list[str] = Field(default_factory=list)
    required_causal_refs: list[int] = Field(default_factory=list)
    forbidden_patterns: list[str] = Field(default_factory=list)


class ContractValidation(BaseModel):
    """Result of validating an enhanced chapter against its contract."""
    chapter_number: int
    passed: bool = False
    drama_actual: float = 0.0
    drama_delta: float = 0.0
    missing_escalations: list[str] = Field(default_factory=list)
    missing_subtext: list[str] = Field(default_factory=list)
    missing_causal_refs: list[int] = Field(default_factory=list)
    violated_patterns: list[str] = Field(default_factory=list)
    compliance_score: float = 0.0
    reason: str = ""
    retry_attempted: bool = False


def _clip(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def build_chapter_contracts(sim_result, chapter_numbers: list[int]) -> dict[int, DramaContract]:
    """Derive DramaContract per chapter from SimulationResult.

    Adapts to real SimulationResult schema (events, drama_suggestions, causal_chains,
    tension_map) rather than the speculative schema in the original plan.
    """
    from models.schemas import SimulationResult as _SR  # noqa: F401

    contracts: dict[int, DramaContract] = {}
    events = getattr(sim_result, "events", []) or []
    drama_sugs = getattr(sim_result, "drama_suggestions", []) or []
    tension_map = getattr(sim_result, "tension_map", {}) or {}

    # Average tension to estimate a baseline target
    baseline = 0.6
    if tension_map:
        vals = [float(v) for v in tension_map.values() if isinstance(v, (int, float))]
        if vals:
            baseline = _clip(sum(vals) / len(vals), 0.3, 0.95)

    def _events_for(ch_num: int) -> list:
        hits: list = []
        for e in events:
            tag = getattr(e, "suggested_insertion", "") or ""
            # tag like "chương 3", "ch3", "3" — accept any containing the chapter number
            if str(ch_num) in tag:
                hits.append(e)
        return hits

    for ch_num in chapter_numbers:
        ch_events = _events_for(ch_num)

        # Drama target: mean of event drama scores for this chapter, else baseline
        if ch_events:
            scores = [float(getattr(e, "drama_score", 0.5)) for e in ch_events]
            drama_target = _clip(sum(scores) / len(scores), 0.3, 0.95)
        else:
            drama_target = baseline

        # Required escalations: top 3 event descriptions for this chapter
        escalations = [
            (getattr(e, "description", "") or "").strip()
            for e in ch_events[:3]
            if getattr(e, "description", "")
        ]

        # Required subtext: drama_suggestions (global list — take first N for first chapters)
        # Distribute suggestions across chapters deterministically
        subtext: list[str] = []
        if drama_sugs:
            idx = (ch_num - 1) % max(1, len(drama_sugs))
            subtext = [drama_sugs[idx]]

        # Causal refs: for each event in this chapter with cause_event_id, find
        # source event and map back to its chapter via suggested_insertion
        causal_refs: list[int] = []
        for e in ch_events:
            cause_id = getattr(e, "cause_event_id", "") or ""
            if not cause_id:
                continue
            # Look up source chapter from any matching event description
            for src in events:
                if cause_id and cause_id in (getattr(src, "event_type", "") or ""):
                    tag = getattr(src, "suggested_insertion", "") or ""
                    for num in _extract_chapter_nums(tag):
                        if num != ch_num and num not in causal_refs:
                            causal_refs.append(num)

        contracts[ch_num] = DramaContract(
            chapter_number=ch_num,
            drama_target=drama_target,
            required_escalations=escalations,
            required_subtext=subtext,
            required_causal_refs=causal_refs,
        )

    return contracts


def _extract_chapter_nums(text: str) -> list[int]:
    import re
    return [int(x) for x in re.findall(r"\d+", text or "")]


def validate_chapter_against_contract(
    llm,
    chapter_content: str,
    contract: DramaContract,
    model_tier: str = "cheap",
) -> ContractValidation:
    """Single cheap LLM call → structured validation against contract."""
    content_excerpt = (chapter_content or "")[:4000]
    prompt = (
        "Đánh giá chương sau có đáp ứng yêu cầu không.\n\n"
        f"CHƯƠNG:\n{content_excerpt}\n\n"
        "YÊU CẦU:\n"
        f"- Drama intensity target: {contract.drama_target:.2f} (0.0-1.0)\n"
        f"- Phải có các escalation: {contract.required_escalations}\n"
        f"- Phải có subtext tâm lý: {contract.required_subtext}\n"
        f"- Phải reference sự kiện từ chương: {contract.required_causal_refs}\n"
        f"- Không được có: {contract.forbidden_patterns}\n\n"
        "Trả về JSON đúng schema:\n"
        '{"drama_actual": <0.0-1.0>, "missing_escalations": [..], '
        '"missing_subtext": [..], "missing_causal_refs": [..], '
        '"violated_patterns": [..], "reason": "1 câu"}'
    )

    try:
        raw = llm.generate_json(
            system_prompt="Bạn là biên tập viên khắt khe. Trả về JSON thuần.",
            user_prompt=prompt,
            temperature=0.2,
            model_tier=model_tier,
        )
    except Exception as exc:
        logger.warning("Contract validation LLM call failed for ch%d: %s", contract.chapter_number, exc)
        return ContractValidation(
            chapter_number=contract.chapter_number,
            passed=False,
            reason=f"validation_llm_error: {exc}",
        )

    if not isinstance(raw, dict):
        raw = {}

    drama_actual = _clip(float(raw.get("drama_actual", 0.0) or 0.0), 0.0, 1.0)
    missing_esc = [str(x) for x in (raw.get("missing_escalations") or []) if x]
    missing_sub = [str(x) for x in (raw.get("missing_subtext") or []) if x]
    missing_causal = [int(x) for x in (raw.get("missing_causal_refs") or []) if str(x).lstrip("-").isdigit()]
    violated = [str(x) for x in (raw.get("violated_patterns") or []) if x]

    drama_delta = drama_actual - contract.drama_target
    miss_penalty = (
        len(missing_esc) * 0.10
        + len(missing_sub) * 0.05
        + len(missing_causal) * 0.05
        + len(violated) * 0.20
    )
    drama_penalty = max(0.0, abs(drama_delta) - contract.drama_tolerance) * 0.5
    compliance = _clip(1.0 - miss_penalty - drama_penalty, 0.0, 1.0)

    passed = (
        abs(drama_delta) <= contract.drama_tolerance
        and not missing_esc
        and not violated
        and compliance >= 0.7
    )

    return ContractValidation(
        chapter_number=contract.chapter_number,
        passed=passed,
        drama_actual=drama_actual,
        drama_delta=drama_delta,
        missing_escalations=missing_esc,
        missing_subtext=missing_sub,
        missing_causal_refs=missing_causal,
        violated_patterns=violated,
        compliance_score=compliance,
        reason=str(raw.get("reason", ""))[:300],
    )


def build_retry_hint(validation: ContractValidation) -> str:
    """Human-readable retry prompt hint derived from failed validation."""
    parts: list[str] = []
    if validation.drama_delta < 0:
        parts.append(
            f"Drama hiện tại thấp ({validation.drama_actual:.2f}). "
            "Cần tăng xung đột, subtext, đối đầu."
        )
    elif validation.drama_delta > 0:
        parts.append(
            f"Drama đang quá cao ({validation.drama_actual:.2f}). "
            "Giảm bớt melodrama, giữ tension có mục đích."
        )
    if validation.missing_escalations:
        parts.append("Thiếu escalation: " + "; ".join(validation.missing_escalations))
    if validation.missing_subtext:
        parts.append("Thiếu subtext: " + "; ".join(validation.missing_subtext))
    if validation.missing_causal_refs:
        parts.append("Phải reference sự kiện chương: " + ", ".join(str(c) for c in validation.missing_causal_refs))
    if validation.violated_patterns:
        parts.append("PHẢI LOẠI BỎ: " + "; ".join(validation.violated_patterns))
    return "\n".join(f"- {p}" for p in parts)


# ══════════════════════════════════════════════════════════════════════════════
# Sprint 2 Task 2 — Voice Contract
# ══════════════════════════════════════════════════════════════════════════════


class VoiceContract(BaseModel):
    """Per-chapter voice contract derived from unified VoiceProfile + chapter speakers."""
    chapter_number: int
    per_character: dict[str, dict] = Field(default_factory=dict)
    min_compliance: float = Field(default=0.75, ge=0.0, le=1.0)
    tolerance_missing_tics: int = Field(default=1, ge=0)


class VoiceValidation(BaseModel):
    chapter_number: int
    per_character_scores: dict[str, float] = Field(default_factory=dict)
    overall_compliance: float = 0.0
    drifted_characters: list[str] = Field(default_factory=list)
    missing_tics: dict[str, list[str]] = Field(default_factory=dict)
    tone_mismatches: dict[str, str] = Field(default_factory=dict)
    passed: bool = False
    retry_attempted: bool = False
    binary_reverted: bool = False
    reason: str = ""


def _infer_speakers(outline, characters: list | None = None) -> list[str]:
    """Derive chapter speakers from outline fields + character list fallback."""
    # ChapterOutline has optional featured_characters / characters_involved / key_events
    for attr in ("featured_characters", "characters_involved", "speakers"):
        vals = getattr(outline, attr, None)
        if vals:
            return [str(v) for v in vals if v]
    # Fallback: scan key_events + summary for character names
    text = " ".join([
        getattr(outline, "summary", "") or "",
        " ".join(getattr(outline, "key_events", []) or []),
    ])
    if characters:
        hits = [c.name for c in characters if getattr(c, "name", "") and c.name in text]
        if hits:
            return hits
    return [c.name for c in (characters or []) if getattr(c, "name", "")]


def build_voice_contracts(
    voice_profiles: list[dict] | dict,
    chapter_outlines: list,
    characters: list | None = None,
    min_compliance: float = 0.75,
    tolerance_missing_tics: int = 1,
) -> dict[int, VoiceContract]:
    """Derive per-chapter voice contracts from L1 voice profiles + outline speakers.

    voice_profiles: either list of dicts (StoryDraft.voice_profiles) or {name: dict/VoiceProfile}.
    """
    if isinstance(voice_profiles, list):
        vp_map = {p.get("name", ""): p for p in voice_profiles if isinstance(p, dict) and p.get("name")}
    else:
        vp_map = {}
        for k, v in (voice_profiles or {}).items():
            vp_map[k] = v.model_dump() if hasattr(v, "model_dump") else v

    contracts: dict[int, VoiceContract] = {}
    for outline in chapter_outlines or []:
        ch_num = getattr(outline, "chapter_number", None)
        if ch_num is None:
            continue
        speakers = _infer_speakers(outline, characters)
        per_char: dict[str, dict] = {}
        for name in speakers:
            vp = vp_map.get(name)
            if not vp:
                continue
            # Unified schema uses verbal_tics + dialogue_examples; legacy L1 uses dialogue_example; legacy L2 uses speech_quirks/dialogue_samples
            tics = list(vp.get("verbal_tics") or vp.get("speech_quirks") or [])[:4]
            examples = list(
                vp.get("dialogue_examples")
                or vp.get("dialogue_example")
                or vp.get("dialogue_samples")
                or []
            )[:2]
            per_char[name] = {
                "vocabulary_level": vp.get("vocabulary_level", ""),
                "sentence_style": vp.get("sentence_style", ""),
                "verbal_tics": tics,
                "dialogue_examples": examples,
            }
        if per_char:
            contracts[ch_num] = VoiceContract(
                chapter_number=ch_num,
                per_character=per_char,
                min_compliance=min_compliance,
                tolerance_missing_tics=tolerance_missing_tics,
            )
    return contracts


def _extract_dialogues(content: str, limit_chars: int = 4000) -> str:
    """Pull quoted segments from chapter content; fall back to raw excerpt."""
    import re as _re
    quotes = _re.findall(r'"([^"]{3,200})"', content or "")
    if not quotes:
        return (content or "")[:limit_chars]
    joined = "\n".join(f'- "{q}"' for q in quotes[:40])
    return joined[:limit_chars]


def _format_voice_profiles_for_prompt(per_character: dict[str, dict]) -> str:
    lines: list[str] = []
    for name, spec in per_character.items():
        parts = [f"**{name}**:"]
        if spec.get("vocabulary_level"):
            parts.append(f"từ vựng={spec['vocabulary_level']}")
        if spec.get("sentence_style"):
            parts.append(f"câu={spec['sentence_style']}")
        if spec.get("verbal_tics"):
            parts.append(f"tics={', '.join(spec['verbal_tics'])}")
        if spec.get("dialogue_examples"):
            parts.append(f'ví dụ="{spec["dialogue_examples"][0][:80]}"')
        lines.append(" ".join(parts))
    return "\n".join(lines)


def validate_chapter_voice(
    llm,
    chapter_content: str,
    contract: VoiceContract,
    model_tier: str = "cheap",
) -> VoiceValidation:
    """Single cheap LLM call → structured voice compliance grading for all chapter speakers."""
    if not contract.per_character:
        return VoiceValidation(
            chapter_number=contract.chapter_number,
            passed=True,
            overall_compliance=1.0,
            reason="no_speakers",
        )

    prompt = (
        "Đánh giá giọng điệu đối thoại trong chương sau so với hồ sơ giọng nói mỗi nhân vật.\n\n"
        f"CHƯƠNG (dialogues):\n{_extract_dialogues(chapter_content)}\n\n"
        f"HỒ SƠ GIỌNG NÓI YÊU CẦU:\n{_format_voice_profiles_for_prompt(contract.per_character)}\n\n"
        "Trả về JSON thuần:\n"
        '{"per_character": {"<name>": {"compliance_score": 0.0-1.0, '
        '"missing_tics": [..], "tone_mismatch": "mô tả nếu giọng lệch, empty nếu OK"}}, '
        '"reason": "1 câu tóm tắt"}'
    )

    try:
        raw = llm.generate_json(
            system_prompt="Bạn là biên tập viên giọng văn khắt khe. Trả về JSON thuần.",
            user_prompt=prompt,
            temperature=0.2,
            model_tier=model_tier,
        )
    except Exception as exc:
        logger.warning("Voice validation LLM call failed for ch%d: %s", contract.chapter_number, exc)
        return VoiceValidation(
            chapter_number=contract.chapter_number,
            passed=False,
            reason=f"voice_llm_error: {type(exc).__name__}",
        )

    if not isinstance(raw, dict):
        return VoiceValidation(chapter_number=contract.chapter_number, passed=False, reason="malformed")

    per_char_result = raw.get("per_character", {}) or {}
    per_scores: dict[str, float] = {}
    drifted: list[str] = []
    missing: dict[str, list[str]] = {}
    tone: dict[str, str] = {}

    for name in contract.per_character:
        info = per_char_result.get(name) if isinstance(per_char_result, dict) else None
        if not isinstance(info, dict):
            info = {}
        score = _clip(float(info.get("compliance_score", 0.0) or 0.0), 0.0, 1.0)
        per_scores[name] = score
        m = [str(x) for x in (info.get("missing_tics") or []) if x]
        if len(m) > contract.tolerance_missing_tics:
            missing[name] = m
        tm = str(info.get("tone_mismatch") or "").strip()
        if tm:
            tone[name] = tm
        if score < contract.min_compliance:
            drifted.append(name)

    overall = sum(per_scores.values()) / max(1, len(per_scores))
    passed = overall >= contract.min_compliance and not drifted and not tone

    return VoiceValidation(
        chapter_number=contract.chapter_number,
        per_character_scores=per_scores,
        overall_compliance=round(overall, 3),
        drifted_characters=drifted,
        missing_tics=missing,
        tone_mismatches=tone,
        passed=passed,
        reason=str(raw.get("reason", ""))[:300],
    )


def build_voice_retry_hint(validation: VoiceValidation) -> str:
    """Human-readable retry prompt hint for scene enhancer."""
    parts: list[str] = []
    if validation.drifted_characters:
        parts.append(
            f"Nhân vật lệch giọng: {', '.join(validation.drifted_characters)}. Phải giữ giọng đặc trưng."
        )
    for name, tics in validation.missing_tics.items():
        parts.append(f"{name} phải dùng: {', '.join(tics)}")
    for name, tone in validation.tone_mismatches.items():
        parts.append(f"{name}: {tone}")
    return "\n".join(f"- {p}" for p in parts)


def aggregate_voice_stats(validations: list[VoiceValidation], llm_calls_saved: int = 0) -> dict:
    """Aggregate per-chapter voice validations into analytics payload."""
    total = len(validations)
    if total == 0:
        return {"total_chapters": 0, "l2_llm_calls_saved": llm_calls_saved}
    passed_first = sum(1 for v in validations if v.passed and not v.retry_attempted)
    passed_retry = sum(1 for v in validations if v.passed and v.retry_attempted)
    failed = sum(1 for v in validations if not v.passed)
    avg_compliance = sum(v.overall_compliance for v in validations) / total
    drifted_total = sum(len(v.drifted_characters) for v in validations)
    binary_reverts = sum(1 for v in validations if v.binary_reverted)
    return {
        "total_chapters": total,
        "passed_first_try": passed_first,
        "passed_after_retry": passed_retry,
        "failed_after_retry": failed,
        "avg_compliance": round(avg_compliance, 3),
        "chars_drifted_total": drifted_total,
        "binary_reverts": binary_reverts,
        "l2_llm_calls_saved": llm_calls_saved,
    }


def aggregate_contract_stats(validations: list[ContractValidation]) -> dict:
    """Aggregate per-chapter validations into analytics payload."""
    total = len(validations)
    if total == 0:
        return {"total_chapters": 0}
    passed_first = sum(1 for v in validations if v.passed and not v.retry_attempted)
    passed_retry = sum(1 for v in validations if v.passed and v.retry_attempted)
    failed = sum(1 for v in validations if not v.passed)
    avg_compliance = sum(v.compliance_score for v in validations) / total
    avg_delta = sum(v.drama_delta for v in validations) / total
    return {
        "total_chapters": total,
        "passed_first_try": passed_first,
        "passed_after_retry": passed_retry,
        "failed_after_retry": failed,
        "avg_compliance": round(avg_compliance, 3),
        "avg_drama_delta": round(avg_delta, 3),
    }
