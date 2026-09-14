"""Batch L, step L2: the storyboard must cover the whole chapter.

`ShotListExtractor.extract` sent the LLM `chapter.content[:CONTENT_WINDOW]`
(8,000 chars), and the coverage verifier read the same window, so nothing ever
noticed the rest was missing. Measured on the 2026-09-14 smoke run: 4 of 7
chapters were longer than the window, one by 14,500 chars — no panel for most
of that chapter could exist.

Now the chapter is cut at paragraph boundaries into window-sized chunks. Each
chunk after the first is told the last panel of the one before, so placement
and appearance carry over, and panel numbers run on. A chunk whose response is
too long to repair is split in half and retried, instead of the whole chapter
falling back to the legacy image path.
"""

from __future__ import annotations

import re
import types

import pytest

from models.schemas import Chapter
from services.media import shot_list as sl_mod
from services.media.shot_list import CONTENT_WINDOW, ShotListExtractor

_MARK = re.compile(r"ĐOẠN(\d+)")


def _paragraph(i: int, words: int = 1200) -> str:
    return f"ĐOẠN{i} " + "chữ " * words


def _chapter(paragraphs: list[str]) -> Chapter:
    return Chapter(chapter_number=3, title="Chương dài", content="\n\n".join(paragraphs))


def _content_section(user_prompt: str) -> str:
    """Only the prose handed to the model — not the carried-over panel note."""
    return user_prompt.split("NỘI DUNG:", 1)[-1].split("NHÂN VẬT:", 1)[0]


class _FakeLLM:
    """Returns one panel per paragraph marker found in the chunk it was given."""

    def __init__(self, fail_when=None):
        self.prompts: list[str] = []
        self.coverage_prompts: list[str] = []
        self.fail_when = fail_when

    def generate_json(self, system_prompt="", user_prompt="", list_key=None, **kwargs):
        if list_key == "missing":
            self.coverage_prompts.append(user_prompt)
            return {"missing": []}
        self.prompts.append(user_prompt)
        markers = _MARK.findall(_content_section(user_prompt))
        if self.fail_when and self.fail_when(markers):
            from services.llm.generation import JSONTooLongToRepairError

            raise JSONTooLongToRepairError("JSON parse failed on a 9000-chars response")
        panels = [
            {
                "n": k + 1,
                "shot": "MS",
                "beat": f"beat {m}",
                "subject": f"Nhân vật {m}",
                "setting": f"bối cảnh {m}",
                "action": f"hành động {m}",
                "screen_side": {f"Nhân vật {m}": "left"},
                "bubbles": [],
                "captions": [],
            }
            for k, m in enumerate(markers)
        ]
        return {"pages": [{"page": 1, "layout": "THREE_TIER", "panels": panels}]}


def _extract(chapter, llm, **kwargs):
    extractor = ShotListExtractor.__new__(ShotListExtractor)
    extractor.llm = types.SimpleNamespace(generate_json=llm.generate_json)
    return extractor.extract(chapter, num_panels=8, **kwargs)


def test_long_chapter_every_paragraph_reaches_llm():
    chapter = _chapter([_paragraph(i) for i in range(1, 5)])  # ~19k chars
    assert len(chapter.content) > 2 * CONTENT_WINDOW
    llm = _FakeLLM()

    shots = _extract(chapter, llm)

    seen = {m for p in llm.prompts for m in _MARK.findall(_content_section(p))}
    assert seen == {"1", "2", "3", "4"}, f"never storyboarded: {sorted({'1','2','3','4'} - seen)}"
    assert [p.beat for p in shots.all_panels()] == ["beat 1", "beat 2", "beat 3", "beat 4"]


def test_no_chunk_exceeds_the_window():
    llm = _FakeLLM()
    _extract(_chapter([_paragraph(i) for i in range(1, 5)]), llm)

    assert llm.prompts, "no call was made"
    assert all(len(_content_section(p).strip()) <= CONTENT_WINDOW for p in llm.prompts)


def test_panel_numbering_continuous_across_chunks():
    shots = _extract(_chapter([_paragraph(i) for i in range(1, 5)]), _FakeLLM())

    assert [p.n for p in shots.all_panels()] == [1, 2, 3, 4]


def test_second_chunk_prompt_carries_previous_panel():
    llm = _FakeLLM()
    _extract(_chapter([_paragraph(i) for i in range(1, 4)]), llm)

    assert len(llm.prompts) >= 2
    second = llm.prompts[1]
    assert "Nhân vật 1" in second and "bối cảnh 1" in second, "last panel of chunk 1 not carried over"
    assert "Nhân vật 1" not in _content_section(second), "carry-over must not be passed off as prose"


def test_coverage_check_sees_chapter_tail():
    llm = _FakeLLM()
    _extract(_chapter([_paragraph(i) for i in range(1, 5)]), llm, coverage_check=True)

    verified = {m for p in llm.coverage_prompts for m in _MARK.findall(p)}
    assert "4" in verified, "the verifier never read the end of the chapter"


def test_too_long_response_splits_chunk_and_keeps_both_halves():
    # One chunk holding two paragraphs; the model "fails" whenever it is handed both.
    paragraphs = [_paragraph(1, words=700), _paragraph(2, words=700)]
    llm = _FakeLLM(fail_when=lambda markers: {"1", "2"} <= set(markers))

    shots = _extract(_chapter(paragraphs), llm)

    assert [p.beat for p in shots.all_panels()] == ["beat 1", "beat 2"]


def test_unsplittable_failure_degrades_to_empty_shot_list():
    llm = _FakeLLM(fail_when=lambda markers: True)

    shots = _extract(_chapter(["ĐOẠN1 ngắn."]), llm)

    assert shots.pages == []


def test_short_chapter_single_call_unchanged():
    llm = _FakeLLM()
    shots = _extract(_chapter(["ĐOẠN1 Một đoạn ngắn.", "ĐOẠN2 Một đoạn nữa."]), llm)

    assert len(llm.prompts) == 1
    assert "TIẾP NỐI" not in llm.prompts[0]
    assert len(shots.all_panels()) == 2


def test_too_long_to_repair_is_still_a_value_error():
    """Every existing caller catches ValueError; the new type must not escape them."""
    from services.llm.generation import JSONTooLongToRepairError

    assert issubclass(JSONTooLongToRepairError, ValueError)


@pytest.mark.parametrize("n", [1, 7])
def test_chunker_keeps_all_text(n):
    text = "\n\n".join(_paragraph(i, words=900) for i in range(n))
    chunks = sl_mod._chunk_by_paragraph(text, CONTENT_WINDOW)
    assert all(len(c) <= CONTENT_WINDOW for c in chunks)
    assert re.sub(r"\s+", "", "".join(chunks)) == re.sub(r"\s+", "", text)
