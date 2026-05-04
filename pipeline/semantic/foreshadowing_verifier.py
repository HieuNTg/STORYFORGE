"""Embedding-based foreshadowing payoff verifier (Sprint 2, P3).

Replaces the LLM-based `verify_seeds_semantic` / `verify_payoffs_semantic` calls
in `foreshadowing_manager.py` with local cosine-similarity checks.

Algorithm per (seed, chapter) pair:
1. Resolve anchor text: `ForeshadowingSeed.semantic_anchor` if available,
   else `ForeshadowingEntry.hint` for legacy entries.
2. Split chapter into sentence-level spans (simple regex; no spaCy here — P4).
3. Embed all spans in ONE batched call (+ the anchor if not cached).
4. Compute max cosine similarity of anchor vs all spans.
5. Emit `SemanticPayoffMatch`; mutate seed in-place (planted / paid_off +
   planted_confidence).

Strict mode (STORYFORGE_SEMANTIC_STRICT=1): any `missed` payoff raises
`SemanticVerificationError` with the full list.  Default mode: log WARN, continue.

Vietnamese text: NFC-normalisation happens inside `EmbeddingService._load` /
`embed_texts`; we do NOT double-normalise here.  Sentence splitting uses a
regex that handles Vietnamese (.!?…) and CJK (。！？) endings.

Cache observability: a single DEBUG log line per `verify_payoffs` call reports
cache hit/miss/total stats from the embedding service's attached cache backend.
"""

from __future__ import annotations

import hashlib
import logging
import re
from typing import Union

from models.semantic_schemas import SemanticPayoffMatch
from models.handoff_schemas import ForeshadowingSeed
from models.schemas import ForeshadowingEntry
from services.embedding_service import get_embedding_service, bytes_to_vec

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Custom exception (D5 strict mode) — defined in __init__.py, re-exported here
# ---------------------------------------------------------------------------

from pipeline.semantic import SemanticVerificationError, is_strict_mode  # noqa: E402


# ---------------------------------------------------------------------------
# Sentence-span splitting
# ---------------------------------------------------------------------------

# Covers Vietnamese / Latin sentence endings (.!?…) and CJK endings (。！？).
# We keep the delimiter attached so short exclamations stay coherent.
_SENT_RE = re.compile(r"[^.!?…。！？]+[.!?…。！？]?")

_MIN_SPAN_CHARS = 10  # skip noise fragments shorter than this


def _split_spans(text: str) -> list[str]:
    """Split text into sentence-level spans.

    Returns deduplicated, non-empty spans of >= _MIN_SPAN_CHARS characters.
    Order is preserved; duplicates (rare) are dropped to avoid redundant embeds.
    """
    seen: set[str] = set()
    spans: list[str] = []
    for m in _SENT_RE.finditer(text):
        span = m.group(0).strip()
        if len(span) >= _MIN_SPAN_CHARS and span not in seen:
            seen.add(span)
            spans.append(span)
    return spans


# ---------------------------------------------------------------------------
# Seed id / anchor helpers
# ---------------------------------------------------------------------------


def _seed_id(entry: Union[ForeshadowingSeed, ForeshadowingEntry]) -> str:
    """Canonical id: ForeshadowingSeed.id, or sha256(hint) for legacy entries."""
    if isinstance(entry, ForeshadowingSeed):
        return entry.id
    return hashlib.sha256(entry.hint.encode("utf-8")).hexdigest()[:16]


def _anchor_text(entry: Union[ForeshadowingSeed, ForeshadowingEntry]) -> str:
    """Anchor text to embed: semantic_anchor (new) or hint (legacy fallback)."""
    if isinstance(entry, ForeshadowingSeed):
        return entry.semantic_anchor or entry.description
    return entry.hint  # ForeshadowingEntry has no semantic_anchor


# ---------------------------------------------------------------------------
# Core verifier
# ---------------------------------------------------------------------------

_WEAK_FLOOR = 0.5  # sim >= this but below threshold → "weak"


