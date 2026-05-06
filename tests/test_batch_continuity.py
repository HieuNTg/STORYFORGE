"""Tests for l1_strict_chapter_continuity flag.

The flag forces sequential within-batch execution so each chapter's
continuity anchor (last ~300 words) is its immediate predecessor's tail,
not the stale prior-batch tail shared across siblings in parallel mode.
"""

from unittest.mock import MagicMock, patch

from pipeline.layer1_story.batch_generator import BatchChapterGenerator
from models.schemas import StoryContext, StoryDraft, ChapterOutline, Chapter, WorldSetting


_WORLD = WorldSetting(name="TestWorld", description="A test world")


def _make_outline(num: int) -> ChapterOutline:
    return ChapterOutline(chapter_number=num, title=f"Chapter {num}", summary=f"Summary {num}")


def _make_chapter(num: int) -> Chapter:
    return Chapter(
        chapter_number=num,
        title=f"Chapter {num}",
        content=f"CONTENT_OF_CH{num}",
        word_count=100,
    )


def _mock_generator(batch_size=5, parallel=True, strict=False):
    gen = MagicMock()
    gen.config.pipeline.chapter_batch_size = batch_size
    gen.config.pipeline.parallel_chapters_enabled = parallel
    gen.config.pipeline.parallel_use_asyncio = True
    gen.config.pipeline.l1_strict_chapter_continuity = strict
    gen.config.pipeline.context_window_chapters = 5
    gen.config.pipeline.story_bible_enabled = False
    gen.config.pipeline.enable_self_review = False
    gen.token_budget_per_chapter = 4000
    return gen


def _captured_anchors_for(strict: bool) -> dict[int, list[str]]:
    """Run a single batch of 3 chapters with the given strict flag.

    Returns {chapter_number: list_of_chapter_texts_seen_at_write_time}.
    The "anchor" is `all_chapter_texts[-1]` if the list is non-empty.
    """
    gen = _mock_generator(batch_size=3, parallel=True, strict=strict)
    captured: dict[int, list[str]] = {}

    def fake_write(*args, **kwargs):
        # signature: (title, genre, style, characters, world, outline,
        #             word_count, story_context, all_chapter_texts, bible_ctx, ...)
        outline = args[5]
        all_texts = args[8]
        captured[outline.chapter_number] = list(all_texts)  # snapshot at call time
        return _make_chapter(outline.chapter_number)

    gen._write_chapter_with_long_context.side_effect = fake_write
    # Strict mode routes through sequential path which can also call write_chapter_stream;
    # parallel path only uses _write_chapter_with_long_context.
    gen.write_chapter_stream.side_effect = lambda *a, **kw: _make_chapter(a[5].chapter_number)

    bg = BatchChapterGenerator(gen)
    draft = StoryDraft(
        title="T", genre="G", synopsis="S",
        characters=[], world=_WORLD, outlines=[],
    )
    outlines = [_make_outline(i) for i in range(1, 4)]  # single batch of 3
    ctx = StoryContext(total_chapters=3)

    with patch("pipeline.layer1_story.batch_generator.process_chapter_post_write"):
        bg.generate_chapters(
            draft=draft, outlines=outlines, story_context=ctx,
            title="T", genre="G", style="S",
            characters=[], world=_WORLD, word_count=2000,
        )
    return captured


class TestStrictContinuityFlag:
    def test_default_is_false(self):
        from config import PipelineConfig
        pc = PipelineConfig()
        assert pc.l1_strict_chapter_continuity is False

    def test_flag_loaded_into_batch_generator(self):
        gen = _mock_generator(strict=True)
        bg = BatchChapterGenerator(gen)
        assert bg.strict_continuity is True

    def test_parallel_mode_all_siblings_see_same_anchor(self):
        """With strict=False (default) parallel mode: all chapters in a single
        batch see the same (frozen) chapter_texts — empty here since this is
        the first batch. The behaviour we assert: the captured snapshot for
        each chapter is identical."""
        captured = _captured_anchors_for(strict=False)
        assert set(captured.keys()) == {1, 2, 3}
        # All three should see the same prior-batch snapshot (empty for first batch)
        assert captured[1] == captured[2] == captured[3]

    def test_strict_mode_each_chapter_sees_predecessor_tail(self):
        """With strict=True: chapter N's all_chapter_texts must contain
        chapter N-1's content, accumulated within the batch."""
        captured = _captured_anchors_for(strict=True)
        assert set(captured.keys()) == {1, 2, 3}

        # Chapter 1: nothing before it in the batch
        assert captured[1] == []
        # Chapter 2: must see chapter 1's content as last entry
        assert captured[2] and captured[2][-1] == "CONTENT_OF_CH1"
        # Chapter 3: must see chapter 2's content as last entry
        assert captured[3] and captured[3][-1] == "CONTENT_OF_CH2"
