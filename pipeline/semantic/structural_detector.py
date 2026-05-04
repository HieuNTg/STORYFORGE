"""NER + embedding-based structural issue detector (Sprint 2, P4).

Replaces the keyword/substring `StructuralIssueDetector` class in
`pipeline/layer2_enhance/structural_detector.py` with deterministic
local-model checks.

Algorithm per chapter:
1. MISSING_CHARACTER — NER (xx_ent_wiki_sm) extracts PERSON entities from
   chapter content; canonical-name substring fallback (word-boundary `\b`)
   for names the small model misses. Any character in
   `contract.must_mention_characters` not found → critical finding.
2. DROPPED_THREAD — embed each `contract.threads_advance` label + the
   chapter sentence spans; max cosine similarity below threshold (default
   0.50, D4) → dropped-thread finding.
3. DANGLING_REFERENCE — NER yields a PERSON name not in the cast AND not
   mentioned in any thread label → dangling reference finding (medium
   severity, not critical).

Strict mode (STORYFORGE_SEMANTIC_STRICT=1): any critical finding raises
`SemanticVerificationError` from `pipeline.semantic`.

Tradeoffs (D2):
- xx_ent_wiki_sm is ~12 MB, weak on Vietnamese. Substring fallback carries
  most of the Vietnamese character detection load.
- Word-boundary regex `\b` prevents "Long" matching "Long-form" but may
  miss tonal diacritics; canonical names with full diacritics are compared
  case-insensitively via `casefold()`.

No caching for NER (fast on CPU, inputs unique per chapter).
Embedding calls are batched per chapter (one embed_batch call for spans,
one for thread labels — two total per chapter).
"""

from __future__ import annotations

import logging
import re
import unicodedata

from models.semantic_schemas import StructuralFinding, StructuralFindingType
from pipeline.semantic import SemanticVerificationError, is_strict_mode
from services.embedding_service import get_embedding_service, bytes_to_vec
from services.ner_service import get_ner_service

import numpy as np

logger = logging.getLogger(__name__)

# Default similarity threshold for thread coverage (D4)
_DEFAULT_THREAD_THRESHOLD = 0.50

# Severity levels
_SEVERITY_CRITICAL = 0.90   # must-mention character missing
_SEVERITY_HIGH = 0.75       # dropped thread
_SEVERITY_MEDIUM = 0.55     # dangling reference


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

_SENT_RE = re.compile(r"[^.!?…。！？]+[.!?…。！？]?")
_MIN_SPAN_CHARS = 10


def _split_spans(text: str) -> list[str]:
    """Split text into sentence-level spans (shared with foreshadowing_verifier)."""
    seen: set[str] = set()
    spans: list[str] = []
    for m in _SENT_RE.finditer(text):
        span = m.group(0).strip()
        if len(span) >= _MIN_SPAN_CHARS and span not in seen:
            seen.add(span)
            spans.append(span)
    return spans


def _canonical_names(characters: list) -> list[str]:
    """Extract canonical name strings from a list of Character objects or strings."""
    result: list[str] = []
    for c in characters:
        if isinstance(c, str):
            result.append(unicodedata.normalize("NFC", c).strip())
        else:
            name = getattr(c, "name", None) or ""
            result.append(unicodedata.normalize("NFC", name).strip())
    return [n for n in result if n]


def _name_in_content(name: str, content: str) -> bool:
    """Word-boundary substring match for canonical name.

    Requires the name to be surrounded by non-word characters (spaces,
    punctuation) and NOT followed by a hyphen-plus-word-char (to exclude
    hyphenated compound tokens like "Long-form").

    Vietnamese diacritics are handled via IGNORECASE + UNICODE flags.
    """
    if not name or not content:
        return False
    escaped = re.escape(name)
    # (?<!\w) — not preceded by a word char
    # (?![-\w]) — not followed by hyphen or word char (blocks "Long-form")
    pattern = r"(?<!\w)" + escaped + r"(?![-\w])"
    try:
        return bool(re.search(pattern, content, re.IGNORECASE | re.UNICODE))
    except re.error:
        return name.casefold() in content.casefold()


