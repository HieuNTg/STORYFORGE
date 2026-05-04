# ADR 0002 — Semantic Verification (local embeddings + NER)

**Status:** Accepted
**Date:** 2026-05-04
**Sprint:** [Sprint 2 — Semantic Verification](../../plans/260504-1213-semantic-verification/README.md)

## Context

Sprint 1 closed the L1→L2 plumbing seam but the individual checks consuming
that envelope are still keyword-driven. Three sites mask real
story-coherence failures:

1. `pipeline/layer1_story/foreshadowing_manager.py` — `_keyword_check` flags a
   payoff when 30% of seed words appear in a chapter (false positives on
   common words; false negatives on Vietnamese paraphrase). The "semantic"
   variant `verify_payoffs_semantic` calls an LLM per chapter — slow, costly,
   non-deterministic, and silently degrades to the keyword path on any error.
2. `pipeline/layer2_enhance/structural_detector.py` — first-3-word substring
   matching for key events, lowercased name `in` content for character
   presence, and a hardcoded Vietnamese action-words list (`đánh, chạy, la
   hét, nổ, chết, giết, đau`) for climax pacing. All three flag false
   positives on paraphrase and miss synonyms/inflection.
3. `pipeline/layer1_story/outline_critic.py` — outline quality is a single LLM
   self-score (1-5). Non-reproducible, gameable by prompt drift, no objective
   signal.

We need deterministic semantic checks that run on the critical path without
adding LLM calls.

## Decision

Replace the three sites with local sentence-transformer embeddings and spaCy
NER. The LLM critic is retained as an *optional secondary* signal for outline
scoring only.

This ADR captures the model and architecture choices. Per-phase task
breakdown lives in
`plans/260504-1213-semantic-verification/phases.md`.

## Why local embeddings, not LLM-based semantic checks

| Dimension | LLM (current) | Local embeddings (chosen) |
|-----------|---------------|---------------------------|
| **Cost** | API call per chapter × per check (e.g. 50ch × 3 checks = 150 calls) | Zero per call after warm load |
| **Determinism** | Temperature, prompt drift, model rev | Bit-identical given same model + text |
| **Latency** | 1-5 s p95 per call, queued | 5-20 ms per chapter on CPU |
| **Failure mode** | Silent fallback to keyword | Explicit `is_available()` health flag; same fallback but observable |
| **Cacheable** | Effectively no (LLM responses change shape) | Trivially — float32 vector keyed by (model_id, NFC(text)) |
| **CI golden** | Flaky | Reproducible byte-for-byte |

The LLM path solved the "paraphrase blind spot" but introduced four new
problems for one. Embeddings solve paraphrase **and** the four problems.

## Why `paraphrase-multilingual-MiniLM-L12-v2`

`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` — 384-dim,
~120 MB, CPU-feasible.

Tradeoff matrix:

| Model | Dim | Size | Vietnamese STS | CPU latency | Verdict |
|-------|-----|------|----------------|-------------|---------|
| **MiniLM-L12-v2 (chosen)** | 384 | 120 MB | ~0.55 | ~5 ms/sentence | Right band for our inputs |
| mpnet-base-v2 | 768 | 1.1 GB | ~0.61 | ~15 ms/sentence | 3× slower for +0.06 STS — not worth it on 5-30-token payoff hints |
| multilingual-e5-large | 1024 | 2.2 GB | ~0.68 | ~30 ms/sentence | Best quality, but requires `query:`/`passage:` prefix coupling and blows the perf budget |
| LaBSE | 768 | 1.8 GB | ~0.62 | ~18 ms/sentence | Strong cross-lingual but optimised for translation pairs, not story-coherence paraphrase |

The 0.06 STS delta between MiniLM and mpnet is well below our threshold band
(payoff: 0.62 ± 0.07 from the calibration set). Operators who want the
upgrade can set `embedding_model` in `PipelineConfig`; defaults stay
lightweight.

`sentence-transformers` is already pinned in `requirements.txt`
(`>=2.7.0,<3.0`) — no new dependency.

