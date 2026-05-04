"""Tests for BatchChapterGenerator."""

from unittest.mock import MagicMock, patch

from pipeline.layer1_story.batch_generator import BatchChapterGenerator, FrozenContext
from models.schemas import StoryContext, StoryDraft, ChapterOutline, Chapter, WorldSetting


_WORLD = WorldSetting(name="TestWorld", description="A test world")


def _make_outline(num: int) -> ChapterOutline:
    return ChapterOutline(chapter_number=num, title=f"Chapter {num}", summary=f"Summary {num}")


def _make_chapter(num: int) -> Chapter:
    return Chapter(
        chapter_number=num,
        title=f"Chapter {num}",
        content=f"Content of chapter {num} " * 50,
        word_count=200,
    )


def _mock_generator(batch_size=5, parallel=False):
    """Create a mock StoryGenerator with realistic config."""
    gen = MagicMock()
    gen.config.pipeline.chapter_batch_size = batch_size
    gen.config.pipeline.parallel_chapters_enabled = parallel
    gen.config.pipeline.context_window_chapters = 5
    gen.config.pipeline.story_bible_enabled = False
    gen.config.pipeline.enable_self_review = False
    gen.token_budget_per_chapter = 4000
    return gen


class TestFrozenContext:
    def test_captures_snapshot(self):
        ctx = StoryContext(total_chapters=10)
        ctx.recent_summaries = ["s1", "s2"]
        ctx.character_states = ["cs1"]
        ctx.plot_events = ["pe1", "pe2"]
        texts = ["chapter 1 text", "chapter 2 text"]

        frozen = FrozenContext(ctx, texts)

        assert frozen.recent_summaries == ["s1", "s2"]
        assert frozen.character_states == ["cs1"]
        assert frozen.plot_events == ["pe1", "pe2"]
        assert frozen.chapter_texts == ["chapter 1 text", "chapter 2 text"]

    def test_snapshot_is_independent_copy(self):
        ctx = StoryContext(total_chapters=5)
        ctx.recent_summaries = ["s1"]
        texts = ["t1"]

        frozen = FrozenContext(ctx, texts)

        ctx.recent_summaries.append("s2")
        texts.append("t2")

        assert frozen.recent_summaries == ["s1"]
        assert frozen.chapter_texts == ["t1"]


class TestSplitBatches:
    def test_exact_division(self):
        gen = _mock_generator(batch_size=5)
        bg = BatchChapterGenerator(gen)
        outlines = [_make_outline(i) for i in range(1, 11)]
        batches = bg._split_batches(outlines)
        assert len(batches) == 2
        assert len(batches[0]) == 5
        assert len(batches[1]) == 5

    def test_remainder_batch(self):
        gen = _mock_generator(batch_size=3)
        bg = BatchChapterGenerator(gen)
        outlines = [_make_outline(i) for i in range(1, 8)]
        batches = bg._split_batches(outlines)
        assert len(batches) == 3
        assert len(batches[0]) == 3
        assert len(batches[1]) == 3
        assert len(batches[2]) == 1

    def test_single_chapter(self):
        gen = _mock_generator(batch_size=5)
        bg = BatchChapterGenerator(gen)
        outlines = [_make_outline(1)]
        batches = bg._split_batches(outlines)
        assert len(batches) == 1
        assert len(batches[0]) == 1

    def test_empty_outlines(self):
        gen = _mock_generator(batch_size=5)
        bg = BatchChapterGenerator(gen)
        batches = bg._split_batches([])
        assert batches == []