def _cosine(a_bytes: bytes, b_bytes: bytes) -> float:
    a = bytes_to_vec(a_bytes)
    b = bytes_to_vec(b_bytes)
    return float(np.dot(a, b))


# ---------------------------------------------------------------------------
# Check functions
# ---------------------------------------------------------------------------


def _check_missing_characters(
    content: str,
    ch_num: int,
    must_mention: list[str],
    ner_persons: set[str],
) -> list[StructuralFinding]:
    """Detect must-mention characters absent from chapter content.

    Detection method: NER first; if a character's canonical name is not
    covered by any NER entity, fall back to word-boundary substring match
    (allowed for identifiers per D2).
    """
    findings: list[StructuralFinding] = []
    for name in must_mention:
        # Check NER result — any entity that matches the canonical name
        ner_hit = any(
            name.casefold() in ent.casefold() or ent.casefold() in name.casefold()
            for ent in ner_persons
        )
        if ner_hit:
            continue

        # Substring fallback (word-boundary)
        if _name_in_content(name, content):
            method = "ner_fallback_substring"
            # Found via substring; no finding
            continue

        # Character is genuinely missing
        detection_method = "ner" if ner_persons or get_ner_service().is_available() else "ner_fallback_substring"
        findings.append(
            StructuralFinding(
                finding_type=StructuralFindingType.MISSING_CHARACTER,
                chapter_num=ch_num,
                severity=_SEVERITY_CRITICAL,
                description=f"Required character '{name}' not found in chapter",
                fix_hint=f"Include character '{name}' in the chapter narrative",
                detection_method=detection_method,
                evidence=tuple(ner_persons),
                confidence=1.0,  # Absence is certain
            )
        )
    return findings


def _check_dropped_threads(
    content: str,
    ch_num: int,
    threads_advance: list[str],
    threshold: float,
    svc,
) -> list[StructuralFinding]:
    """Detect threads that should advance but have no embedding match in chapter.

    One embed_batch call for all thread labels + all spans.
    """
    if not threads_advance:
        return []

    spans = _split_spans(content)
    if not spans:
        # Empty chapter: all threads are dropped
        return [
            StructuralFinding(
                finding_type=StructuralFindingType.MISSING_KEY_EVENT,
                chapter_num=ch_num,
                severity=_SEVERITY_HIGH,
                description=f"Thread '{t}' not advanced (empty chapter)",
                fix_hint=f"Write content advancing thread: {t}",
                detection_method="embedding",
                evidence=(),
                confidence=1.0,
            )
            for t in threads_advance
        ]

    if not svc.is_available():
        # No embedder — skip thread checks (warn once at call site)
        return []

    # Batch embed: thread labels first, then spans
    all_texts = threads_advance + spans
    all_bytes = svc.embed_batch(all_texts)
    thread_vecs = all_bytes[: len(threads_advance)]
    span_vecs = all_bytes[len(threads_advance):]

    findings: list[StructuralFinding] = []
    for thread_label, t_vec in zip(threads_advance, thread_vecs):
        max_sim = max((_cosine(t_vec, s_vec) for s_vec in span_vecs), default=0.0)
        if max_sim < threshold:
            confidence = round(1.0 - max_sim, 4)
            findings.append(
                StructuralFinding(
                    finding_type=StructuralFindingType.MISSING_KEY_EVENT,
                    chapter_num=ch_num,
                    severity=_SEVERITY_HIGH,
                    description=f"Thread '{thread_label}' not advanced (max_sim={max_sim:.3f} < {threshold})",
                    fix_hint=f"Include content advancing thread: {thread_label}",
                    detection_method="embedding",
                    evidence=(),
                    confidence=confidence,
                )
            )
    return findings


