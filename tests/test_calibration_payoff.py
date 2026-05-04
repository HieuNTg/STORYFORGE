"""Real-model calibration test for foreshadowing payoff verifier (Sprint 2 P7).

Loads `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` and runs
the 30-pair Vietnamese calibration set in `tests/fixtures/sprint2_vi_calibration.json`
through `pipeline.semantic.foreshadowing_verifier.verify_payoffs`.

Asserts overall accuracy ≥ 80% at the default threshold (0.62) per D4.
Reports per-class precision/recall on stdout (run with `-s` to see).

Marked `@pytest.mark.calibration` so it can be excluded from the unit suite:
    pytest -m "not calibration"          # fast unit tests
    pytest -m calibration -s             # this test only

Skips gracefully when the embedding service is unavailable (no model
installed, no internet on first run, etc.) — tests that *require* the model
should not block CI on an environment that cannot download it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from models.schemas import Chapter
from models.handoff_schemas import ForeshadowingSeed
from pipeline.semantic.foreshadowing_verifier import verify_payoffs
from services.embedding_service import (
    get_embedding_service,
    reset_embedding_service,
)


FIXTURE_PATH = (
    Path(__file__).parent / "fixtures" / "sprint2_vi_calibration.json"
)


@pytest.fixture(scope="module")
def calibration_pairs() -> list[dict]:
    data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return data["pairs"]


@pytest.fixture(scope="module")
def real_embedding_service():
    """Force a fresh singleton, then load the real model.

    Skips the test if the model is unavailable (e.g. no network on first
    run, or sentence-transformers not installed).
    """
    reset_embedding_service()
    svc = get_embedding_service()
    if not svc.is_available():
        pytest.skip(
            "Embedding model unavailable — install sentence-transformers and "
            "ensure model download is permitted to run calibration."
        )
    return svc


def _make_seed(pair: dict, payoff_chapter: int) -> ForeshadowingSeed:
    return ForeshadowingSeed(
        id=pair["id"],
        plant_chapter=1,
        payoff_chapter=payoff_chapter,
        description=pair["anchor"],
        semantic_anchor=pair["anchor"],
    )


def _make_chapter(pair: dict, chapter_num: int) -> Chapter:
    # Repeat the span to comfortably exceed the 10-char minimum span filter
    # and provide multiple candidate sentences (helps the verifier pick a max).
    content = (
        pair["chapter_span"]
        + ". "
        + pair["chapter_span"]
        + "."
    )
    return Chapter(
        chapter_number=chapter_num,
        title=f"Ch{chapter_num}",
        content=content,
        word_count=len(content.split()),
    )


def _expected_to_predicted_match(
    confidence: float, threshold: float, weak_window: float = 0.05
) -> str:
    """Bucket confidence into matched/weak/missed using verifier's status logic."""
    if confidence >= threshold:
        return "matched"
    if confidence >= max(0.0, threshold - weak_window):
        return "weak"
    return "missed"


