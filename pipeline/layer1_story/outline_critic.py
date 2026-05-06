"""Critique-revise loop for chapter outlines after initial generation.

P5 refactor: primary scoring is now the deterministic ObjectiveMetrics from
`outline_metrics.py`. The LLM critique is kept as a *secondary* signal only:
  - logged + persisted in the returned OutlineCritique
  - does NOT drive `should_rewrite` unless `enable_llm_outline_critic=True`
    AND `overall_score` is already at or below the rewrite threshold

`should_rewrite` is True when:
  composite_score < COMPOSITE_REWRITE_THRESHOLD (0.60)
  OR any single metric is below its individual floor (see METRIC_FLOORS below).

Pre-P5 callers that call `critique_and_revise(...)` continue to work.
The return type changed: now returns (outlines, OutlineCritique-dict) but the
dict is backward-compatible — it still has `overall_score` (now the composite
float), plus new keys: `metrics`, `llm_signal`, `composite_score`,
`should_rewrite`.
"""

from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass
from typing import Optional, TYPE_CHECKING

from models.schemas import Character, ChapterOutline, ConflictEntry, ForeshadowingEntry, WorldSetting
from models.semantic_schemas import OutlineMetrics
from pipeline.layer1_story.outline_metrics import OUTLINE_METRIC_FLOORS

if TYPE_CHECKING:
    from services.llm_client import LLMClient

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

COMPOSITE_REWRITE_THRESHOLD: float = 0.60
"""Composite score below this → should_rewrite=True."""

PROPER_NOUN_COVERAGE_FLOOR: float = 0.60
"""Outline must cover ≥ 60% of proper nouns from the user's idea (literal mode)."""

# Common Vietnamese sentence-starters / generic words that pass capitalization heuristics
# but are NOT proper nouns. Keep tight — false positives are cheaper than false negatives here.
_PROPER_NOUN_STOPWORDS: frozenset[str] = frozenset({
    "Tôi", "Bạn", "Anh", "Chị", "Em", "Họ", "Nó", "Nhưng", "Và", "Hoặc",
    "Khi", "Nếu", "Vì", "Để", "Sau", "Trước", "Trong", "Ngoài", "Với",
    "Một", "Hai", "Ba", "Bốn", "Năm", "Sáu", "Bảy", "Tám", "Chín", "Mười",
    "Câu", "Chương", "Phần", "Tập", "Truyện", "Cốt", "Câu chuyện",
    "Có", "Là", "Sẽ", "Đã", "Đang", "Không", "Cũng", "Chỉ", "Còn",
    "Tuy", "Mặc", "Vẫn", "Lại", "Theo", "Bởi", "Bằng",
})


def _extract_proper_nouns(text: str) -> set[str]:
    """Heuristic proper-noun extraction for Vietnamese / transliterated Chinese names.

    Captures sequences of 1–4 tokens where each token's first character is
    Unicode-uppercase (covers Vietnamese diacritics: Lý, Tô, Đường, etc.).
    Filters generic stopwords. Token boundary is whitespace; punctuation is stripped.
    """
    if not text:
        return set()

    _SENT_END = ".!?;:\n…"
    _STRIP_CHARS = ".,;:!?\"'()[]{}<>«»“”‘’—…"

    raw_tokens = re.split(r"\s+", text)
    # Each tokens[i] = (cleaned_word, breaks_run) — breaks_run=True if the original
    # token ended in sentence-terminating punctuation.
    tokens: list[tuple[str, bool]] = []
    for t in raw_tokens:
        if not t:
            continue
        breaks = bool(t) and t[-1] in _SENT_END
        cleaned = t.strip(_STRIP_CHARS)
        tokens.append((cleaned, breaks))

    def _is_proper(tok: str) -> bool:
        return bool(tok) and tok[0].isupper() and tok not in _PROPER_NOUN_STOPWORDS

    nouns: set[str] = set()
    i = 0
    n = len(tokens)
    while i < n:
        word, breaks = tokens[i]
        if _is_proper(word):
            j = i + 1
            # Stop the run at sentence boundary on the CURRENT token
            if not breaks:
                while j < n and j - i < 4:
                    nxt_word, nxt_breaks = tokens[j]
                    if not _is_proper(nxt_word):
                        break
                    j += 1
                    if nxt_breaks:
                        break
            phrase = " ".join(tokens[k][0] for k in range(i, j))
            if phrase and phrase not in _PROPER_NOUN_STOPWORDS:
                nouns.add(phrase)
            i = j
        else:
            i += 1
    return nouns


