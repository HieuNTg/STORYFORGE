"""Unit tests for pipeline.layer1_story.sequential_write_dispatch.

Covers the chapter-write dispatch extracted from _run_batch_sequential:
beat-chapter short-circuit, stream vs long-context path selection, contract
attachment, and the token-budget warning.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from pipeline.layer1_story.sequential_write_dispatch import write_sequential_chapter


def _chapter(content: str = "nội dung chương") -> SimpleNamespace:
    return SimpleNamespace(chapter_number=3, content=content)


def _batch_gen(token_budget: int = 100_000) -> SimpleNamespace:
    gen = MagicMock()
    gen.token_budget_per_chapter = token_budget
    gen.write_chapter_stream.return_value = _chapter("từ stream")
    gen._write_chapter_with_long_context.return_value = _chapter("từ long context")
    return SimpleNamespace(gen=gen)


def _call(batch_gen, **overrides):
    kwargs = dict(
        outline=SimpleNamespace(chapter_number=3, title="Chương 3"),
        contract=None,
        contract_text="",
        beat_chapter=None,
        stream_callback=None,
        title="Kiếm Đạo",
        genre="tiên hiệp",
        style="cổ trang",
        characters=[],
        world=None,
        word_count=1000,
        story_context=SimpleNamespace(open_threads=[]),
        all_chapter_texts=[],
        bible_ctx="",
        active_conflicts=[],
        seeds=[],
        payoffs=[],
        pacing="rising",
        enhancement_context="",
        arc_context="",
        chapter_scenes=[],
    )
    kwargs.update(overrides)
    return write_sequential_chapter(batch_gen, **kwargs)


class TestPathSelection:
    def test_beat_chapter_short_circuits_writers(self):
        batch_gen = _batch_gen()
        beat = _chapter("đã viết theo nhịp")
        result = _call(batch_gen, beat_chapter=beat)
        assert result is beat
        batch_gen.gen.write_chapter_stream.assert_not_called()
        batch_gen.gen._write_chapter_with_long_context.assert_not_called()

    def test_stream_callback_selects_stream_writer(self):
        batch_gen = _batch_gen()
        result = _call(batch_gen, stream_callback=lambda *_: None)
        assert result.content == "từ stream"
        batch_gen.gen._write_chapter_with_long_context.assert_not_called()

    def test_default_selects_long_context_writer(self):
        batch_gen = _batch_gen()
        result = _call(batch_gen)
        assert result.content == "từ long context"
        batch_gen.gen.write_chapter_stream.assert_not_called()


class TestContractAttachment:
    def test_contract_and_negotiated_attached(self):
        batch_gen = _batch_gen()
        negotiated = object()
        contract = MagicMock()
        contract.to_negotiated.return_value = negotiated
        result = _call(batch_gen, contract=contract, contract_text="HỢP ĐỒNG")
        assert result.contract is contract
        assert result.negotiated_contract is negotiated
        # negotiated contract is also forwarded to the writer
        kwargs = batch_gen.gen._write_chapter_with_long_context.call_args.kwargs
        assert kwargs["negotiated_contract"] is negotiated
        assert kwargs["chapter_contract"] == "HỢP ĐỒNG"

    def test_attach_failure_is_non_fatal(self):
        batch_gen = _batch_gen()
        contract = MagicMock()
        contract.to_negotiated.side_effect = [object(), RuntimeError("boom")]
        result = _call(batch_gen, contract=contract)
        assert result.content == "từ long context"


class TestTokenBudgetWarning:
    def test_warns_when_budget_nearly_spent(self, caplog):
        _call(_batch_gen(token_budget=1))
        assert any("token budget" in r.message for r in caplog.records)

    def test_no_warning_under_threshold(self, caplog):
        _call(_batch_gen(token_budget=1_000_000))
        assert not any("token budget" in r.message for r in caplog.records)
