"""Sprint 2 — character-state extraction must not be strictly serial.

`extract_states_from_chapter` issued one cheap LLM call per character, one after
another, against the same 5000-character excerpt. On a 10-chapter, 5-character
story that is ~50 serial calls and it set the wall-clock floor of the whole
consistency engine, while every other L2 stage was already gathered.

The prompt is unchanged: this is a scheduling fix, not a quality one. Batching
all characters into a single call would cut cost as well, but changes the
prompt and its parsed shape, so it belongs in its own measured change.
"""

import threading
from unittest.mock import MagicMock, patch

from pipeline.layer2_enhance.character_state_registry import CharacterStateRegistry
from tests.concurrency_probe import InFlightProbe


CONTENT = "Lan và Minh và Hoa cùng bước vào khu rừng. " * 20


def _subject(kwargs) -> str:
    """The character a call is extracting, read from the prompt's first line.

    The chapter content names every character, so matching anywhere in the
    prompt identifies all of them — only the quoted slot is specific.
    """
    first_line = kwargs.get("user_prompt", "").splitlines()[0] if kwargs.get(
        "user_prompt"
    ) else ""
    return first_line.split('"')[1] if '"' in first_line else ""


def _registry(side_effect=None, probe=None):
    with patch("pipeline.layer2_enhance.character_state_registry.LLMClient"):
        reg = CharacterStateRegistry()
    llm = MagicMock()

    def _call(*args, **kwargs):
        if probe:
            with probe:
                pass
        if side_effect:
            return side_effect(*args, **kwargs)
        return {"location": "khu rừng", "emotional_state": "căng thẳng"}

    llm.generate_json.side_effect = _call
    reg.llm = llm
    return reg


class TestExtractionRunsConcurrently:
    def test_three_characters_are_not_extracted_one_after_another(self):
        probe = InFlightProbe(rendezvous=3)
        reg = _registry(probe=probe)

        reg.extract_states_from_chapter(CONTENT, 1, ["Lan", "Minh", "Hoa"])

        assert probe.peak == 3, f"only {probe.peak} extraction call(s) overlapped"

    def test_every_present_character_is_extracted(self):
        reg = _registry()
        states = reg.extract_states_from_chapter(CONTENT, 1, ["Lan", "Minh", "Hoa"])
        assert {s.name for s in states} == {"Lan", "Minh", "Hoa"}

    def test_absent_characters_are_skipped_without_a_call(self):
        reg = _registry()
        reg.extract_states_from_chapter(CONTENT, 1, ["Lan", "KhôngCóMặt"])
        assert reg.llm.generate_json.call_count == 1

    def test_order_is_deterministic_not_completion_order(self):
        """Results must not depend on which thread finished first."""
        order = ["Lan", "Minh", "Hoa"]
        others_done = threading.Semaphore(0)

        def staggered(*args, **kwargs):
            # The subject appears in the quoted slot on line 1: nhân vật "Lan".
            if _subject(kwargs) == "Lan":
                # Finish last, yet must still come back first.
                for _ in order[1:]:
                    others_done.acquire(timeout=10)
            else:
                others_done.release()
            return {"location": "x"}

        reg = _registry(side_effect=staggered)
        states = reg.extract_states_from_chapter(CONTENT, 1, order)
        assert [s.name for s in states] == order


class TestSharedStateIsSafe:
    def test_registry_is_merged_without_loss(self):
        reg = _registry()
        reg.extract_states_from_chapter(CONTENT, 1, ["Lan", "Minh", "Hoa"])
        reg.extract_states_from_chapter(CONTENT, 2, ["Lan", "Minh", "Hoa"])

        for name in ("Lan", "Minh", "Hoa"):
            assert set(reg.states[name]) == {1, 2}, f"{name} lost a chapter"

    def test_concurrent_chapters_do_not_corrupt_the_registry(self):
        reg = _registry()

        def run(ch):
            reg.extract_states_from_chapter(CONTENT, ch, ["Lan", "Minh", "Hoa"])

        threads = [threading.Thread(target=run, args=(n,)) for n in range(1, 6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        for name in ("Lan", "Minh", "Hoa"):
            assert set(reg.states[name]) == {1, 2, 3, 4, 5}


class TestFailuresStayNonFatal:
    def test_one_character_failing_does_not_lose_the_others(self):
        def flaky(*args, **kwargs):
            if _subject(kwargs) == "Minh":
                raise RuntimeError("provider 503")
            return {"location": "khu rừng"}

        reg = _registry(side_effect=flaky)
        states = reg.extract_states_from_chapter(CONTENT, 1, ["Lan", "Minh", "Hoa"])

        assert {s.name for s in states} == {"Lan", "Hoa"}

    def test_all_failing_returns_empty_without_raising(self):
        def always_fail(*args, **kwargs):
            raise RuntimeError("down")

        reg = _registry(side_effect=always_fail)
        assert reg.extract_states_from_chapter(CONTENT, 1, ["Lan", "Minh"]) == []

    def test_no_characters_present_makes_no_calls(self):
        reg = _registry()
        assert reg.extract_states_from_chapter("nội dung khác", 1, ["Lan"]) == []
        assert reg.llm.generate_json.call_count == 0
