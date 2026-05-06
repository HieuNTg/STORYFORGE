"""Context helpers: RAG KB lazy singleton and long-context chapter writing.

Bug #4 fix: Added RAG batch cache to prevent re-querying same context within batch.
"""

import hashlib
import logging
import threading
from typing import Optional

from models.schemas import Chapter, ChapterOutline, StoryContext, count_words

logger = logging.getLogger(__name__)

# Lazy singleton — only instantiated when rag_enabled=True
_rag_kb = None

# ══════════════════════════════════════════════════════════════════════════════
# Bug #4: RAG Batch Cache — prevents re-querying similar context within batch
# ══════════════════════════════════════════════════════════════════════════════


class RAGBatchCache:
    """Batch-scoped cache for RAG query results.

    Key: hash(outline_summary + character_names + thread_ids)
    Automatically clears between batches via reset_batch().
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._cache = {}
                    cls._instance._batch_id = 0
        return cls._instance

    @staticmethod
    def _make_key(
        outline_summary: str,
        char_names: list[str],
        thread_ids: list[str],
    ) -> str:
        """Generate cache key from query parameters."""
        parts = [
            outline_summary[:200],
            "|".join(sorted(char_names)[:5]),
            "|".join(sorted(thread_ids)[:5]),
        ]
        combined = "::".join(parts)
        return hashlib.md5(combined.encode()).hexdigest()[:16]

    def get(
        self,
        outline_summary: str,
        char_names: list[str],
        thread_ids: list[str],
    ) -> Optional[str]:
        """Get cached RAG result if exists."""
        key = self._make_key(outline_summary, char_names, thread_ids)
        return self._cache.get(key)

    def set(
        self,
        outline_summary: str,
        char_names: list[str],
        thread_ids: list[str],
        result: str,
    ) -> None:
        """Cache RAG result."""
        key = self._make_key(outline_summary, char_names, thread_ids)
        self._cache[key] = result

    def reset_batch(self) -> None:
        """Clear cache for new batch. Call at batch boundary."""
        with self._lock:
            self._cache.clear()
            self._batch_id += 1
            logger.debug(f"RAG batch cache cleared (batch {self._batch_id})")

    @property
    def hit_rate(self) -> float:
        """For analytics."""
        return 0.0  # Could track hits/misses if needed


def get_rag_batch_cache() -> RAGBatchCache:
    """Get the RAG batch cache singleton."""
    return RAGBatchCache()


def get_rag_kb(persist_dir: str):
    """Return a shared RAGKnowledgeBase instance (lazy init)."""
    global _rag_kb
    if _rag_kb is None:
        try:
            from services.rag_knowledge_base import RAGKnowledgeBase
            _rag_kb = RAGKnowledgeBase(persist_dir=persist_dir)
        except Exception as e:
            logger.warning(f"RAG init failed: {e}")
            return None
    return _rag_kb


def reset_rag_kb_singleton() -> None:
    """Test hook — drop the process-wide RAG singleton so next get_rag_kb() rebuilds."""
    global _rag_kb
    _rag_kb = None


def _rank_focus_characters(characters: list, max_n: int) -> list:
    """Pick up to max_n focus characters. Prefers protagonist/antagonist/main,
    falls back to original order so single-role casts still emit queries."""
    if not characters:
        return []
    priority_roles = {"protagonist", "antagonist", "main"}
    primary = [c for c in characters if getattr(c, "role", "").lower() in priority_roles]
    if len(primary) >= max_n:
        return primary[:max_n]
    # Pad from remaining in original order, skipping duplicates
    seen = {id(c) for c in primary}
    for c in characters:
        if id(c) in seen:
            continue
        primary.append(c)
        if len(primary) >= max_n:
            break
    return primary[:max_n]


def build_rag_context(
    rag_kb,
    outline: ChapterOutline,
    characters: list | None = None,
    open_threads: list | None = None,
    per_char_queries: int = 3,
    per_thread_queries: int = 3,
    n_per_query: int = 2,
    merge_cap: int = 8,
) -> str:
    """Multi-query semantic retrieval: fan out by summary + focus char + open thread.

    Dedups by (chapter_number, chunk_index), ranks ascending by embedding distance,
    and caps the merged set at `merge_cap`. Returns an already-formatted block ready
    to be appended to the chapter prompt, or "" when no hits / RAG unavailable.

    Bug #4: Uses batch cache to prevent re-querying same context within batch.
    """
    if rag_kb is None or not getattr(rag_kb, "is_available", False):
        return ""
    if not outline or not getattr(outline, "summary", ""):
        return ""

    # Bug #4: Check batch cache first
    char_names = [getattr(c, "name", "") for c in (characters or []) if getattr(c, "name", "")]
    thread_ids = [
        getattr(t, "thread_id", "") or getattr(t, "title", "")
        for t in (open_threads or [])
    ]
    cache = get_rag_batch_cache()
    cached = cache.get(outline.summary, char_names, thread_ids)
    if cached is not None:
        logger.debug(f"RAG cache hit for chapter {outline.chapter_number}")
        return cached

    queries: list[tuple[str, str, dict | None]] = []
    queries.append(("summary", outline.summary, None))

    focus_chars = _rank_focus_characters(characters or [], per_char_queries)
    for c in focus_chars:
        name = getattr(c, "name", "") or ""
        if not name:
            continue
        motivation = getattr(c, "motivation", "") or getattr(c, "personality", "") or ""
        q = f"{name}: {motivation}".strip(": ").strip()
        if not q:
            continue
        queries.append((f"char_{name}", q, {"characters": {"$contains": name}}))

    for t in (open_threads or [])[:per_thread_queries]:
        # PlotThread uses thread_id (not title); accept either for robustness
        tid = getattr(t, "thread_id", None) or getattr(t, "title", "") or ""
        desc = getattr(t, "description", "") or ""
        if not tid and not desc:
            continue
        qstr = f"{tid}: {desc}".strip(": ").strip()
        queries.append((f"thread_{tid or 'untitled'}", qstr, None))

    seen_keys: set[str] = set()
    merged: list[dict] = []
    for tag, q, where in queries:
        if not q:
            continue
        hits = rag_kb.query_structured(
            question=q,
            n_results=n_per_query,
            where=where,
            exclude_chapter=outline.chapter_number,
        )
        for h in hits:
            meta = h.get("metadata", {}) or {}
            key = f"{meta.get('chapter_number', '?')}_{meta.get('chunk_index', '?')}"
            if key in seen_keys:
                continue
            seen_keys.add(key)
            enriched = dict(h)
            enriched["query_tag"] = tag
            merged.append(enriched)

    merged.sort(key=lambda h: h.get("distance", 0.0))
    merged = merged[:merge_cap]
    if not merged:
        return ""

    lines = []
    for h in merged:
        meta = h.get("metadata", {}) or {}
        ch = meta.get("chapter_number", "?")
        tag = h.get("query_tag", "")
        text = (h.get("text") or "").strip()
        lines.append(f"[ch{ch} — {tag}] {text}")

    result = "\n---\n".join(lines)

    # Bug #4: Cache result for batch
    cache.set(outline.summary, char_names, thread_ids, result)
    logger.debug(f"RAG cache set for chapter {outline.chapter_number}")

    return result


def write_chapter_with_long_context(
    llm,
    long_context_client,
    config,
    title: str,
    genre: str,
    style: str,
    characters: list,
    world,
    outline: ChapterOutline,
    word_count: int,
    story_context: StoryContext,
    all_chapter_texts: list,
    bible_ctx: str = "",
    layer_model=None,
    enhancement_context: str = "",
    idea: str = "",
    idea_summary: str = "",
) -> Chapter:
    """Try long-context generation; fall back to standard if disabled/overflow."""
    # Lazy import for mock compat
    from pipeline.layer1_story.chapter_writer import build_chapter_prompt, strip_llm_preamble

    use_lc = False
    window_size = getattr(config.pipeline, "context_window_chapters", 5)
    windowed_texts = all_chapter_texts[-window_size:] if all_chapter_texts else []
    if (
        windowed_texts
        and config.pipeline.use_long_context
        and long_context_client.is_configured
    ):
        from services.token_counter import fits_in_context
        if fits_in_context(windowed_texts, long_context_client.max_context):
            use_lc = True
        else:
            logger.info(
                f"Chapter {outline.chapter_number}: long-context skipped "
                f"(texts exceed context window), falling back to rolling context"
            )

    # Bug 2: continuity anchor — last ~300 words of chapter N-1.
    prev_tail = ""
    if all_chapter_texts:
        words = (all_chapter_texts[-1] or "").split()
        prev_tail = " ".join(words[-300:]) if words else ""

    rag_kb = get_rag_kb(config.pipeline.rag_persist_dir) if config.pipeline.rag_enabled else None
    sys_prompt, user_prompt = build_chapter_prompt(
        config, title, genre, style, characters, world, outline,
        word_count, story_context, bible_context=bible_ctx,
        full_chapter_texts=windowed_texts if use_lc else None,
        rag_kb=rag_kb,
        enhancement_context=enhancement_context,
        previous_chapter_tail=prev_tail,
        idea=idea,
        idea_summary=idea_summary,
    )
    if use_lc:
        content = long_context_client.generate(
            system_prompt=sys_prompt, user_prompt=user_prompt, max_tokens=8192,
        )
    else:
        content = llm.generate(
            system_prompt=sys_prompt, user_prompt=user_prompt, max_tokens=8192,
            model=layer_model,
        )
    content = strip_llm_preamble(content)
    return Chapter(
        chapter_number=outline.chapter_number,
        title=outline.title,
        content=content,
        word_count=count_words(content),
    )