def verify_payoffs(
    seeds: list[Union[ForeshadowingSeed, ForeshadowingEntry]],
    chapters: list,  # list[Chapter | Any with .chapter_number and .content attrs]
    threshold: float = 0.55,
    role: str = "payoff",
) -> list[SemanticPayoffMatch]:
    """Verify foreshadowing payoffs for all (seed, expected_chapter) pairs.

    For each seed, the expected chapter is determined by `payoff_chapter`
    (for ForeshadowingEntry) or `payoff_chapter` on ForeshadowingSeed.
    We scan ONLY the matching chapter (exact chapter number).  This is a
    deliberate choice: scanning all chapters would dilute the signal and
    defeat the purpose of scheduled payoffs.  Document choice: commit msg.

    Mutates each seed in place:
      - seed.paid_off = True  when matched
      - seed.planted_confidence = max_sim (payoff confidence)

    Args:
        seeds: Mixed list of ForeshadowingSeed (new) or ForeshadowingEntry (legacy).
        chapters: Chapter objects with .chapter_number (int) and .content (str).
        threshold: Cosine similarity threshold for `matched` status (default 0.55,
            calibrated against Vietnamese paraphrase pairs — see
            `tests/fixtures/sprint2_vi_calibration.json`; 0.62 yielded only 73%
            accuracy on multilingual MiniLM, 0.55 yields 96.67%).
        role: "seed" or "payoff" — recorded in the match objects.

    Returns:
        List of SemanticPayoffMatch, one per (seed, matching chapter) pair.
        Seeds whose payoff_chapter has no matching chapter in the list are
        omitted (no chapter written yet).

    Raises:
        SemanticVerificationError: if STORYFORGE_SEMANTIC_STRICT=1 and any
            match has status=="missed".
    """
    if not seeds:
        return []

    svc = get_embedding_service()
    use_embedding = svc.is_available()

    # Build chapter lookup: chapter_number -> content
    ch_map: dict[int, str] = {}
    for c in chapters:
        ch_num_raw = getattr(c, "chapter_number", None)
        if ch_num_raw is None:
            ch_num_raw = getattr(c, "num", None)
        if ch_num_raw is None:
            logger.warning(
                "verify_payoffs: chapter object %r has no chapter_number; "
                "skipping to avoid silent key collision on 0",
                getattr(c, "title", repr(c)),
            )
            continue
        ch_map[int(ch_num_raw)] = c.content

    results: list[SemanticPayoffMatch] = []

    for seed in seeds:
        ch_num = seed.payoff_chapter
        content = ch_map.get(ch_num)
        if content is None:
            # Chapter not written yet — skip silently
            continue

        match = _verify_single(seed, ch_num, content, threshold, role, use_embedding, svc)
        results.append(match)

        # Mutate seed in place (ForeshadowingEntry has planted_confidence; ForeshadowingSeed does not)
        prev_conf = getattr(seed, "planted_confidence", None) or 0.0
        new_conf = max(prev_conf, match.confidence)
        if role == "payoff":
            if match.matched:
                seed.paid_off = True
            try:
                seed.planted_confidence = new_conf
            except Exception:
                pass  # ForeshadowingSeed is frozen; confidence not stored on new model
        elif role == "seed":
            if match.matched:
                seed.planted = True
            try:
                seed.planted_confidence = new_conf
            except Exception:
                pass

    # Strict-mode check
    if is_strict_mode():
        missed = [m for m in results if m.status == "missed"]
        if missed:
            ids = ", ".join(m.seed_id for m in missed)
            raise SemanticVerificationError(
                f"Missed foreshadowing payoffs: {ids}",
                missed_payoffs=missed,
            )

    # Warn-and-continue for weak and missed
    for m in results:
        if m.status == "missed":
            logger.warning(
                "semantic_payoff missed seed_id=%s ch=%d confidence=%.3f threshold=%.3f method=%s",
                m.seed_id, m.chapter_num, m.confidence, m.threshold_used, m.method,
            )
        elif m.status == "weak":
            logger.warning(
                "semantic_payoff weak seed_id=%s ch=%d confidence=%.3f threshold=%.3f method=%s",
                m.seed_id, m.chapter_num, m.confidence, m.threshold_used, m.method,
            )

    n_matched = sum(1 for m in results if m.status == "matched")
    n_weak = sum(1 for m in results if m.status == "weak")
    n_missed = sum(1 for m in results if m.status == "missed")
    logger.info(
        "foreshadowing_verified matched=%d weak=%d missed=%d",
        n_matched, n_weak, n_missed,
    )

    return results


