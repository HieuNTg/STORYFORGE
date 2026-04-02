# Long-Context RAG Optimization Report

**Date:** 2026-04-02

## Current RAG Usage

`services/rag_knowledge_base.py` — ChromaDB + sentence-transformers vector store.

**Query pattern:** Called from `pipeline/layer1_story/context_helpers.py::get_rag_kb()` during Layer 1 chapter generation.
**Frequency:** Up to `num_chapters` queries per run (default 100 = 100 queries).
**Config:** 500-char chunks, 50-char overlap, top-3 results per query.
**Default:** Disabled (`rag_enabled: false`). User opt-in.

## Token Overhead

Each RAG retrieval inserts ≤ 3 × 500 chars ≈ **375–500 tokens** into the chapter prompt.

For a 100-chapter story: ~40,000–50,000 extra input tokens total, split across 100 calls.
Embedding inference (local `all-MiniLM-L6-v2`): negligible. ChromaDB query: ~5–20 ms each.

## Which Pipeline Stages Can Skip RAG with 128K+ Models

| Stage | Skip RAG? | Reason |
|-------|-----------|--------|
| Layer 1 — world/character design | No | RAG provides uploaded source material |
| Layer 1 — chapters 1–5 | Conditional | Story bible fits in context |
| Layer 1 — chapters 6+ (128K+ model) | Yes | Full prior chapters already in window |
| Layer 2 — drama analysis/enhancement | Yes | Works entirely on in-memory story draft |
| Layer 3 — storyboard | Yes | Operates on enhanced_story object |

## Cost Comparison

| Model | Context | RAG needed? |
|-------|---------|-------------|
| GPT-4o-mini | 128K | No for ch 6+ (saves ~$0.02/100-ch run) |
| Claude 3 Haiku | 200K | No |
| Gemini 1.5 Pro | 1M | No |
| Llama 3 8B (Ollama) | 8K | Yes — required |
| GPT-3.5-turbo | 16K | Yes for ch 6+ |

## Recommendation: Conditional RAG

```python
# pipeline/layer1_story/context_helpers.py
LONG_CONTEXT_THRESHOLD = 100_000  # tokens

def get_rag_kb():
    effective_window = detect_context_window(config.llm.model)
    if effective_window >= LONG_CONTEXT_THRESHOLD:
        return NoOpRAGKnowledgeBase()  # skip RAG transparently
    return RAGKnowledgeBase() if config.pipeline.rag_enabled else NoOpRAGKnowledgeBase()
```

**Expected impact:**
- Removes 375–500 tokens × N_chapters from input cost on long-context runs.
- Eliminates ChromaDB startup latency (~1–2s) for Ollama/small-model runs.
- No quality regression: story bible replaces retrieval for 100K+ context models.
- Add Settings → Advanced UI hint: "RAG auto-disabled for long-context models."
