"""Behavior tests for BatchChapterGenerator — focusing on P0-3 fix, batch size,
order preservation, retry logic, error propagation, checkpoint integration,
and CancelledError handling.

All tests are self-contained; no conftest changes required.
"""

import asyncio
import threading
from unittest.mock import MagicMock, patch

import pytest

from pipeline.layer1_story.batch_generator import (
    BatchChapterGenerator,
    CausalAccumulator,
    FrozenContext,
)
from models.schemas import (
    Chapter,
    ChapterOutline,
    StoryContext,
    StoryDraft,
    WorldSetting,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_WORLD = WorldSetting(name="TestWorld", description="A test world")


def _make_outline(num: int, pacing: str = "rising") -> ChapterOutline:
    return ChapterOutline(
        chapter_number=num,
        title=f"Chapter {num}",
        summary=f"Summary {num}",
        pacing_type=pacing,
    )


def _make_chapter(num: int, content: str | None = None) -> Chapter:
    text = content or (f"Content of chapter {num} " * 50)
    return Chapter(
        chapter_number=num,
        title=f"Chapter {num}",
        content=text,
        word_count=len(text.split()),
    )


def _mock_generator(batch_size: int = 5, parallel: bool = False, use_asyncio: bool = True):
    """Return a MagicMock StoryGenerator with realistic pipeline config."""
    gen = MagicMock()
    gen.config.pipeline.chapter_batch_size = batch_size
    gen.config.pipeline.parallel_chapters_enabled = parallel
    gen.config.pipeline.parallel_use_asyncio = use_asyncio
    gen.config.pipeline.context_window_chapters = 5
    gen.config.pipeline.story_bible_enabled = False
    gen.config.pipeline.enable_self_review = False
    gen.config.pipeline.enable_chapter_contracts = False
    gen.config.pipeline.enable_contract_validation = False
    gen.config.pipeline.enable_chapter_critique = False
    gen.config.pipeline.enable_scene_decomposition = False
    gen.config.pipeline.enable_tiered_context = False
    gen.config.pipeline.enable_thread_enforcement = False
    gen.config.pipeline.enable_l1_causal_graph = False
    gen.config.pipeline.enable_emotional_memory = False
    gen.config.pipeline.enable_foreshadowing_enforcement = False
    gen.config.pipeline.enable_consistency_rewrite = False
    gen.config.pipeline.enable_pacing_enforcement = False
    gen.config.pipeline.foreshadowing_payoff_rewrite_on_miss = False
    gen.config.pipeline.rag_enabled = False
    gen.config.pipeline.rag_index_chapters = False
    gen.config.pipeline.parallel_causal_sync = True
    gen.config.pipeline.chapter_retry_max = 2
    gen.config.pipeline.chapter_retry_threshold = 0.6
    gen.token_budget_per_chapter = 4000
    gen._layer_model = "cheap"
    gen.bible_manager = MagicMock()
    gen.bible_manager.get_context_for_chapter.return_value = ""
    gen._get_self_reviewer.return_value = None
    return gen


def _make_draft() -> StoryDraft:
    return StoryDraft(title="Test", genre="Fantasy", synopsis="S", characters=[], world=_WORLD)


# ---------------------------------------------------------------------------
# CausalAccumulator
# ---------------------------------------------------------------------------


class TestCausalAccumulator:
    def test_add_and_retrieve_event(self):
        acc = CausalAccumulator()
        acc.add_event(1, "causal_marker", "desc A")
        events = acc.get_events_sorted()
        assert len(events) == 1
        assert events[0]["chapter"] == 1
        assert events[0]["type"] == "causal_marker"

    def test_sorted_by_chapter(self):
        acc = CausalAccumulator()
        acc.add_event(3, "t", "d3")
        acc.add_event(1, "t", "d1")
        acc.add_event(2, "t", "d2")
        events = acc.get_events_sorted()
        assert [e["chapter"] for e in events] == [1, 2, 3]

    def test_clear(self):
        acc = CausalAccumulator()
        acc.add_event(1, "t", "d")
        acc.clear()
        assert acc.get_events_sorted() == []

    def test_thread_safety(self):
        """Multiple threads adding events must not lose or corrupt data."""
        acc = CausalAccumulator()
        errors = []

        def add_many(chapter_num):
            try:
                for _ in range(20):
                    acc.add_event(chapter_num, "t", "d")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=add_many, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert len(acc.get_events_sorted()) == 100  # 5 threads * 20 events


# ---------------------------------------------------------------------------
# FrozenContext
# ---------------------------------------------------------------------------


class TestFrozenContextIsolation:
    def test_mutations_to_source_not_reflected(self):
        ctx = StoryContext(total_chapters=5)
        ctx.recent_summaries = ["s1"]
        ctx.character_states = []
        ctx.plot_events = []
        texts = ["t1"]

        frozen = FrozenContext(ctx, texts)
        ctx.recent_summaries.append("s2")
        texts.append("t2")

        assert frozen.recent_summaries == ["s1"]
        assert frozen.chapter_texts == ["t1"]


# ---------------------------------------------------------------------------
# _split_batches
# ---------------------------------------------------------------------------


class TestSplitBatches:
    def test_batch_size_respected_exact(self):
        gen = _mock_generator(batch_size=3)
        bg = BatchChapterGenerator(gen)
        batches = bg._split_batches([_make_outline(i) for i in range(1, 10)])
        assert all(len(b) == 3 for b in batches)

    def test_batch_size_respected_remainder(self):
        gen = _mock_generator(batch_size=4)
        bg = BatchChapterGenerator(gen)
        batches = bg._split_batches([_make_outline(i) for i in range(1, 7)])
        assert len(batches) == 2
        assert len(batches[0]) == 4
        assert len(batches[1]) == 2

    def test_single_item(self):
        gen = _mock_generator(batch_size=5)
        bg = BatchChapterGenerator(gen)
        assert bg._split_batches([_make_outline(1)]) == [[_make_outline(1)]]

    def test_empty(self):
        gen = _mock_generator(batch_size=5)
        bg = BatchChapterGenerator(gen)
        assert bg._split_batches([]) == []


# ---------------------------------------------------------------------------
# Sequential mode — basic generation
# ---------------------------------------------------------------------------


class TestSequentialGeneration:
    @patch("pipeline.layer1_story.batch_generator.process_chapter_post_write")
    def test_all_chapters_produced(self, mock_post):
        gen = _mock_generator(batch_size=5)
        gen._write_chapter_with_long_context.side_effect = (
            lambda *a, **kw: _make_chapter(a[5].chapter_number)
        )
        bg = BatchChapterGenerator(gen)
        draft = _make_draft()
        bg.generate_chapters(
            draft=draft,
            outlines=[_make_outline(i) for i in range(1, 6)],
            story_context=StoryContext(total_chapters=5),
            title="T", genre="G", style="S", characters=[], world=_WORLD,
        )
        assert len(draft.chapters) == 5
        assert [ch.chapter_number for ch in draft.chapters] == [1, 2, 3, 4, 5]

    @patch("pipeline.layer1_story.batch_generator.process_chapter_post_write")
    def test_order_preserved_across_batches(self, mock_post):
        """Chapter N+1 call happens after chapter N's post_write — i.e. live context updates."""
        gen = _mock_generator(batch_size=2)
        call_log = []

        def fake_write(*a, **kw):
            ch = _make_chapter(a[5].chapter_number)
            call_log.append(("write", ch.chapter_number))
            return ch

        def fake_post(chapter, *a, **kw):
            call_log.append(("post", chapter.chapter_number))

        gen._write_chapter_with_long_context.side_effect = fake_write
        mock_post.side_effect = fake_post

        bg = BatchChapterGenerator(gen)
        draft = _make_draft()
        bg.generate_chapters(
            draft=draft,
            outlines=[_make_outline(i) for i in range(1, 5)],
            story_context=StoryContext(total_chapters=4),
            title="T", genre="G", style="S", characters=[], world=_WORLD,
        )

        # Sequential: write then post within each batch, strictly ordered
        assert call_log == [
            ("write", 1), ("post", 1),
            ("write", 2), ("post", 2),
            ("write", 3), ("post", 3),
            ("write", 4), ("post", 4),
        ]

    @patch("pipeline.layer1_story.batch_generator.process_chapter_post_write")
    def test_chapter_content_accumulated_in_all_chapter_texts(self, mock_post):
        """Each chapter's content is appended so later chapters see prior content."""
        gen = _mock_generator(batch_size=5)
        seen_texts: list[list[str]] = []

        def fake_write(title, genre, style, characters, world, outline,
                       word_count, story_context, all_chapter_texts, *a, **kw):
            seen_texts.append(list(all_chapter_texts))
            return _make_chapter(outline.chapter_number)

        gen._write_chapter_with_long_context.side_effect = fake_write
        bg = BatchChapterGenerator(gen)
        draft = _make_draft()
        bg.generate_chapters(
            draft=draft,
            outlines=[_make_outline(i) for i in range(1, 4)],
            story_context=StoryContext(total_chapters=3),
            title="T", genre="G", style="S", characters=[], world=_WORLD,
        )

        # chapter 1 sees empty list, chapter 2 sees 1 entry, chapter 3 sees 2 entries
        assert len(seen_texts[0]) == 0
        assert len(seen_texts[1]) == 1
        assert len(seen_texts[2]) == 2

    @patch("pipeline.layer1_story.batch_generator.process_chapter_post_write")
    def test_write_error_propagates(self, mock_post):
        gen = _mock_generator(batch_size=5)
        gen._write_chapter_with_long_context.side_effect = RuntimeError("LLM unavailable")

        bg = BatchChapterGenerator(gen)
        draft = _make_draft()
        with pytest.raises(RuntimeError, match="LLM unavailable"):
            bg.generate_chapters(
                draft=draft,
                outlines=[_make_outline(1)],
                story_context=StoryContext(total_chapters=1),
                title="T", genre="G", style="S", characters=[], world=_WORLD,
            )

    @patch("pipeline.layer1_story.batch_generator.process_chapter_post_write")
    def test_checkpoint_callback_receives_batch_index(self, mock_post):
        gen = _mock_generator(batch_size=2)
        gen._write_chapter_with_long_context.side_effect = (
            lambda *a, **kw: _make_chapter(a[5].chapter_number)
        )
        checkpoint_cb = MagicMock()
        bg = BatchChapterGenerator(gen)
        draft = _make_draft()
        bg.generate_chapters(
            draft=draft,
            outlines=[_make_outline(i) for i in range(1, 5)],
            story_context=StoryContext(total_chapters=4),
            title="T", genre="G", style="S", characters=[], world=_WORLD,
            batch_checkpoint_callback=checkpoint_cb,
        )
        # 2 batches: [1,2] and [3,4] → calls (1,2) and (2,2)
        assert checkpoint_cb.call_count == 2
        checkpoint_cb.assert_any_call(1, 2)
        checkpoint_cb.assert_any_call(2, 2)

    @patch("pipeline.layer1_story.batch_generator.process_chapter_post_write")
    def test_checkpoint_failure_does_not_abort_generation(self, mock_post):
        gen = _mock_generator(batch_size=5)
        gen._write_chapter_with_long_context.side_effect = (
            lambda *a, **kw: _make_chapter(a[5].chapter_number)
        )

        def bad_ckpt(*args):
            raise OSError("disk full")

        bg = BatchChapterGenerator(gen)
        draft = _make_draft()
        # Should NOT raise — checkpoint errors are swallowed
        bg.generate_chapters(
            draft=draft,
            outlines=[_make_outline(i) for i in range(1, 3)],
            story_context=StoryContext(total_chapters=2),
            title="T", genre="G", style="S", characters=[], world=_WORLD,
            batch_checkpoint_callback=bad_ckpt,
        )
        assert len(draft.chapters) == 2

    @patch("pipeline.layer1_story.batch_generator.process_chapter_post_write")
    def test_returns_draft_chapters_list(self, mock_post):
        gen = _mock_generator(batch_size=5)
        gen._write_chapter_with_long_context.side_effect = (
            lambda *a, **kw: _make_chapter(a[5].chapter_number)
        )
        bg = BatchChapterGenerator(gen)
        draft = _make_draft()
        result = bg.generate_chapters(
            draft=draft,
            outlines=[_make_outline(i) for i in range(1, 4)],
            story_context=StoryContext(total_chapters=3),
            title="T", genre="G", style="S", characters=[], world=_WORLD,
        )
        assert result == list(draft.chapters)
        assert len(result) == 3


# ---------------------------------------------------------------------------
# Parallel mode (asyncio) — P0-3 fix: partial failure persistence
# ---------------------------------------------------------------------------


class TestP03PartialFailureFix:
    """Critical: when one chapter in a parallel batch fails, the others that
    already succeeded must be RAG-indexed before the error re-raises, and
    the exception must propagate with the exact original type/message.
    Fixed at lines 1155-1192 of batch_generator.py.

    Note: the fix's "persisting" means _index_chapter_into_rag is called for
    the successful chapters before raise. draft.chapters is populated by the
    outer generate_chapters loop only when a batch returns successfully, so on
    partial failure the draft is not mutated — the exception bubbles immediately.
    """

    @pytest.mark.asyncio
    async def test_async_batch_partial_failure_rag_indexes_successes(self):
        """asyncio gather: 2 succeed, 1 fails — RAG index called for the 2 successes."""
        gen = _mock_generator(batch_size=3, parallel=True, use_asyncio=True)
        gen.config.pipeline.rag_enabled = True
        gen.config.pipeline.rag_index_chapters = True

        def fake_write(title, genre, style, characters, world, outline,
                       word_count, story_context, all_chapter_texts, *a, **kw):
            if outline.chapter_number == 2:
                raise ValueError("chapter 2 failed")
            return _make_chapter(outline.chapter_number)

        gen._write_chapter_with_long_context.side_effect = fake_write
        indexed_chapters: list[int] = []

        def fake_index_chapter(chapter_number, content, characters, threads, summary):
            indexed_chapters.append(chapter_number)
            return 1

        with patch("pipeline.layer1_story.batch_generator.process_chapter_post_write"), \
             patch("pipeline.layer1_story.batch_generator._index_chapter_into_rag") as mock_rag:
            mock_rag.return_value = 0

            bg = BatchChapterGenerator(gen)
            draft = _make_draft()

            with pytest.raises(ValueError, match="chapter 2 failed"):
                bg.generate_chapters(
                    draft=draft,
                    outlines=[_make_outline(i) for i in range(1, 4)],
                    story_context=StoryContext(total_chapters=3),
                    title="T", genre="G", style="S", characters=[], world=_WORLD,
                )

            # _index_chapter_into_rag must be called for the 2 successful chapters
            # before the exception propagates (P0-3 fix at lines 1175-1192)
            assert mock_rag.call_count >= 2
            rag_chapter_nums = [c.args[1].chapter_number for c in mock_rag.call_args_list]
            assert 1 in rag_chapter_nums
            assert 3 in rag_chapter_nums

    @pytest.mark.asyncio
    async def test_async_batch_all_fail_nothing_persisted(self):
        """When all chapters in a batch fail, nothing is appended to draft."""
        gen = _mock_generator(batch_size=2, parallel=True, use_asyncio=True)
        gen._write_chapter_with_long_context.side_effect = RuntimeError("all fail")

        with patch("pipeline.layer1_story.batch_generator.process_chapter_post_write"):
            bg = BatchChapterGenerator(gen)
            draft = _make_draft()

            with pytest.raises(RuntimeError, match="all fail"):
                bg.generate_chapters(
                    draft=draft,
                    outlines=[_make_outline(i) for i in range(1, 3)],
                    story_context=StoryContext(total_chapters=2),
                    title="T", genre="G", style="S", characters=[], world=_WORLD,
                )

            assert draft.chapters == []

    @pytest.mark.asyncio
    async def test_async_batch_first_exception_is_reraised(self):
        """The actual exception from the failing chapter must bubble up."""
        gen = _mock_generator(batch_size=2, parallel=True, use_asyncio=True)

        def fake_write(title, genre, style, characters, world, outline, *a, **kw):
            if outline.chapter_number == 1:
                raise KeyError("missing key in chapter 1")
            return _make_chapter(outline.chapter_number)

        gen._write_chapter_with_long_context.side_effect = fake_write

        with patch("pipeline.layer1_story.batch_generator.process_chapter_post_write"):
            bg = BatchChapterGenerator(gen)
            draft = _make_draft()

            with pytest.raises(KeyError, match="missing key in chapter 1"):
                bg.generate_chapters(
                    draft=draft,
                    outlines=[_make_outline(1), _make_outline(2)],
                    story_context=StoryContext(total_chapters=2),
                    title="T", genre="G", style="S", characters=[], world=_WORLD,
                )


# ---------------------------------------------------------------------------
# Parallel mode — order preservation
# ---------------------------------------------------------------------------


class TestParallelOrderPreservation:
    @patch("pipeline.layer1_story.batch_generator.process_chapter_post_write")
    def test_chapters_sorted_by_number(self, mock_post):
        gen = _mock_generator(batch_size=4, parallel=True)

        def fake_write(title, genre, style, characters, world, outline, *a, **kw):
            return _make_chapter(outline.chapter_number)

        gen._write_chapter_with_long_context.side_effect = fake_write

        bg = BatchChapterGenerator(gen)
        draft = _make_draft()
        bg.generate_chapters(
            draft=draft,
            outlines=[_make_outline(i) for i in range(1, 5)],
            story_context=StoryContext(total_chapters=4),
            title="T", genre="G", style="S", characters=[], world=_WORLD,
        )

        nums = [ch.chapter_number for ch in draft.chapters]
        assert nums == sorted(nums)

    @patch("pipeline.layer1_story.batch_generator.process_chapter_post_write")
    def test_post_processing_sequential_in_order(self, mock_post):
        gen = _mock_generator(batch_size=3, parallel=True)
        post_order = []

        gen._write_chapter_with_long_context.side_effect = (
            lambda *a, **kw: _make_chapter(a[5].chapter_number)
        )

        def fake_post(chapter, *a, **kw):
            post_order.append(chapter.chapter_number)

        mock_post.side_effect = fake_post

        bg = BatchChapterGenerator(gen)
        draft = _make_draft()
        bg.generate_chapters(
            draft=draft,
            outlines=[_make_outline(i) for i in range(1, 4)],
            story_context=StoryContext(total_chapters=3),
            title="T", genre="G", style="S", characters=[], world=_WORLD,
        )

        assert post_order == [1, 2, 3]


# ---------------------------------------------------------------------------
# Threaded parallel mode
# ---------------------------------------------------------------------------


class TestThreadedParallelMode:
    @patch("pipeline.layer1_story.batch_generator.process_chapter_post_write")
    def test_threaded_all_chapters_produced(self, mock_post):
        gen = _mock_generator(batch_size=3, parallel=True, use_asyncio=False)
        gen._write_chapter_with_long_context.side_effect = (
            lambda *a, **kw: _make_chapter(a[5].chapter_number)
        )
        bg = BatchChapterGenerator(gen)
        draft = _make_draft()
        bg.generate_chapters(
            draft=draft,
            outlines=[_make_outline(i) for i in range(1, 4)],
            story_context=StoryContext(total_chapters=3),
            title="T", genre="G", style="S", characters=[], world=_WORLD,
        )
        assert len(draft.chapters) == 3

    @patch("pipeline.layer1_story.batch_generator.process_chapter_post_write")
    def test_threaded_error_propagates(self, mock_post):
        gen = _mock_generator(batch_size=2, parallel=True, use_asyncio=False)
        gen._write_chapter_with_long_context.side_effect = RuntimeError("thread crash")

        bg = BatchChapterGenerator(gen)
        draft = _make_draft()
        with pytest.raises(RuntimeError, match="thread crash"):
            bg.generate_chapters(
                draft=draft,
                outlines=[_make_outline(1), _make_outline(2)],
                story_context=StoryContext(total_chapters=2),
                title="T", genre="G", style="S", characters=[], world=_WORLD,
            )


# ---------------------------------------------------------------------------
# Causal sync
# ---------------------------------------------------------------------------


class TestCausalSync:
    @patch("pipeline.layer1_story.batch_generator.process_chapter_post_write")
    def test_causal_events_synced_to_context(self, mock_post):
        """When a chapter contains a causal keyword, _sync_causal_events is called."""
        gen = _mock_generator(batch_size=2, parallel=True)
        gen.config.pipeline.parallel_causal_sync = True

        def fake_write(title, genre, style, characters, world, outline, *a, **kw):
            # content contains Vietnamese causal keyword → triggers extraction
            return _make_chapter(outline.chapter_number, content="vì thế điều này xảy ra " * 30)

        gen._write_chapter_with_long_context.side_effect = fake_write

        story_ctx = StoryContext(total_chapters=2)
        synced_events: list = []

        class FakeGraph:
            def add_event(self, chapter, event_type, description):
                synced_events.append({"chapter": chapter, "type": event_type})

        story_ctx.causal_graph = FakeGraph()

        bg = BatchChapterGenerator(gen)
        draft = _make_draft()
        bg.generate_chapters(
            draft=draft,
            outlines=[_make_outline(1), _make_outline(2)],
            story_context=story_ctx,
            title="T", genre="G", style="S", characters=[], world=_WORLD,
        )

        assert len(synced_events) >= 1

    @patch("pipeline.layer1_story.batch_generator.process_chapter_post_write")
    def test_causal_sync_disabled(self, mock_post):
        """When parallel_causal_sync=False, no events are synced."""
        gen = _mock_generator(batch_size=2, parallel=True)
        gen.config.pipeline.parallel_causal_sync = False
        gen._write_chapter_with_long_context.side_effect = (
            lambda *a, **kw: _make_chapter(a[5].chapter_number, content="vì thế xảy ra " * 30)
        )
        story_ctx = StoryContext(total_chapters=2)
        events_synced = []

        class FakeGraph:
            def add_event(self, **kw):
                events_synced.append(kw)

        story_ctx.causal_graph = FakeGraph()
        bg = BatchChapterGenerator(gen)
        # Rebuild with causal_sync = False
        bg.causal_sync = False
        draft = _make_draft()
        bg.generate_chapters(
            draft=draft,
            outlines=[_make_outline(1), _make_outline(2)],
            story_context=story_ctx,
            title="T", genre="G", style="S", characters=[], world=_WORLD,
        )
        assert events_synced == []


# ---------------------------------------------------------------------------
# _build_sibling_context
# ---------------------------------------------------------------------------


class TestBuildSiblingContext:
    def test_single_outline_returns_empty(self):
        assert BatchChapterGenerator._build_sibling_context([_make_outline(1)]) == ""

    def test_empty_batch_returns_empty(self):
        assert BatchChapterGenerator._build_sibling_context([]) == ""

    def test_multiple_outlines_contain_all_chapters(self):
        result = BatchChapterGenerator._build_sibling_context(
            [_make_outline(i) for i in range(1, 4)]
        )
        assert "Ch1" in result
        assert "Ch2" in result
        assert "Ch3" in result

    def test_each_line_contains_summary(self):
        outlines = [_make_outline(1), _make_outline(2)]
        result = BatchChapterGenerator._build_sibling_context(outlines)
        assert "Summary 1" in result
        assert "Summary 2" in result


# ---------------------------------------------------------------------------
# Stream callback forces sequential path
# ---------------------------------------------------------------------------


class TestStreamCallbackForcesSequential:
    @patch("pipeline.layer1_story.batch_generator.process_chapter_post_write")
    def test_stream_uses_write_chapter_stream(self, mock_post):
        gen = _mock_generator(batch_size=2, parallel=True)
        gen.write_chapter_stream.side_effect = (
            lambda *a, **kw: _make_chapter(a[5].chapter_number)
        )
        bg = BatchChapterGenerator(gen)
        draft = _make_draft()
        bg.generate_chapters(
            draft=draft,
            outlines=[_make_outline(1)],
            story_context=StoryContext(total_chapters=1),
            title="T", genre="G", style="S", characters=[], world=_WORLD,
            stream_callback=MagicMock(),
        )
        gen.write_chapter_stream.assert_called_once()
        gen._write_chapter_with_long_context.assert_not_called()


# ---------------------------------------------------------------------------
# asyncio.CancelledError propagation
# ---------------------------------------------------------------------------


class TestCancelledErrorHandling:
    @pytest.mark.asyncio
    async def test_cancelled_error_propagates_from_write(self):
        """CancelledError from a chapter write must not be swallowed."""
        gen = _mock_generator(batch_size=1, parallel=True)
        gen._write_chapter_with_long_context.side_effect = asyncio.CancelledError()

        with patch("pipeline.layer1_story.batch_generator.process_chapter_post_write"):
            bg = BatchChapterGenerator(gen)
            draft = _make_draft()
            with pytest.raises((asyncio.CancelledError, Exception)):
                bg.generate_chapters(
                    draft=draft,
                    outlines=[_make_outline(1)],
                    story_context=StoryContext(total_chapters=1),
                    title="T", genre="G", style="S", characters=[], world=_WORLD,
                )


# ---------------------------------------------------------------------------
# Batch size config edge cases
# ---------------------------------------------------------------------------


class TestBatchSizeConfig:
    @patch("pipeline.layer1_story.batch_generator.process_chapter_post_write")
    def test_batch_size_1_writes_all_chapters(self, mock_post):
        gen = _mock_generator(batch_size=1)
        gen._write_chapter_with_long_context.side_effect = (
            lambda *a, **kw: _make_chapter(a[5].chapter_number)
        )
        bg = BatchChapterGenerator(gen)
        draft = _make_draft()
        bg.generate_chapters(
            draft=draft,
            outlines=[_make_outline(i) for i in range(1, 4)],
            story_context=StoryContext(total_chapters=3),
            title="T", genre="G", style="S", characters=[], world=_WORLD,
        )
        assert len(draft.chapters) == 3

    @patch("pipeline.layer1_story.batch_generator.process_chapter_post_write")
    def test_batch_size_larger_than_total_chapters(self, mock_post):
        gen = _mock_generator(batch_size=100)
        gen._write_chapter_with_long_context.side_effect = (
            lambda *a, **kw: _make_chapter(a[5].chapter_number)
        )
        bg = BatchChapterGenerator(gen)
        draft = _make_draft()
        bg.generate_chapters(
            draft=draft,
            outlines=[_make_outline(i) for i in range(1, 4)],
            story_context=StoryContext(total_chapters=3),
            title="T", genre="G", style="S", characters=[], world=_WORLD,
        )
        assert len(draft.chapters) == 3

    def test_reads_batch_size_from_config(self):
        for size in [1, 3, 7, 10]:
            gen = _mock_generator(batch_size=size)
            bg = BatchChapterGenerator(gen)
            assert bg.batch_size == size