## Why spaCy NER over LLM extraction (D2)

For character-presence detection we need PER entities from chapter content.

- **spaCy `xx_ent_wiki_sm`** (~12 MB, multilingual): handles Vietnamese,
  Chinese, English PER reasonably. Deterministic, zero API cost,
  sub-millisecond per chapter.
- **`vi_core_news_lg`**: Vietnamese-specific but underwhelming on novel-style
  prose.
- **LLM extraction with response caching**: explicitly rejected. Violates the
  "no new LLM calls in critical path" constraint and reintroduces the latency
  variance we are removing from the foreshadowing checks.

Hybrid: spaCy primary; canonical-name substring fallback only for character
names (an *identifier* match against `Character.name`, not a content match —
the only acceptable place for substring matching post-Sprint 2).

## Why fixed thresholds over adaptive (D4)

```python
semantic_payoff_threshold: float = 0.55
semantic_seed_threshold: float = 0.55
semantic_event_threshold: float = 0.55
semantic_character_threshold: float = 0.50
```

- **Adaptive thresholds hide regressions.** A percentile-based threshold per
  chapter ("the 70th percentile of cosine similarity for this chapter") moves
  the goalposts when prose drifts. A single low number is auditable.
- **Defaults are calibrated once** (P7, against a 30-pair labelled
  Vietnamese set). Calibration is not a runtime concern; the numbers are
  baked in as `PipelineConfig` defaults.
- Operators tune via config without touching code. YAGNI on auto-tuning.

## Cache invalidation policy (D3)

- **Storage:** SQLite table `embedding_cache(key TEXT PK, model_id TEXT, dim
  INTEGER, vec BLOB, created_at TIMESTAMP)`. Migration in P2.
- **Key:** `sha256(model_id ␟ NFC(text))`. NFC normalisation is mandatory for
  Vietnamese — combining vs precomposed diacritics must produce the same
  cache hit.
- **Storage form:** float32 little-endian bytes. Platform-stable on x86 and
  ARM (mostly LE; we do not target s390x).
- **Invalidation:** model_id-based cache namespacing. Bumping
  `embedding_model` config does not delete old rows; they become
  unreferenced. No TTL — embeddings are deterministic and the cache only
  grows.
- **Bound:** ~5 MB per 1000 chapters at 384-dim float32. Acceptable
  indefinitely on single-host SQLite.
- **Pruning:** optional `scripts/prune_embedding_cache.py` (not Sprint 2
  scope) for >90 day rows.
- **Story deletion does not prune:** payoff hints are cross-story reusable.

## Strict-mode behaviour (D5)

`STORYFORGE_SEMANTIC_STRICT=1` mirrors the Sprint 1 handoff strict-mode
flag. CI golden tests run with strict mode on so threshold regressions block
merge. Production runs default to warn-and-continue with findings persisted
to `chapters.semantic_findings`.

## Rejected alternatives (one-liners)

- **Train a custom classifier on Vietnamese payoff-pair data.** Sprint
  budget; insufficient labelled data; off-the-shelf is good enough.
- **GPU embeddings.** Single-host SQLite deployment target; CPU latency
  meets the 1.20× cold / 1.05× warm benchmark targets.
- **Replace ChromaDB with this cache.** Different access patterns (RAG
  retrieval vs cosine verification). Revisit in Sprint 4+.
- **Async embedding API.** YAGNI. Embeddings are CPU-bound; asyncio buys
  nothing without thread offloading.

## Consequences

Positive:
- One LLM call removed from the per-chapter critical path.
- Three keyword/substring sites become semantically aware.
- Outline scoring becomes reproducible.
- All three checks are CI-testable with golden fixtures.

Negative:
- ~120 MB model load on first embedding call (one-time per process).
- New SQLite table; migration must be safe (P2).
- Dependency on a quietly-trained third-party model. Mitigated by pinning
  `sentence-transformers` version and recording `embedding_model` in
  `ChapterSemanticFindings` so we can detect cross-version drift.