class TestBatchChapterGenerator:
    @patch("pipeline.layer1_story.batch_generator.process_chapter_post_write")
    def test_generates_all_chapters(self, mock_post_write):
        gen = _mock_generator(batch_size=3)
        chapters_created = []

        def fake_write(title, genre, style, characters, world, outline,
                       word_count, story_context, all_chapter_texts, bible_ctx="", **kwargs):
            ch = _make_chapter(outline.chapter_number)
            chapters_created.append(ch)
            return ch

        gen._write_chapter_with_long_context.side_effect = fake_write

        bg = BatchChapterGenerator(gen)
        draft = StoryDraft(
            title="Test", genre="Fantasy", synopsis="Test story",
            characters=[], world=_WORLD, outlines=[],
        )
        outlines = [_make_outline(i) for i in range(1, 6)]
        ctx = StoryContext(total_chapters=5)

        bg.generate_chapters(
            draft=draft, outlines=outlines, story_context=ctx,
            title="Test", genre="Fantasy", style="Detailed",
            characters=[], world=_WORLD, word_count=2000,
        )

        assert len(draft.chapters) == 5
        assert mock_post_write.call_count == 5

    @patch("pipeline.layer1_story.batch_generator.process_chapter_post_write")
    def test_batch_boundaries(self, mock_post_write):
        gen = _mock_generator(batch_size=2)
        call_order = []

        def fake_write(*args, **kwargs):
            outline = args[5]
            call_order.append(f"write_{outline.chapter_number}")
            return _make_chapter(outline.chapter_number)

        gen._write_chapter_with_long_context.side_effect = fake_write

        def fake_post(*args, **kwargs):
            chapter = args[0]
            call_order.append(f"post_{chapter.chapter_number}")

        mock_post_write.side_effect = fake_post

        bg = BatchChapterGenerator(gen)
        draft = StoryDraft(
            title="T", genre="G", synopsis="S",
            characters=[], world=_WORLD, outlines=[],
        )
        outlines = [_make_outline(i) for i in range(1, 5)]
        ctx = StoryContext(total_chapters=4)

        bg.generate_chapters(
            draft=draft, outlines=outlines, story_context=ctx,
            title="T", genre="G", style="S",
            characters=[], world=_WORLD,
        )

        assert call_order == [
            "write_1", "post_1", "write_2", "post_2",
            "write_3", "post_3", "write_4", "post_4",
        ]

    def test_reads_config_batch_size(self):
        gen = _mock_generator(batch_size=7)
        bg = BatchChapterGenerator(gen)
        assert bg.batch_size == 7

    def test_reads_config_parallel_flag(self):
        gen = _mock_generator(parallel=True)
        bg = BatchChapterGenerator(gen)
        assert bg.parallel_enabled is True

    @patch("pipeline.layer1_story.batch_generator.process_chapter_post_write")
    def test_progress_callback_called(self, mock_post_write):
        gen = _mock_generator(batch_size=5)
        gen._write_chapter_with_long_context.side_effect = (
            lambda *a, **kw: _make_chapter(a[5].chapter_number)
        )

        bg = BatchChapterGenerator(gen)
        draft = StoryDraft(
            title="T", genre="G", synopsis="S",
            characters=[], world=_WORLD, outlines=[],
        )
        outlines = [_make_outline(1)]
        ctx = StoryContext(total_chapters=1)
        progress = MagicMock()

        bg.generate_chapters(
            draft=draft, outlines=outlines, story_context=ctx,
            title="T", genre="G", style="S",
            characters=[], world=_WORLD,
            progress_callback=progress,
        )

        assert progress.call_count >= 3  # batch log + writing + extracting


class TestParallelBatch:
    @patch("pipeline.layer1_story.batch_generator.process_chapter_post_write")
    def test_parallel_generates_all_chapters(self, mock_post_write):
        gen = _mock_generator(batch_size=3, parallel=True)

        def fake_write(*args, **kwargs):
            outline = args[5]
            return _make_chapter(outline.chapter_number)

        gen._write_chapter_with_long_context.side_effect = fake_write

        bg = BatchChapterGenerator(gen)
        draft = StoryDraft(
            title="T", genre="G", synopsis="S",
            characters=[], world=_WORLD, outlines=[],
        )
        outlines = [_make_outline(i) for i in range(1, 6)]
        ctx = StoryContext(total_chapters=5)

        bg.generate_chapters(
            draft=draft, outlines=outlines, story_context=ctx,
            title="T", genre="G", style="S",
            characters=[], world=_WORLD,
        )

        assert len(draft.chapters) == 5
        assert mock_post_write.call_count == 5
        nums = [ch.chapter_number for ch in draft.chapters]
        assert nums == [1, 2, 3, 4, 5]

    @patch("pipeline.layer1_story.batch_generator.process_chapter_post_write")
    def test_parallel_post_processing_sequential(self, mock_post_write):
        gen = _mock_generator(batch_size=3, parallel=True)
        post_order = []

        def fake_write(*args, **kwargs):
            outline = args[5]
            return _make_chapter(outline.chapter_number)

        gen._write_chapter_with_long_context.side_effect = fake_write

        def fake_post(*args, **kwargs):
            chapter = args[0]
            post_order.append(chapter.chapter_number)

        mock_post_write.side_effect = fake_post

        bg = BatchChapterGenerator(gen)
        draft = StoryDraft(
            title="T", genre="G", synopsis="S",
            characters=[], world=_WORLD, outlines=[],
        )
        outlines = [_make_outline(i) for i in range(1, 4)]
        ctx = StoryContext(total_chapters=3)

        bg.generate_chapters(
            draft=draft, outlines=outlines, story_context=ctx,
            title="T", genre="G", style="S",
            characters=[], world=_WORLD,
        )

        assert post_order == [1, 2, 3]

    @patch("pipeline.layer1_story.batch_generator.process_chapter_post_write")
    def test_parallel_falls_back_to_sequential_with_stream(self, mock_post_write):
        gen = _mock_generator(batch_size=3, parallel=True)
        gen.write_chapter_stream.side_effect = lambda *a, **kw: _make_chapter(a[5].chapter_number)

        bg = BatchChapterGenerator(gen)
        draft = StoryDraft(
            title="T", genre="G", synopsis="S",
            characters=[], world=_WORLD, outlines=[],
        )
        outlines = [_make_outline(1)]
        ctx = StoryContext(total_chapters=1)

        bg.generate_chapters(
            draft=draft, outlines=outlines, story_context=ctx,
            title="T", genre="G", style="S",
            characters=[], world=_WORLD,
            stream_callback=MagicMock(),
        )

        gen.write_chapter_stream.assert_called_once()
        gen._write_chapter_with_long_context.assert_not_called()


