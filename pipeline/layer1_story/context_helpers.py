"""Context helpers: RAG KB lazy singleton and long-context chapter writing."""

import logging

from models.schemas import Chapter, ChapterOutline, StoryContext, count_words

logger = logging.getLogger(__name__)

# Lazy singleton — only instantiated when rag_enabled=True
_rag_kb = None


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
) -> Chapter:
    """Try long-context generation; fall back to standard if disabled/overflow."""
    # Lazy import for mock compat
    from pipeline.layer1_story.chapter_writer import build_chapter_prompt

    use_lc = False
    if (
        all_chapter_texts
        and config.pipeline.use_long_context
        and long_context_client.is_configured
    ):
        from services.token_counter import fits_in_context
        if fits_in_context(all_chapter_texts, long_context_client.max_context):
            use_lc = True
        else:
            logger.info(
                f"Chapter {outline.chapter_number}: long-context skipped "
                f"(texts exceed context window), falling back to rolling context"
            )

    rag_kb = get_rag_kb(config.pipeline.rag_persist_dir) if config.pipeline.rag_enabled else None
    sys_prompt, user_prompt = build_chapter_prompt(
        config, title, genre, style, characters, world, outline,
        word_count, story_context, bible_context=bible_ctx,
        full_chapter_texts=all_chapter_texts if use_lc else None,
        rag_kb=rag_kb,
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
    return Chapter(
        chapter_number=outline.chapter_number,
        title=outline.title,
        content=content,
        word_count=count_words(content),
    )