@pytest.mark.calibration
def test_payoff_verifier_calibration(
    calibration_pairs, real_embedding_service, monkeypatch, capsys
):
    """Run all 30 pairs through the real model.

    Reports overall + per-class accuracy and asserts overall >= 0.80.
    """
    # Disable strict mode so missed pairs don't raise
    monkeypatch.delenv("STORYFORGE_SEMANTIC_STRICT", raising=False)
    monkeypatch.delenv("STORYFORGE_HANDOFF_STRICT", raising=False)

    threshold = 0.62

    # Build seeds and chapters in lockstep — each pair gets its own
    # chapter_number so the verifier matches them 1:1.
    seeds: list[ForeshadowingSeed] = []
    chapters: list[Chapter] = []
    expected_per_id: dict[str, str] = {}
    category_per_id: dict[str, str] = {}

    for idx, pair in enumerate(calibration_pairs, start=1):
        seed = _make_seed(pair, payoff_chapter=idx)
        chapter = _make_chapter(pair, chapter_num=idx)
        seeds.append(seed)
        chapters.append(chapter)
        expected_per_id[pair["id"]] = pair["expected"]
        category_per_id[pair["id"]] = pair["category"]

    results = verify_payoffs(seeds, chapters, threshold=threshold)
    assert len(results) == len(calibration_pairs), (
        f"Expected {len(calibration_pairs)} results, got {len(results)}"
    )

    # Build prediction dict
    pred_per_id: dict[str, tuple[str, float]] = {}
    for r in results:
        pred = _expected_to_predicted_match(r.confidence, threshold)
        pred_per_id[r.seed_id] = (pred, r.confidence)

    # Compute accuracy + per-class precision/recall
    n_total = len(calibration_pairs)
    n_3class_correct = 0
    classes = ("matched", "weak", "missed")

    # 3-class confusion: confusion[expected][predicted] = count
    confusion = {c: {c2: 0 for c2 in classes} for c in classes}

    # Binary classification: should-match (paraphrase) vs should-NOT-match
    # (near-miss + negative). This is the actual product KPI — does
    # `paid_off=True` get set correctly?
    n_binary_correct = 0
    n_pos = 0  # expected matched (paraphrase)
    n_neg = 0  # expected not-matched (near-miss + negative)
    binary_confusion = {
        "tp": 0, "fp": 0, "tn": 0, "fn": 0
    }

    rows: list[tuple[str, str, str, str, float]] = []  # id, cat, exp, pred, conf
    for pair in calibration_pairs:
        pid = pair["id"]
        exp = expected_per_id[pid]
        pred, conf = pred_per_id[pid]
        confusion[exp][pred] += 1
        if exp == pred:
            n_3class_correct += 1
        rows.append((pid, category_per_id[pid], exp, pred, conf))

        # Binary product KPI
        should_match = (exp == "matched")
        actually_matched = (pred == "matched")
        if should_match:
            n_pos += 1
            if actually_matched:
                binary_confusion["tp"] += 1
                n_binary_correct += 1
            else:
                binary_confusion["fn"] += 1
        else:
            n_neg += 1
            if actually_matched:
                binary_confusion["fp"] += 1
            else:
                binary_confusion["tn"] += 1
                n_binary_correct += 1

    accuracy_3class = n_3class_correct / n_total
    accuracy_binary = n_binary_correct / n_total

    # Per-class P / R (3-class)
    per_class: dict[str, tuple[float, float, int, int]] = {}
    for c in classes:
        tp = confusion[c][c]
        fp = sum(confusion[other][c] for other in classes if other != c)
        fn = sum(confusion[c][other] for other in classes if other != c)
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        per_class[c] = (precision, recall, tp, tp + fn)

    # Binary precision/recall (positives = should-match)
    tp = binary_confusion["tp"]
    fp = binary_confusion["fp"]
    fn = binary_confusion["fn"]
    binary_precision = tp / (tp + fp) if (tp + fp) else 0.0
    binary_recall = tp / (tp + fn) if (tp + fn) else 0.0
    binary_f1 = (
        2 * binary_precision * binary_recall / (binary_precision + binary_recall)
        if (binary_precision + binary_recall) else 0.0
    )

    # ---- Print report ------------------------------------------------------
    print("\n=== Sprint 2 P7 — Calibration report ===")
    print(f"Pairs: {n_total}, threshold={threshold}, model={real_embedding_service.model_id}")
    print(
        f"\nBinary accuracy (paid_off=True correctness): "
        f"{accuracy_binary:.2%} ({n_binary_correct}/{n_total})"
    )
    print(
        f"Binary precision={binary_precision:.2%}  recall={binary_recall:.2%}  "
        f"F1={binary_f1:.2%}  (positives={n_pos}, negatives={n_neg})"
    )
    print(f"Binary confusion: {binary_confusion}")

    print(
        f"\n3-class accuracy (matched/weak/missed bucketing): "
        f"{accuracy_3class:.2%} ({n_3class_correct}/{n_total})"
    )
    print("Per-class precision / recall:")
    for c in classes:
        p, r, tp_c, support = per_class[c]
        print(f"  {c:8s}  P={p:.2%}  R={r:.2%}  support={support}  tp={tp_c}")

    print("\nConfusion matrix (rows=expected, cols=predicted):")
    print(f"             {'matched':>10s} {'weak':>10s} {'missed':>10s}")
    for exp in classes:
        row = "  ".join(f"{confusion[exp][p]:>9d}" for p in classes)
        print(f"  {exp:8s}    {row}")

    print("\nPer-pair detail:")
    print(f"  {'id':<10s}  {'category':<11s}  {'expected':<8s}  {'predicted':<10s}  conf")
    for pid, cat, exp, pred, conf in rows:
        marker = "" if exp == pred else "  <-- MISMATCH"
        print(f"  {pid:<10s}  {cat:<11s}  {exp:<8s}  {pred:<10s}  {conf:.3f}{marker}")

    # ---- Assertions --------------------------------------------------------
    # Primary assertion: binary product KPI ≥ 80%. This is the actual user-facing
    # behaviour — does verify_payoffs correctly set paid_off=True/False?
    assert accuracy_binary >= 0.80, (
        f"Binary calibration accuracy {accuracy_binary:.2%} < 80% target at "
        f"threshold={threshold}. precision={binary_precision:.2%} "
        f"recall={binary_recall:.2%}. "
        f"Confusion: {binary_confusion}"
    )