def _check_dangling_references(
    ch_num: int,
    ner_persons: set[str],
    all_cast_names: list[str],
    thread_labels: list[str],
) -> list[StructuralFinding]:
    """Flag PERSON entities not in the cast list and not mentioned in any thread.

    Only fires when NER is available (requires PERSON detection).
    """
    if not ner_persons:
        return []

    # Build a casefold lookup for cast names and thread text
    cast_cf = {n.casefold() for n in all_cast_names if n}
    thread_cf = " ".join(thread_labels).casefold()

    findings: list[StructuralFinding] = []
    for ent in ner_persons:
        ent_cf = ent.casefold()
        # In cast?
        if any(ent_cf in cn or cn in ent_cf for cn in cast_cf):
            continue
        # In any thread label?
        if ent_cf in thread_cf:
            continue
        findings.append(
            StructuralFinding(
                finding_type=StructuralFindingType.MISSING_CHARACTER,
                chapter_num=ch_num,
                severity=_SEVERITY_MEDIUM,
                description=f"Dangling character reference '{ent}' not in cast or threads",
                fix_hint=f"Either add '{ent}' to the cast or remove the reference",
                detection_method="ner",
                evidence=(ent,),
                confidence=0.8,
            )
        )
    return findings


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def detect_structural_issues(
    chapter,
    contract,
    characters: list,
    thread_threshold: float = _DEFAULT_THREAD_THRESHOLD,
) -> list[StructuralFinding]:
    """Detect structural issues in *chapter* given *contract* and *characters*.

    Args:
        chapter: Object with `.chapter_number` (int) and `.content` (str).
        contract: `NegotiatedChapterContract` with `.must_mention_characters`
            (list[str]) and `.threads_advance` (list[str]).
        characters: List of `Character` objects (or strings). Used to build
            the cast for dangling-reference detection.
        thread_threshold: Cosine similarity threshold below which a thread
            is considered dropped (default 0.50, D4).

    Returns:
        List of `StructuralFinding`. Empty list = no issues detected.

    Side effects (strict mode):
        Raises `SemanticVerificationError` if any critical finding is present
        and `STORYFORGE_SEMANTIC_STRICT=1`.
    """
    ch_num: int = getattr(chapter, "chapter_number", 0) or 0
    content: str = getattr(chapter, "content", "") or ""

    must_mention: list[str] = list(getattr(contract, "must_mention_characters", []) or [])
    threads_advance: list[str] = list(getattr(contract, "threads_advance", []) or [])

    cast_names = _canonical_names(characters)
    ner_svc = get_ner_service()
    emb_svc = get_embedding_service()

    # -- NER pass (once per chapter) ----------------------------------------
    ner_persons: set[str] = set()
    if ner_svc.is_available():
        ner_persons = ner_svc.extract_persons(content)
    else:
        logger.warning(
            "NER unavailable for ch=%d; falling back to canonical-name substring only.",
            ch_num,
        )

    # -- Checks -------------------------------------------------------------
    findings: list[StructuralFinding] = []

    if must_mention:
        findings.extend(
            _check_missing_characters(content, ch_num, must_mention, ner_persons)
        )

    if threads_advance:
        if not emb_svc.is_available():
            logger.warning(
                "Embedding service unavailable — skipping thread-coverage check for ch=%d.",
                ch_num,
            )
        else:
            findings.extend(
                _check_dropped_threads(
                    content, ch_num, threads_advance, thread_threshold, emb_svc
                )
            )

    # Dangling references only if NER fired (otherwise we have no entity list)
    if ner_svc.is_available():
        all_names = cast_names + must_mention
        findings.extend(
            _check_dangling_references(ch_num, ner_persons, all_names, threads_advance)
        )

    # -- Strict-mode gate ---------------------------------------------------
    if is_strict_mode():
        critical = [f for f in findings if f.severity >= 0.80]
        if critical:
            descs = "; ".join(f.description for f in critical)
            raise SemanticVerificationError(
                f"Structural critical findings in ch={ch_num}: {descs}",
                critical_findings=critical,
            )

    # -- Log ----------------------------------------------------------------
    for f in findings:
        logger.warning(
            "semantic_structural_issue ch=%d type=%s severity=%.2f description=%s",
            ch_num, f.finding_type.value, f.severity, f.description,
        )

    n_critical = sum(1 for f in findings if f.severity >= 0.80)
    n_major = sum(1 for f in findings if 0.60 <= f.severity < 0.80)
    n_minor = sum(1 for f in findings if f.severity < 0.60)
    ch_label = f"ch_{ch_num:02d}"
    logger.info(
        "structural_findings critical=%d major=%d minor=%d chapter=%s",
        n_critical, n_major, n_minor, ch_label,
    )

    return findings


__all__ = ["detect_structural_issues"]
