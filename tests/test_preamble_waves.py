"""Sprint 2 — the L1 preamble ran independent calls one after another.

Before chapter writing begins, `generate_full_story` made a run of one-off LLM
calls in a strict line. Three of them (idea summary, theme/premise, characters)
read only the raw request; three more (voice profiles, world, arc waypoints)
read only the cast. Nothing in either group needed anything from its siblings,
yet each waited for the one before it — a minute or more of dead time per run,
before a single chapter existed.

Two properties make this safe rather than merely faster, and both are tested
here because getting either wrong is silent:

- Each task runs in its own copied context. The trace layer keeps per-call
  attribution in contextvars; siblings sharing one context corrupt token and
  cost accounting rather than failing.
- Results come back, they are not applied. Voice profiles and arc waypoints
  both write into the shared `characters` list, so those writes must happen on
  the calling thread after every reader is finished.
"""

import ast
import contextvars
import inspect
import threading
import time
from types import SimpleNamespace

import pytest

from pipeline.layer1_story.generator import StoryGenerator


def _gen(max_parallel_workers: int = 4) -> StoryGenerator:
    gen = StoryGenerator.__new__(StoryGenerator)
    gen.config = SimpleNamespace(
        llm=SimpleNamespace(max_parallel_workers=max_parallel_workers)
    )
    return gen


class TestTheWaveRunsConcurrently:
    def test_three_slow_tasks_do_not_serialise(self):
        def slow(value):
            def _run():
                time.sleep(0.15)
                return value

            return _run

        started = time.monotonic()
        results = _gen()._run_preamble_wave(
            [("a", slow(1)), ("b", slow(2)), ("c", slow(3))]
        )
        elapsed = time.monotonic() - started

        assert dict(results) == {"a": 1, "b": 2, "c": 3}
        assert elapsed < 0.35, f"serial would take ~0.45s, took {elapsed:.2f}s"

    def test_every_task_is_reported_by_name(self):
        results = _gen()._run_preamble_wave(
            [("world", lambda: "w"), ("premise", lambda: {"p": 1})]
        )
        assert dict(results) == {"world": "w", "premise": {"p": 1}}

    def test_an_empty_wave_is_not_an_error(self):
        assert _gen()._run_preamble_wave([]) == []

    def test_worker_count_honours_max_parallel_workers(self):
        """A wave must not be the one place the provider limit is ignored."""
        live = 0
        peak = 0
        lock = threading.Lock()

        def task():
            nonlocal live, peak
            with lock:
                live += 1
                peak = max(peak, live)
            time.sleep(0.05)
            with lock:
                live -= 1

        _gen(max_parallel_workers=1)._run_preamble_wave(
            [(str(i), task) for i in range(4)]
        )
        assert peak == 1, f"{peak} ran at once against a limit of 1"


class TestFailureHandlingMatchesTheInlineCode:
    def test_a_non_critical_failure_is_dropped_not_raised(self):
        results = _gen()._run_preamble_wave(
            [("premise", lambda: 1 / 0), ("world", lambda: "w")]
        )
        assert dict(results) == {"world": "w"}

    def test_a_critical_failure_comes_back_for_the_caller_to_raise(self):
        """Critical steps must still abort the run, on the calling thread."""
        boom = RuntimeError("provider down")

        def fail():
            raise boom

        results = dict(
            _gen()._run_preamble_wave([("world", fail)], critical={"world"})
        )
        assert results["world"] is boom

    def test_one_failure_does_not_lose_its_siblings(self):
        results = _gen()._run_preamble_wave(
            [("a", lambda: 1 / 0), ("b", lambda: "kept"), ("c", lambda: "kept too")]
        )
        assert dict(results) == {"b": "kept", "c": "kept too"}


class TestContextIsolation:
    def test_a_worker_cannot_leak_a_contextvar_to_its_caller(self):
        """Trace attribution lives in contextvars; a leak corrupts cost data."""
        var = contextvars.ContextVar("preamble_probe", default="caller")

        def setter():
            var.set("worker")
            return var.get()

        results = dict(_gen()._run_preamble_wave([("s", setter)]))

        assert results["s"] == "worker"
        assert var.get() == "caller", "the worker's write escaped its context"


def _nested_function(name: str) -> ast.FunctionDef:
    source = inspect.getsource(StoryGenerator.generate_full_story)
    tree = ast.parse(inspect.cleandoc(source))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name} not found in generate_full_story")


def _names_in(node: ast.AST) -> set:
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)} | {
        n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute)
    } | {
        alias.name
        for n in ast.walk(node)
        if isinstance(n, ast.ImportFrom)
        for alias in n.names
    }


class TestMutatorsStayOffTheWorkerThreads:
    """Both wave-2 steps write into the shared `characters` list."""

    @pytest.mark.parametrize(
        "task,mutator",
        [
            ("_gen_voice_profiles", "update_character_speech_patterns"),
            ("_gen_waypoints", "apply_waypoints_to_characters"),
        ],
    )
    def test_the_worker_does_not_apply_its_own_result(self, task, mutator):
        assert mutator not in _names_in(_nested_function(task)), (
            f"{task} mutates `characters` on a worker thread while its siblings read it"
        )

    def test_both_waves_actually_go_through_the_helper(self):
        source = inspect.getsource(StoryGenerator.generate_full_story)
        assert source.count("_run_preamble_wave(") == 2

    @pytest.mark.parametrize(
        "task", ["_gen_idea_summary", "_gen_premise", "_gen_characters"]
    )
    def test_wave_one_tasks_do_not_read_the_cast(self, task):
        """Reading `characters` would make wave 1 depend on its own sibling."""
        assert "characters" not in _names_in(_nested_function(task))