class TestSiblingContext:
    def test_build_sibling_context_multiple(self):
        outlines = [_make_outline(1), _make_outline(2), _make_outline(3)]
        result = BatchChapterGenerator._build_sibling_context(outlines)
        assert "Ch1" in result
        assert "Ch2" in result
        assert "Ch3" in result

    def test_build_sibling_context_single(self):
        result = BatchChapterGenerator._build_sibling_context([_make_outline(1)])
        assert result == ""

    def test_build_sibling_context_empty(self):
        result = BatchChapterGenerator._build_sibling_context([])
        assert result == ""


class TestBatchCheckpointAndResume:
    @patch("pipeline.layer1_story.batch_generator.process_chapter_post_write")
    def test_checkpoint_callback_called_per_batch(self, mock_post_write):
        gen = _mock_generator(batch_size=2)
        gen._write_chapter_with_long_context.side_effect = (
            lambda *a, **kw: _make_chapter(a[5].chapter_number)
        )

        bg = BatchChapterGenerator(gen)
        draft = StoryDraft(
            title="T", genre="G", synopsis="S",
            characters=[], world=_WORLD, outlines=[],
        )
        outlines = [_make_outline(i) for i in range(1, 6)]
        ctx = StoryContext(total_chapters=5)
        checkpoint_cb = MagicMock()

        bg.generate_chapters(
            draft=draft, outlines=outlines, story_context=ctx,
            title="T", genre="G", style="S",
            characters=[], world=_WORLD,
            batch_checkpoint_callback=checkpoint_cb,
        )

        assert checkpoint_cb.call_count == 3  # 3 batches: [1,2], [3,4], [5]
        checkpoint_cb.assert_any_call(1, 3)
        checkpoint_cb.assert_any_call(2, 3)
        checkpoint_cb.assert_any_call(3, 3)

    @patch("pipeline.layer1_story.batch_generator.process_chapter_post_write")
    def test_resume_from_batch_skips_earlier(self, mock_post_write):
        gen = _mock_generator(batch_size=2)
        written_chapters = []

        def fake_write(*args, **kwargs):
            ch = _make_chapter(args[5].chapter_number)
            written_chapters.append(ch.chapter_number)
            return ch

        gen._write_chapter_with_long_context.side_effect = fake_write

        bg = BatchChapterGenerator(gen)
        draft = StoryDraft(
            title="T", genre="G", synopsis="S",
            characters=[], world=_WORLD, outlines=[],
        )
        outlines = [_make_outline(i) for i in range(1, 7)]
        ctx = StoryContext(total_chapters=6)

        bg.generate_chapters(
            draft=draft, outlines=outlines, story_context=ctx,
            title="T", genre="G", style="S",
            characters=[], world=_WORLD,
            resume_from_batch=2,
        )

        assert written_chapters == [5, 6]
        assert len(draft.chapters) == 2

    @patch("pipeline.layer1_story.batch_generator.process_chapter_post_write")
    def test_checkpoint_callback_failure_does_not_stop_generation(self, mock_post_write):
        gen = _mock_generator(batch_size=5)
        gen._write_chapter_with_long_context.side_effect = (
            lambda *a, **kw: _make_chapter(a[5].chapter_number)
        )

        def bad_checkpoint(*args):
            raise RuntimeError("disk full")

        bg = BatchChapterGenerator(gen)
        draft = StoryDraft(
            title="T", genre="G", synopsis="S",
            characters=[], world=_WORLD, outlines=[],
        )
        outlines = [_make_outline(i) for i in range(1, 4)]
        ctx = StoryContext(total_chapters=3)

        bg.generate_chapters(
            draft=draft, outlines=outlines, story_context=ctx,
            title="T", genre="G", style="S",
            characters=[], world=_WORLD,
            batch_checkpoint_callback=bad_checkpoint,
        )

        assert len(draft.chapters) == 3


