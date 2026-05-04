"""10-chapter pipeline timing benchmark for Sprint 2 (P7).

Sprint 2 semantic verification (foreshadowing_verifier, structural_detector,
outline_metrics) is mandatory in the pipeline — there is no "baseline / no
Sprint-2" toggle to compare against. Instead this benchmark measures the
cold-cache vs warm-cache cost of the embedding-driven verification path
across a 10-chapter scenario.

Why this is the right comparison:
  - The cache hit-rate determines the marginal cost of running Sprint 2
    on every story. If warm-cache time is dominated by non-embedding work,
    the per-chapter overhead of the new semantic checks is bounded.
  - First-pass / cold-cache time is a worst-case upper bound that surfaces
    if the model load or initial embedding batch ever becomes a regression
    (e.g. someone disables L2 normalisation, doubling embedding cost).

Assertion: warm-cache total time ≤ 1.20 × cold-cache total time per chapter.
That is, cache lookups must dominate over re-encoding when content repeats.
In practice we expect warm-cache to be ≪ cold-cache because every span is
served from the SQLite cache.

Marked `@pytest.mark.perf` so it is excluded from the unit suite:
    pytest -m "not perf"          # fast unit tests
    pytest -m perf -s             # this benchmark only

Skips gracefully when sentence-transformers / model is unavailable.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from models.handoff_schemas import ForeshadowingSeed
from models.schemas import Chapter
from pipeline.semantic.foreshadowing_verifier import verify_payoffs
from services.embedding_cache import (
    EmbeddingCache,
    reset_embedding_cache,
)
from services.embedding_service import (
    get_embedding_service,
    reset_embedding_service,
)


# ---------------------------------------------------------------------------
# Fixtures: 10-chapter Vietnamese scenario
# ---------------------------------------------------------------------------


_VI_CHAPTER_TEMPLATES = [
    "Long bước vào hang động và tìm thấy thanh kiếm tổ tiên giấu sâu trong vách đá.",
    "Mai phát hiện ra rằng người yêu cũ đã lừa dối cô suốt nhiều năm qua trong im lặng.",
    "Sư phụ truyền lại bí kíp kiếm pháp tối thượng cho đệ tử trong đêm mưa lạnh giá.",
    "Hà đành thanh lý căn nhà nhỏ của gia đình để trả khoản nợ cho cha mình.",
    "Hắc Long Vương thức tỉnh sau ngàn năm ngủ vùi dưới đáy đại dương sâu thẳm.",
    "Hùng từ chối lời mời làm việc tại Sài Gòn để ở lại quê nhà chăm sóc mẹ.",
    "Tiểu Vũ thành công luyện thành Kim Đan, bước sang một tầng tu vi mới hoàn toàn.",
    "Linh kết hôn với người mình không yêu vì áp lực gia đình quá nặng nề.",
    "Cuối cùng người ta cũng biết được nguồn gốc thực sự của Phong sau bao năm.",
    "Trong cuộc đại chiến với ma chúa, bảo kiếm vỡ thành hai mảnh giữa trận tiền.",
]

_VI_ANCHORS = [
    "Long phát hiện thanh kiếm tổ tiên giấu trong động",
    "Mai nhận ra Tuấn đã lừa dối mình",
    "Sư phụ truyền lại bí kíp kiếm pháp",
    "Hà phải bán nhà để trả nợ cho cha",
    "Hắc Long Vương trỗi dậy từ đáy biển",
    "Hùng từ chối công việc ở Sài Gòn",
    "Tiểu Vũ đột phá lên cảnh giới Kim Đan",
    "Linh kết hôn vì áp lực gia đình",
    "Bí mật về thân thế của Phong được hé lộ",
    "Thanh kiếm gãy đôi trong trận chiến ma vương",
]


def _make_seed(idx: int) -> ForeshadowingSeed:
    return ForeshadowingSeed(
        id=f"perf-{idx:02d}",
        plant_chapter=idx,
        payoff_chapter=idx,
        description=_VI_ANCHORS[idx - 1],
        semantic_anchor=_VI_ANCHORS[idx - 1],
    )


def _make_chapter(idx: int) -> Chapter:
    body = _VI_CHAPTER_TEMPLATES[idx - 1]
    # Repeat the body a few times so the chapter has multiple span candidates,
    # mirroring real Vietnamese chapters with multiple paragraphs.
    content = ". ".join([body] * 4) + "."
    return Chapter(
        chapter_number=idx,
        title=f"Chương {idx}",
        content=content,
        word_count=len(content.split()),
    )


@pytest.fixture(scope="module")
def real_embedder():
    """Load the real embedder once for the module. Skip if unavailable."""
    reset_embedding_service()
    svc = get_embedding_service()
    if not svc.is_available():
        pytest.skip("Embedding model unavailable — install sentence-transformers.")
    return svc


@pytest.fixture
def fresh_cache(tmp_path: Path, real_embedder):
    """Attach a fresh SQLite cache for each run, so cold-cache measurements
    are not polluted by previous tests' entries."""
    db_file = tmp_path / "perf_cache.db"
    reset_embedding_cache()
    cache = EmbeddingCache(db_path=str(db_file))
    real_embedder.attach_cache(cache)
    yield cache
    reset_embedding_cache()