def proper_noun_fidelity_check(
    idea: str,
    outlines: list[ChapterOutline],
) -> tuple[float, list[str]]:
    """Check what fraction of idea's proper nouns appear in outline summaries+titles.

    Returns (coverage_ratio, missing_nouns). coverage_ratio in [0.0, 1.0].
    If idea has no detectable proper nouns, returns (1.0, []) — nothing to enforce.
    """
    idea_nouns = _extract_proper_nouns(idea)
    if not idea_nouns:
        return 1.0, []

    haystack = "\n".join(
        f"{o.title} {o.summary} {' '.join(o.characters_involved)}"
        for o in outlines
    )
    missing = [n for n in idea_nouns if n not in haystack]
    coverage = 1.0 - (len(missing) / len(idea_nouns))
    return coverage, missing

STRICT_RAISE_THRESHOLD: float = 0.50
"""STORYFORGE_SEMANTIC_STRICT=1 + composite < this → raise SemanticVerificationError."""

# Canonical definition lives in pipeline.layer1_story.outline_metrics.OUTLINE_METRIC_FLOORS.
# METRIC_FLOORS is kept as a module-level alias so existing callers of
# outline_critic.METRIC_FLOORS continue to work without modification.
METRIC_FLOORS: dict[str, float] = OUTLINE_METRIC_FLOORS
"""Per-metric floors. Failing any floor also triggers should_rewrite=True.

Alias for ``pipeline.layer1_story.outline_metrics.OUTLINE_METRIC_FLOORS``.
"""

# Legacy threshold kept for backward compat (LLM score 1-5; not used for decisions)
REVISION_THRESHOLD = 4

# ---------------------------------------------------------------------------
# Prompt templates (unchanged)
# ---------------------------------------------------------------------------

CRITIQUE_OUTLINE = """Bạn là biên tập viên kịch bản. Phân tích dàn ý và chỉ ra vấn đề.
Thể loại: {genre} | Tóm tắt: {synopsis}
Nhân vật: {characters}
Bối cảnh: {world}
Dàn ý: {outlines}

Đánh giá: plot_holes (lỗ hổng logic), pacing_issues (nhịp điệu sai, vd 3 climax liên tiếp), character_underuse (nhân vật biến mất quá lâu), arc_coherence (arc không tự nhiên), foreshadowing_gaps (seed không payoff hoặc ngược lại), overall_score 1-5.
BẮT BUỘC tiếng Việt. Trả về JSON:
{{"plot_holes":[],"pacing_issues":[],"character_underuse":[],"arc_coherence":[],"foreshadowing_gaps":[],"overall_score":3}}"""