class TestCausalAccumulator:
    """Tests for CausalAccumulator (#3 improvement)."""

    def test_add_and_get_events(self):
        from pipeline.layer1_story.batch_generator import CausalAccumulator
        acc = CausalAccumulator()
        acc.add_event(2, "plot", "Event 2")
        acc.add_event(1, "causal", "Event 1")
        acc.add_event(3, "twist", "Event 3")

        events = acc.get_events_sorted()
        assert len(events) == 3
        assert events[0]["chapter"] == 1
        assert events[1]["chapter"] == 2
        assert events[2]["chapter"] == 3

    def test_clear(self):
        from pipeline.layer1_story.batch_generator import CausalAccumulator
        acc = CausalAccumulator()
        acc.add_event(1, "test", "desc")
        acc.clear()
        assert acc.get_events_sorted() == []

    def test_thread_safe(self):
        from pipeline.layer1_story.batch_generator import CausalAccumulator
        import threading
        acc = CausalAccumulator()

        def add_events(start):
            for i in range(10):
                acc.add_event(start + i, "test", f"event {start + i}")

        threads = [threading.Thread(target=add_events, args=(i * 10,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        events = acc.get_events_sorted()
        assert len(events) == 50


class TestNewConfigFlags:
    """Tests for new config flags (#1, #2, #3)."""

    def test_reads_asyncio_flag(self):
        gen = _mock_generator(parallel=True)
        gen.config.pipeline.parallel_use_asyncio = True
        gen.config.pipeline.chapter_retry_max = 3
        gen.config.pipeline.chapter_retry_threshold = 0.7
        gen.config.pipeline.parallel_causal_sync = True

        bg = BatchChapterGenerator(gen)

        assert bg.use_asyncio is True
        assert bg.retry_max == 3
        assert bg.retry_threshold == 0.7
        assert bg.causal_sync is True

    def test_defaults_when_not_set(self):
        from config.defaults import PipelineConfig
        gen = _mock_generator()
        # Use real PipelineConfig to verify defaults
        gen.config.pipeline = PipelineConfig()

        bg = BatchChapterGenerator(gen)

        assert bg.use_asyncio is True  # default from PipelineConfig
        assert bg.retry_max == 2  # default from PipelineConfig
        assert bg.retry_threshold == 0.6  # default from PipelineConfig
        assert bg.causal_sync is True  # default from PipelineConfig


class TestAsyncBatch:
    """Tests for async batch execution (#1 improvement)."""

    def test_parallel_routes_to_async_or_threaded(self):
        gen = _mock_generator(parallel=True)
        gen.config.pipeline.parallel_use_asyncio = False
        gen.config.pipeline.enable_chapter_contracts = False
        gen.config.pipeline.enable_tiered_context = False
        gen.config.pipeline.enable_scene_decomposition = False
        gen.config.pipeline.enable_contract_validation = False
        gen._layer_model = "cheap"

        bg = BatchChapterGenerator(gen)

        # Mock the internal methods
        bg._run_batch_threaded = MagicMock(return_value=[_make_chapter(1)])
        bg._run_batch_async = MagicMock()

        frozen = FrozenContext(StoryContext(total_chapters=1), [])
        draft = StoryDraft(
            title="T", genre="G", synopsis="S",
            characters=[], world=_WORLD, outlines=[],
        )

        bg._run_batch_parallel(
            batch=[_make_outline(1)],
            frozen=frozen,
            draft=draft,
            story_context=StoryContext(total_chapters=1),
            all_chapter_texts=[],
            title="T", genre="G", style="S",
            characters=[], world=_WORLD,
            word_count=2000, context_window=5,
            executor=MagicMock(), self_reviewer=None,
            progress_callback=None,
        )

        # Should route to threaded when asyncio disabled
        bg._run_batch_threaded.assert_called_once()
        bg._run_batch_async.assert_not_called()


class TestDramaContractPassthrough:
    """Smoke tests: negotiated_contract is passed to write calls (Sprint 3 P2)."""

    @patch("pipeline.layer1_story.batch_generator.process_chapter_post_write")
    def test_negotiated_contract_passed_when_contract_built(self, mock_post_write):
        """When a contract is built, to_negotiated() result is passed to write call."""
        from unittest.mock import call
        gen = _mock_generator(batch_size=5)
        gen.config.pipeline.enable_chapter_contracts = True
        gen.config.pipeline.enable_proactive_constraints = False
        gen.config.pipeline.enable_thread_enforcement = False
        gen.config.pipeline.enable_l1_causal_graph = False
        gen.config.pipeline.enable_emotional_memory = False
        gen.config.pipeline.enable_foreshadowing_enforcement = False
        gen.config.pipeline.enable_scene_decomposition = False
        gen.config.pipeline.enable_scene_beat_writing = False
        gen.config.pipeline.rag_enabled = False
        gen.config.pipeline.story_bible_enabled = False
        gen.config.pipeline.enable_tiered_context = False
        gen._layer_model = "cheap"

        write_calls = []

        def fake_write(*args, **kwargs):
            write_calls.append(kwargs.get("negotiated_contract"))
            return _make_chapter(args[5].chapter_number)

        gen._write_chapter_with_long_context.side_effect = fake_write

        from models.handoff_schemas import NegotiatedChapterContract

        fake_negotiated = NegotiatedChapterContract(
            chapter_num=1, pacing_type="rising",
            drama_target=0.7, drama_tolerance=0.15, drama_ceiling=0.85,
        )
        fake_contract = MagicMock()
        fake_contract.to_negotiated.return_value = fake_negotiated

        bg = BatchChapterGenerator(gen)
        draft = StoryDraft(
            title="T", genre="G", synopsis="S",
            characters=[], world=_WORLD, outlines=[],
        )
        outlines = [_make_outline(1)]
        ctx = StoryContext(total_chapters=1)

        with patch(
            "pipeline.layer1_story.chapter_contract_builder.build_contract",
            return_value=fake_contract,
        ), patch(
            "pipeline.layer1_story.chapter_contract_builder.format_contract_for_prompt",
            return_value="contract text",
        ):
            bg.generate_chapters(
                draft=draft, outlines=outlines, story_context=ctx,
                title="T", genre="G", style="S",
                characters=[], world=_WORLD,
            )

        assert len(write_calls) == 1
        assert write_calls[0] is fake_negotiated

    @patch("pipeline.layer1_story.batch_generator.process_chapter_post_write")
    def test_negotiated_contract_none_when_no_contract(self, mock_post_write):
        """When contracts disabled, negotiated_contract=None is passed."""
        gen = _mock_generator(batch_size=5)
        gen.config.pipeline.enable_chapter_contracts = False
        gen.config.pipeline.enable_thread_enforcement = False
        gen.config.pipeline.enable_l1_causal_graph = False
        gen.config.pipeline.enable_emotional_memory = False
        gen.config.pipeline.enable_foreshadowing_enforcement = False
        gen.config.pipeline.enable_scene_decomposition = False
        gen.config.pipeline.enable_scene_beat_writing = False
        gen.config.pipeline.rag_enabled = False
        gen.config.pipeline.story_bible_enabled = False
        gen.config.pipeline.enable_tiered_context = False
        gen._layer_model = "cheap"

        write_calls = []

        def fake_write(*args, **kwargs):
            write_calls.append(kwargs.get("negotiated_contract"))
            return _make_chapter(args[5].chapter_number)

        gen._write_chapter_with_long_context.side_effect = fake_write

        bg = BatchChapterGenerator(gen)
        draft = StoryDraft(
            title="T", genre="G", synopsis="S",
            characters=[], world=_WORLD, outlines=[],
        )
        outlines = [_make_outline(1)]
        ctx = StoryContext(total_chapters=1)

        bg.generate_chapters(
            draft=draft, outlines=outlines, story_context=ctx,
            title="T", genre="G", style="S",
            characters=[], world=_WORLD,
        )

        assert len(write_calls) == 1
        assert write_calls[0] is None