def verify_seeds(
    seeds: list[Union[ForeshadowingSeed, ForeshadowingEntry]],
    chapters: list,
    threshold: float = 0.55,
) -> list[SemanticPayoffMatch]:
    """Verify foreshadowing seeds are planted in their scheduled chapter.

    Same algorithm as `verify_payoffs` but checks `plant_chapter` and uses
    a lower default threshold (0.55 per D4 defaults).
    """
    if not seeds:
        return []

    svc = get_embedding_service()
    use_embedding = svc.is_available()

    ch_map: dict[int, str] = {}
    for c in chapters:
        ch_num_raw = getattr(c, "chapter_number", None)
        if ch_num_raw is None:
            ch_num_raw = getattr(c, "num", None)
        if ch_num_raw is None:
            logger.warning(
                "verify_seeds: chapter object %r has no chapter_number; "
                "skipping to avoid silent key collision on 0",
                getattr(c, "title", repr(c)),
            )
            continue
        ch_map[int(ch_num_raw)] = c.content

    results: list[SemanticPayoffMatch] = []

    for seed in seeds:
        ch_num = seed.plant_chapter
        content = ch_map.get(ch_num)
        if content is None:
            continue

        match = _verify_single(seed, ch_num, content, threshold, "seed", use_embedding, svc)
        results.append(match)

        if match.matched:
            seed.planted = True
        prev_conf = getattr(seed, "planted_confidence", None) or 0.0
        try:
            seed.planted_confidence = max(prev_conf, match.confidence)
        except Exception:
            pass  # ForeshadowingSeed is frozen; confidence not stored on new model

    if is_strict_mode():
        missed = [m for m in results if m.status == "missed"]
        if missed:
            ids = ", ".join(m.seed_id for m in missed)
            raise SemanticVerificationError(
                f"Missed foreshadowing seeds: {ids}",
                missed_payoffs=missed,
            )

    for m in results:
        if m.status in ("missed", "weak"):
            logger.warning(
                "semantic_seed %s seed_id=%s ch=%d confidence=%.3f threshold=%.3f",
                m.status, m.seed_id, m.chapter_num, m.confidence, m.threshold_used,
            )

    return results


def _verify_single(
    seed: Union[ForeshadowingSeed, ForeshadowingEntry],
    ch_num: int,
    content: str,
    threshold: float,
    role: str,
    use_embedding: bool,
    svc,
) -> SemanticPayoffMatch:
    """Verify one seed against one chapter's content. Returns a SemanticPayoffMatch.

    Uses embedding similarity when available; falls back to keyword heuristic.
    """
    seed_id = _seed_id(seed)
    anchor = _anchor_text(seed)

    if not use_embedding:
        # Keyword fallback
        return _keyword_match(seed_id, ch_num, role, anchor, content, threshold)

    spans = _split_spans(content)
    if not spans:
        # Empty chapter — treat as missed
        return SemanticPayoffMatch(
            seed_id=seed_id,
            chapter_num=ch_num,
            role=role,
            matched=False,
            confidence=0.0,
            threshold_used=threshold,
            matched_span=None,
            method="embedding",
        )

    # Batch embed all spans + anchor in ONE call
    all_texts = [anchor] + spans
    all_bytes = svc.embed_batch(all_texts)

    anchor_bytes = all_bytes[0]
    span_bytes = all_bytes[1:]

    # Compute max cosine similarity
    max_sim = 0.0
    best_span: str | None = None
    for span, span_b in zip(spans, span_bytes):
        sim = svc.similarity(anchor_bytes, span_b)
        if sim > max_sim:
            max_sim = sim
            best_span = span

    matched = max_sim >= threshold
    matched_span = (best_span[:280] if best_span else None) if matched or max_sim >= _WEAK_FLOOR else None

    # Log cache debug stats (once per call via embed_batch; cache stats from service cache)
    _log_cache_debug(svc, ch_num, len(spans))

    return SemanticPayoffMatch(
        seed_id=seed_id,
        chapter_num=ch_num,
        role=role,
        matched=matched,
        confidence=round(max_sim, 4),
        threshold_used=threshold,
        matched_span=matched_span,
        method="embedding",
    )


def _keyword_match(
    seed_id: str,
    ch_num: int,
    role: str,
    anchor: str,
    content: str,
    threshold: float,
) -> SemanticPayoffMatch:
    """Keyword-based fallback when embedding service is unavailable."""
    words = [w.lower() for w in anchor.split() if len(w) > 3]
    content_lower = content.lower()
    if words:
        ratio = sum(1 for w in words if w in content_lower) / len(words)
    else:
        ratio = 1.0
    matched = ratio >= 0.3  # keyword fallback threshold
    return SemanticPayoffMatch(
        seed_id=seed_id,
        chapter_num=ch_num,
        role=role,
        matched=matched,
        confidence=round(ratio, 4),
        threshold_used=threshold,
        matched_span=None,
        method="keyword_fallback",
    )


# ---------------------------------------------------------------------------
# Cache observability helper
# ---------------------------------------------------------------------------

def _log_cache_debug(svc, ch_num: int, n_spans: int) -> None:
    """Log debug-level cache stats once per chapter verification call.

    Accesses the `_cache` attribute of the service if it has a `stats()` method
    (the real SQLite-backed EmbeddingCache does); no-op otherwise.
    """
    try:
        cache = getattr(svc, "_cache", None)
        if cache is not None and hasattr(cache, "stats"):
            st = cache.stats()
            logger.debug(
                "embedding_cache ch=%d spans=%d backend=%s total_entries=%d",
                ch_num, n_spans,
                st.get("backend", "?"),
                st.get("total_entries", 0),
            )
    except Exception:  # noqa: BLE001 — never fail on observability
        pass


__all__ = [
    "SemanticVerificationError",
    "verify_payoffs",
    "verify_seeds",
]