REVISE_OUTLINE = """Bạn là biên kịch tài năng. Sửa dàn ý dựa trên phản hồi biên tập.
Thể loại: {genre} | Nhân vật: {characters} | Bối cảnh: {world}
Dàn ý gốc: {outlines}
Phản hồi: lỗ hổng=[{plot_holes}] nhịp điệu=[{pacing_issues}] nhân vật lãng quên=[{character_underuse}] arc=[{arc_coherence}] foreshadowing=[{foreshadowing_gaps}]

Yêu cầu: giữ nguyên số chương, chỉ sửa phần có vấn đề. Đảm bảo setup→rising→climax→cooldown xen kẽ. Bổ sung seed/payoff còn thiếu. Lấp lỗ hổng logic.
BẮT BUỘC tiếng Việt. Tên nhân vật PHẢI dùng CHÍNH XÁC như trên.
Trả về JSON:
{{"outlines":[{{"chapter_number":1,"title":"","summary":"","key_events":[],"characters_involved":[],"emotional_arc":"","pacing_type":"rising","arc_id":1,"foreshadowing_plants":[],"payoff_references":[]}}]}}"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _format_outlines_for_prompt(outlines: list[ChapterOutline]) -> str:
    lines = []
    for o in outlines:
        lines.append(
            f"Chương {o.chapter_number} [{o.pacing_type}] '{o.title}': {o.summary} "
            f"| Nhân vật: {', '.join(o.characters_involved)} "
            f"| Arc ID: {o.arc_id}"
        )
    return "\n".join(lines)


def _format_critique_field(items) -> str:
    if not items:
        return "Không có"
    if isinstance(items, list):
        return "; ".join(str(i) for i in items)
    return str(items)


# ---------------------------------------------------------------------------
# LLM critic (unchanged logic; demoted to secondary signal)
# ---------------------------------------------------------------------------


def critique_outline(
    llm: "LLMClient",
    outlines: list[ChapterOutline],
    characters: list[Character],
    world: WorldSetting,
    synopsis: str,
    genre: str,
    model: Optional[str] = None,
) -> dict:
    """Call LLM to critique the outline. Returns critique dict. Non-fatal.

    NOTE (P5): This is a *secondary* signal. Callers should use
    `score_outline` or `critique_and_revise` instead; those routes gate the
    LLM call behind `enable_llm_outline_critic` config flag.
    """
    chars_text = "\n".join(
        f"- {c.name} ({c.role}): {c.personality}" for c in characters
    )
    try:
        result = llm.generate_json(
            system_prompt="Bạn là biên tập viên kịch bản chuyên nghiệp. BẮT BUỘC viết bằng tiếng Việt. Trả về JSON.",
            user_prompt=CRITIQUE_OUTLINE.format(
                genre=genre,
                synopsis=synopsis,
                characters=chars_text,
                world=f"{world.name}: {world.description}",
                outlines=_format_outlines_for_prompt(outlines),
            ),
            model=model,
        )
        return result if isinstance(result, dict) else {}
    except Exception as e:
        logger.warning("critique_outline failed (non-fatal): %s", e)
        return {}


def revise_outline_from_critique(
    llm: "LLMClient",
    outlines: list[ChapterOutline],
    critique: dict,
    characters: list[Character],
    world: WorldSetting,
    genre: str,
    threshold: int = REVISION_THRESHOLD,
    model: Optional[str] = None,
) -> list[ChapterOutline]:
    """Revise outlines using LLM critique feedback. Non-fatal.

    NOTE (P5): Decision to call this is now made by `score_outline` based on
    deterministic metrics. The `threshold` param is kept for backward compat
    but is no longer the primary gate.
    """
    score = critique.get("overall_score", threshold)
    try:
        score = int(score)
    except (TypeError, ValueError):
        score = threshold

    if score >= threshold:
        logger.info("Outline score %s >= threshold %s, skipping revision.", score, threshold)
        return outlines

    chars_text = "\n".join(
        f"- {c.name} ({c.role}): {c.personality}" for c in characters
    )
    try:
        result = llm.generate_json(
            system_prompt="Bạn là biên kịch tài năng. BẮT BUỘC viết bằng tiếng Việt. Trả về JSON.",
            user_prompt=REVISE_OUTLINE.format(
                genre=genre,
                characters=chars_text,
                world=f"{world.name}: {world.description}",
                outlines=_format_outlines_for_prompt(outlines),
                plot_holes=_format_critique_field(critique.get("plot_holes", [])),
                pacing_issues=_format_critique_field(critique.get("pacing_issues", [])),
                character_underuse=_format_critique_field(critique.get("character_underuse", [])),
                arc_coherence=_format_critique_field(critique.get("arc_coherence", [])),
                foreshadowing_gaps=_format_critique_field(critique.get("foreshadowing_gaps", [])),
            ),
            temperature=0.85,
            model=model,
        )
        revised = [ChapterOutline(**o) for o in result.get("outlines", [])]
        if not revised:
            logger.warning("revise_outline_from_critique returned empty list, keeping originals.")
            return outlines
        logger.info("Outline revised: %d chapters (score was %s).", len(revised), score)
        return revised
    except Exception as e:
        logger.warning("revise_outline_from_critique failed (non-fatal): %s", e)
        return outlines


# ---------------------------------------------------------------------------
# P5 primary entry point
# ---------------------------------------------------------------------------


def score_outline(
    outlines: list[ChapterOutline],
    characters: list[Character],
    conflict_web: list[ConflictEntry] | None = None,
    foreshadowing_plan: list[ForeshadowingEntry] | None = None,
) -> tuple[OutlineMetrics, bool, list[str]]:
    """Compute deterministic objective metrics and decide should_rewrite.

    Returns:
        (metrics, should_rewrite, failing_reasons)

    No LLM call. Pure.

    Floors (any violation → should_rewrite=True):
        conflict_web_density   >= 0.10
        arc_trajectory_variance >= 0.10
        pacing_distribution_skew >= 0.30
        beat_coverage_ratio    >= 0.50
        screen_time_balance    >= 0.30

    Composite threshold: should_rewrite if overall_score < 0.60.
    Strict mode: if STORYFORGE_SEMANTIC_STRICT=1 AND overall_score < 0.50,
                 raise SemanticVerificationError.
    """
    from pipeline.layer1_story.outline_metrics import compute_outline_metrics

    metrics = compute_outline_metrics(
        outlines=outlines,
        conflict_web=conflict_web or [],
        characters=characters,
        foreshadowing_plan=foreshadowing_plan,
    )

    failing: list[str] = []

    # Floor checks
    if metrics.conflict_web_density < METRIC_FLOORS["conflict_web_density"]:
        failing.append(
            f"conflict_web_density={metrics.conflict_web_density:.3f} "
            f"< floor={METRIC_FLOORS['conflict_web_density']}"
        )
    if metrics.arc_trajectory_variance < METRIC_FLOORS["arc_trajectory_variance"]:
        failing.append(
            f"arc_trajectory_variance={metrics.arc_trajectory_variance:.3f} "
            f"< floor={METRIC_FLOORS['arc_trajectory_variance']}"
        )
    if metrics.pacing_distribution_skew < METRIC_FLOORS["pacing_distribution_skew"]:
        failing.append(
            f"pacing_distribution_skew={metrics.pacing_distribution_skew:.3f} "
            f"< floor={METRIC_FLOORS['pacing_distribution_skew']}"
        )
    if metrics.beat_coverage_ratio < METRIC_FLOORS["beat_coverage_ratio"]:
        failing.append(
            f"beat_coverage_ratio={metrics.beat_coverage_ratio:.3f} "
            f"< floor={METRIC_FLOORS['beat_coverage_ratio']}"
        )
    screen_time_balance = 1.0 - metrics.character_screen_time_gini
    if screen_time_balance < METRIC_FLOORS["character_screen_time_balance"]:
        failing.append(
            f"character_screen_time_balance={screen_time_balance:.3f} "
            f"< floor={METRIC_FLOORS['character_screen_time_balance']}"
        )

    # Composite threshold
    if metrics.overall_score < COMPOSITE_REWRITE_THRESHOLD:
        failing.append(
            f"overall_score={metrics.overall_score:.3f} "
            f"< threshold={COMPOSITE_REWRITE_THRESHOLD}"
        )

    should_rewrite = bool(failing)

    # Strict mode
    from pipeline.semantic import is_strict_mode
    if is_strict_mode() and metrics.overall_score < STRICT_RAISE_THRESHOLD:
        from pipeline.semantic import SemanticVerificationError
        raise SemanticVerificationError(
            f"Outline composite_score={metrics.overall_score:.3f} "
            f"< strict floor={STRICT_RAISE_THRESHOLD}. Failing: {failing}"
        )

    if failing:
        logger.warning(
            "Outline metrics below threshold: %s",
            "; ".join(failing),
        )
    else:
        logger.info(
            "Outline metrics OK: overall=%.3f", metrics.overall_score
        )

    return metrics, should_rewrite, failing


def critique_and_revise(
    llm: "LLMClient",
    outlines: list[ChapterOutline],
    characters: list[Character],
    world: WorldSetting,
    synopsis: str,
    genre: str,
    max_rounds: int = 1,
    model: Optional[str] = None,
    conflict_web: list[ConflictEntry] | None = None,
    foreshadowing_plan: list[ForeshadowingEntry] | None = None,
    enable_llm_critic: bool = True,
    idea: str = "",
    idea_fidelity_mode: str = "literal",
) -> tuple[list[ChapterOutline], dict]:
    """Primary public API for the outline critique-revise loop.

    P5 behaviour:
    1. Compute deterministic metrics via `score_outline`.
    2. If `enable_llm_critic=True`, also call LLM `critique_outline` as secondary
       signal — its output is logged and returned but does NOT change the
       `should_rewrite` decision.
    3. If should_rewrite, run one LLM revision pass (using the LLM critique as
       guidance if available; otherwise runs a generic revision prompt).
    4. Returns (outlines, critique_dict) where critique_dict is backward-compat
       (still has `overall_score`; now also has `metrics`, `llm_signal`,
       `composite_score`, `should_rewrite`).
    """
    metrics, should_rewrite, failing = score_outline(
        outlines=outlines,
        characters=characters,
        conflict_web=conflict_web,
        foreshadowing_plan=foreshadowing_plan,
    )

    # Secondary signal: LLM critique
    llm_critique: dict = {}
    if enable_llm_critic:
        try:
            llm_critique = critique_outline(
                llm, outlines, characters, world, synopsis, genre, model=model
            )
            logger.info(
                "LLM critique (secondary signal) score=%s",
                llm_critique.get("overall_score", "?"),
            )
        except Exception as e:
            logger.warning("LLM critique secondary signal failed (non-fatal): %s", e)

    # Revision: only if metrics say should_rewrite
    for round_num in range(max_rounds):
        if not should_rewrite:
            break
        logger.info(
            "Round %d: rewriting outline (composite=%.3f, failing=%s)",
            round_num + 1, metrics.overall_score, failing,
        )
        guide_critique = llm_critique if llm_critique else {
            "overall_score": 1,
            "plot_holes": failing,
            "pacing_issues": [],
            "character_underuse": [],
            "arc_coherence": [],
            "foreshadowing_gaps": [],
        }
        outlines = revise_outline_from_critique(
            llm, outlines, guide_critique, characters, world, genre, model=model
        )
        # Re-score after revision
        metrics, should_rewrite, failing = score_outline(
            outlines=outlines,
            characters=characters,
            conflict_web=conflict_web,
            foreshadowing_plan=foreshadowing_plan,
        )

    # Idea fidelity guard: in "literal" mode, force one extra re-roll if proper-noun
    # coverage in outline is below floor. Runs AFTER the metric-driven loop so a
    # single re-roll budget is preserved per outline.
    fidelity_coverage: float = 1.0
    fidelity_missing: list[str] = []
    if idea and idea_fidelity_mode == "literal":
        fidelity_coverage, fidelity_missing = proper_noun_fidelity_check(idea, outlines)
        if fidelity_coverage < PROPER_NOUN_COVERAGE_FLOOR:
            logger.warning(
                "Outline fidelity FAIL: %.0f%% proper-noun coverage (floor=%.0f%%); missing=%s. Re-rolling once.",
                fidelity_coverage * 100, PROPER_NOUN_COVERAGE_FLOOR * 100, fidelity_missing,
            )
            fidelity_critique = {
                "overall_score": 1,
                "plot_holes": [
                    f"Dàn ý KHÔNG dùng các tên riêng từ ý tưởng gốc của tác giả: {', '.join(fidelity_missing)}. "
                    f"BẮT BUỘC đưa các tên này vào outline (tiêu đề, tóm tắt, hoặc characters_involved)."
                ],
                "pacing_issues": [],
                "character_underuse": fidelity_missing,
                "arc_coherence": [],
                "foreshadowing_gaps": [],
            }
            outlines = revise_outline_from_critique(
                llm, outlines, fidelity_critique, characters, world, genre, model=model
            )
            # Re-check post-revision (no further re-rolls)
            fidelity_coverage, fidelity_missing = proper_noun_fidelity_check(idea, outlines)
            logger.info(
                "Outline fidelity post-reroll: %.0f%% coverage; still_missing=%s",
                fidelity_coverage * 100, fidelity_missing,
            )

    # Build backward-compat return dict
    result_dict: dict = {
        # Backward compat: callers reading overall_score get composite (0-1)
        # We scale to 1-5 to avoid breaking existing log lines ("score X/5")
        "overall_score": round(metrics.overall_score * 5, 2),
        # P5 additions
        "metrics": metrics.model_dump(),
        "llm_signal": llm_critique or None,
        "composite_score": metrics.overall_score,
        "should_rewrite": should_rewrite,
        "failing_metrics": failing,
        "idea_fidelity_coverage": fidelity_coverage,
        "idea_fidelity_missing": fidelity_missing,
    }
    # Merge in LLM critique fields if available (plot_holes etc.) for diagnostics
    if llm_critique:
        for k in ("plot_holes", "pacing_issues", "character_underuse",
                  "arc_coherence", "foreshadowing_gaps"):
            if k in llm_critique:
                result_dict[k] = llm_critique[k]

    return outlines, result_dict
