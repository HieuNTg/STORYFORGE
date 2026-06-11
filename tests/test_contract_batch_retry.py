"""Unit tests for pipeline.layer1_story.contract_batch_retry.

Covers the shared batch contract-validation helper that both the threaded
path and (since the async dedupe) _run_batch_async delegate to: gating,
the no-retry happy path, the rebuild-and-rewrite retry loop, the retry_max
cap, and non-fatal validation failures.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from pipeline.layer1_story.contract_batch_retry import validate_and_retry_threaded


def _chapter(num: int = 1, content: str = "nội dung gốc") -> SimpleNamespace:
    return SimpleNamespace(chapter_number=num, content=content)


def _outline(num: int = 1) -> SimpleNamespace:
    return SimpleNamespace(chapter_number=num)


def _batch_gen(validation: bool = True, retry_max: int = 2) -> SimpleNamespace:
    return SimpleNamespace(
        llm=object(),
        config=SimpleNamespace(
            pipeline=SimpleNamespace(enable_contract_validation=validation)
        ),
        gen=SimpleNamespace(_layer_model="cheap"),
        retry_threshold=0.6,
        retry_max=retry_max,
        _write_chapter_parallel=MagicMock(
            return_value=(_chapter(content="nội dung viết lại"), None)
        ),
    )


def _call(batch_gen, chapters, contracts, progress_callback=None):
    return validate_and_retry_threaded(
        batch_gen,
        chapters=chapters,
        contracts=contracts,
        batch=[_outline()],
        frozen=None,
        draft=None,
        story_context=None,
        frozen_threads=[],
        sibling_summaries="",
        shared_enhancement="",
        title="Kiếm Đạo",
        genre="tiên hiệp",
        style="cổ trang",
        characters=[],
        world=None,
        word_count=1000,
        macro_arcs=None,
        conflict_web=None,
        foreshadowing_plan=None,
        progress_callback=progress_callback,
    )


class TestGating:
    def test_no_contracts_returns_chapters_unchanged(self):
        chapters = [_chapter()]
        result = _call(_batch_gen(), chapters, contracts={})
        assert result is chapters

    def test_flag_disabled_returns_chapters_unchanged(self):
        chapters = [_chapter()]
        with patch(
            "pipeline.layer1_story.chapter_contract_builder.validate_contract_compliance"
        ) as mock_validate:
            result = _call(
                _batch_gen(validation=False), chapters, contracts={1: object()}
            )
            mock_validate.assert_not_called()
        assert result is chapters


class TestCompliantPath:
    def test_above_threshold_skips_retry(self):
        batch_gen = _batch_gen()
        progress = MagicMock()
        with patch(
            "pipeline.layer1_story.chapter_contract_builder.validate_contract_compliance",
            return_value={"compliance_score": 0.9, "failures": []},
        ):
            result = _call(
                batch_gen,
                [_chapter()],
                contracts={1: object()},
                progress_callback=progress,
            )
        batch_gen._write_chapter_parallel.assert_not_called()
        assert result[0].content == "nội dung gốc"
        progress.assert_called_once_with("Ch1 compliance: 90%")


class TestRetryLoop:
    def test_below_threshold_rebuilds_and_rewrites(self):
        batch_gen = _batch_gen()
        with (
            patch(
                "pipeline.layer1_story.chapter_contract_builder.validate_contract_compliance",
                side_effect=[
                    {"compliance_score": 0.3, "failures": ["thiếu sự kiện"]},
                    {"compliance_score": 0.9, "failures": []},
                ],
            ),
            patch(
                "pipeline.layer1_story.chapter_contract_builder.build_contract"
            ) as mock_build,
        ):
            result = _call(batch_gen, [_chapter()], contracts={1: object()})
        assert mock_build.call_args.kwargs["previous_failures"] == ["thiếu sự kiện"]
        batch_gen._write_chapter_parallel.assert_called_once()
        assert result[0].content == "nội dung viết lại"

    def test_retry_capped_at_retry_max(self):
        batch_gen = _batch_gen(retry_max=2)
        with (
            patch(
                "pipeline.layer1_story.chapter_contract_builder.validate_contract_compliance",
                return_value={"compliance_score": 0.3, "failures": ["vẫn lệch"]},
            ),
            patch("pipeline.layer1_story.chapter_contract_builder.build_contract"),
        ):
            _call(batch_gen, [_chapter()], contracts={1: object()})
        assert batch_gen._write_chapter_parallel.call_count == 2


class TestBestEffortFailure:
    def test_validation_exception_keeps_original_chapter(self, caplog):
        batch_gen = _batch_gen()
        chapters = [_chapter()]
        with patch(
            "pipeline.layer1_story.chapter_contract_builder.validate_contract_compliance",
            side_effect=RuntimeError("boom"),
        ):
            result = _call(batch_gen, chapters, contracts={1: object()})
        assert result[0].content == "nội dung gốc"
        assert any("Contract validation failed" in r.message for r in caplog.records)