# ---------------------------------------------------------------------------
# Benchmark
# ---------------------------------------------------------------------------


@pytest.mark.perf
def test_sprint2_10ch_cold_vs_warm_cache(fresh_cache, real_embedder, monkeypatch, capsys):
    """Cold-cache vs warm-cache run over 10 Vietnamese chapters.

    Asserts: warm-cache time per chapter ≤ 1.20 × cold-cache time per chapter
    is the SLA we don't expect to hit (warm should be far faster) — we use
    1.20× as a safety upper bound that catches catastrophic cache regressions.
    """
    monkeypatch.delenv("STORYFORGE_SEMANTIC_STRICT", raising=False)
    monkeypatch.delenv("STORYFORGE_HANDOFF_STRICT", raising=False)

    seeds = [_make_seed(i) for i in range(1, 11)]
    chapters = [_make_chapter(i) for i in range(1, 11)]

    # ---- Cold-cache run ----------------------------------------------------
    t0 = time.perf_counter()
    cold_results = verify_payoffs(seeds, chapters, threshold=0.62)
    cold_seconds = time.perf_counter() - t0
    cold_per_chapter = cold_seconds / len(chapters)

    cache_stats_after_cold = fresh_cache.stats()

    # ---- Warm-cache run ----------------------------------------------------
    # Same seeds + chapters → every embed call is a cache hit.
    t1 = time.perf_counter()
    warm_results = verify_payoffs(seeds, chapters, threshold=0.62)
    warm_seconds = time.perf_counter() - t1
    warm_per_chapter = warm_seconds / len(chapters)

    cache_stats_after_warm = fresh_cache.stats()

    # ---- Sanity checks -----------------------------------------------------
    assert len(cold_results) == 10
    assert len(warm_results) == 10
    # Confidence values should be deterministic across runs (same model, same input)
    cold_conf = sorted((r.seed_id, round(r.confidence, 3)) for r in cold_results)
    warm_conf = sorted((r.seed_id, round(r.confidence, 3)) for r in warm_results)
    assert cold_conf == warm_conf, (
        f"Non-deterministic results: cold={cold_conf} warm={warm_conf}"
    )

    # ---- Performance assertion --------------------------------------------
    # Warm should be at most 1.20× cold; in practice we expect ≤ 0.50× because
    # warm-cache run avoids the SentenceTransformer.encode pass entirely.
    ratio = warm_seconds / max(cold_seconds, 1e-9)

    # ---- Print report ------------------------------------------------------
    print("\n=== Sprint 2 P7 — 10-chapter perf bench ===")
    print(f"Model: {real_embedder.model_id}")
    print(f"Chapters: {len(chapters)}")
    print(
        f"Cold-cache total: {cold_seconds:.3f}s "
        f"({cold_per_chapter*1000:.1f} ms/chapter)"
    )
    print(
        f"Warm-cache total: {warm_seconds:.3f}s "
        f"({warm_per_chapter*1000:.1f} ms/chapter)"
    )
    print(f"Warm/cold ratio: {ratio:.3f} (assert ≤ 1.20)")
    print(f"Cache after cold: {cache_stats_after_cold['total_entries']} entries")
    print(f"Cache after warm: {cache_stats_after_warm['total_entries']} entries")

    # The cache must have been populated by the cold run
    assert cache_stats_after_cold["total_entries"] > 0
    # And the warm run must NOT have grown the cache (everything was a hit)
    assert (
        cache_stats_after_warm["total_entries"]
        == cache_stats_after_cold["total_entries"]
    ), "Warm-cache run inserted new entries; cache lookups are not all hitting."

    assert ratio <= 1.20, (
        f"Warm-cache regression: warm/cold={ratio:.3f}× exceeds 1.20× SLA. "
        f"Cold={cold_seconds:.3f}s, Warm={warm_seconds:.3f}s."
    )
