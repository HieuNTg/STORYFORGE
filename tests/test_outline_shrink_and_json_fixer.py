"""P0 found by the Batch K smoke run (2026-09-14): 5 chapters asked, 2 written.

The chain, from the real run's log:

1. ``revise_outline_from_critique`` got 18,871 completion tokens back. The JSON
   held a raw newline inside a string, which ``json.loads`` rejects as an
   "Invalid control character".
2. ``_repair_json`` does not handle that, so ``generate_json`` handed its LLM
   fixer ``text[:4000]`` -- the head of a far longer response.
3. The fixer returned *valid* JSON holding 2 chapters.
4. ``revise_outline_from_critique`` only refused an *empty* revision, so the
   2-chapter outline replaced the 5-chapter one, and the story was reported done.

Each guard below closes one link. Any one of them would have saved that run.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from models.schemas import Character, ChapterOutline


# --------------------------------------------------------------------------
# generate_json: a GenerationMixin host that counts calls instead of making them
# --------------------------------------------------------------------------


class _Recorder:
    def __init__(self, main_text: str, fixer_reply: str = '{"fixed": true}'):
        self.main_text = main_text
        self.fixer_reply = fixer_reply
        self.fixer_inputs: list[str] = []

    def _generate_json_text(self, *a, **k):
        return self.main_text

    def generate(self, *a, user_prompt: str = "", **k):
        self.fixer_inputs.append(user_prompt)
        return self.fixer_reply


def _subject(main_text: str, fixer_reply: str = '{"fixed": true}'):
    from services.llm.generation import GenerationMixin

    class Subject(_Recorder, GenerationMixin):
        pass

    return Subject(main_text, fixer_reply)


class TestRawControlCharactersParseWithoutTheLLM:
    def test_raw_newline_in_string_parses_without_llm(self):
        """The exact failure of the smoke run: a literal newline inside a string."""
        text = '{"outlines": [{"title": "Chương 1", "summary": "dòng một\ndòng hai"}]}'
        subject = _subject(text)

        result = subject.generate_json("sys", "user", expect="dict")

        assert result["outlines"][0]["summary"] == "dòng một\ndòng hai"
        assert subject.fixer_inputs == [], "a parseable response must not reach the fixer"

    def test_raw_tab_in_string_parses_without_llm(self):
        subject = _subject('{"a": "x\ty"}')

        assert subject.generate_json("sys", "user") == {"a": "x\ty"}
        assert subject.fixer_inputs == []


class TestFixerNeverSeesATruncatedText:
    @staticmethod
    def _long_malformed() -> str:
        # Unparseable even after _repair_json: the array and the object never close.
        items = ", ".join('{"k": "value"}' for _ in range(500))
        text = '{"items": [' + items + ', {"k": "val'
        assert len(text) > 6000
        return text

    def test_json_fixer_never_receives_truncated_text(self):
        """Sending the fixer the head of a long response returns a SHORTER valid
        document -- silent data loss. Refuse instead, with the length in the error."""
        subject = _subject(self._long_malformed())

        with pytest.raises(ValueError, match="chars"):
            subject.generate_json("sys", "user")

        assert subject.fixer_inputs == [], (
            "the fixer was sent a truncated head of the response"
        )

    def test_a_short_malformed_response_still_gets_its_repair(self):
        """The guard bounds what the fixer may see; it must not remove the fixer."""
        subject = _subject("not json at all, just prose")

        assert subject.generate_json("sys", "user") == {"fixed": True}
        assert len(subject.fixer_inputs) == 1


# --------------------------------------------------------------------------
# revise_outline_from_critique: a revision must keep every chapter
# --------------------------------------------------------------------------


def _outline(n: int) -> ChapterOutline:
    return ChapterOutline(chapter_number=n, title=f"Chương {n}", summary=f"Tóm tắt {n}")


def _payload(count: int) -> dict:
    return {
        "outlines": [
            {"chapter_number": n, "title": f"Mới {n}", "summary": f"Sửa {n}"}
            for n in range(1, count + 1)
        ]
    }


def _revise(llm_payload: dict, originals: list[ChapterOutline]):
    from pipeline.layer1_story.outline_critic import revise_outline_from_critique

    llm = MagicMock()
    llm.generate_json.return_value = llm_payload
    world = MagicMock()
    world.name = "W"
    world.description = "d"
    return revise_outline_from_critique(
        llm,
        originals,
        {"overall_score": 3},
        [Character(name="Nguyễn Thị Hạnh", role="chính")],
        world,
        "Tâm lý xã hội",
    )


class TestRevisionKeepsEveryChapter:
    def test_revised_outline_with_fewer_chapters_is_rejected(self):
        """The smoke run: 5 in, 2 back, and the 2 were kept."""
        originals = [_outline(n) for n in range(1, 6)]

        result = _revise(_payload(2), originals)

        assert result is originals, (
            f"a revision dropped {5 - len(result)} of 5 chapters and was accepted"
        )

    def test_revised_outline_with_more_chapters_is_rejected(self):
        originals = [_outline(n) for n in range(1, 4)]

        assert _revise(_payload(6), originals) is originals

    def test_a_full_revision_is_still_accepted(self):
        originals = [_outline(n) for n in range(1, 6)]

        result = _revise(_payload(5), originals)

        assert [o.title for o in result] == [f"Mới {n}" for n in range(1, 6)]


def test_payload_helper_is_valid_json():
    """Guard the fixture itself: the payloads above must round-trip."""
    assert json.loads(json.dumps(_payload(3)))["outlines"][2]["chapter_number"] == 3
