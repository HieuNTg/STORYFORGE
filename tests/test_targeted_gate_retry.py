"""Sprint 2 — the quality gate's retry threw the whole layer away.

When a gate failed, Layer 1 was regenerated from scratch (every preamble call,
every chapter) or Layer 2 was enhanced a second time in full — at the price of
the first pass — to fix what is usually two weak chapters out of ten. The
replacement was then accepted unseen: nothing compared the retry against what
it replaced, so a *worse* second attempt shipped.

SmartRevisionService already does the targeted version of this and had been
running later in the very same pipeline: rewrite only the chapters below
threshold, re-score each, keep the rewrite only when it measurably improves.

The wholesale path is kept as a fallback, and that matters: when every chapter
clears the chapter threshold but the story scores low overall, the complaint is
not localised to any chapter and only regenerating the layer can move it.
"""

import ast
import asyncio
import inspect
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import pipeline.orchestrator_layers as ol


def _scores(*chapter_overalls):
    return [
        SimpleNamespace(
            overall=sum(chapter_overalls) / len(chapter_overalls),
            chapter_scores=[
                SimpleNamespace(chapter_number=i + 1, overall=v)
                for i, v in enumerate(chapter_overalls)
            ],
        )
    ]


def _call(**overrides):
    kwargs = dict(
        story=SimpleNamespace(chapters=[]),
        quality_scores=_scores(2.0, 4.5),
        reviews=[],
        genre="trinh thám",
        chapter_threshold=3.0,
        idea="",
        idea_summary="",
        log=lambda m: None,
    )
    kwargs.update(overrides)
    return asyncio.run(ol._targeted_gate_revision(**kwargs))


class TestTargetedRevisionContract:
    def test_no_scores_means_nothing_to_target(self):
        assert _call(quality_scores=[]) == 0

    def test_no_per_chapter_scores_means_nothing_to_target(self):
        scores = [SimpleNamespace(overall=2.0, chapter_scores=[])]
        assert _call(quality_scores=scores) == 0

    def test_it_reports_how_many_chapters_it_changed(self):
        with patch("services.smart_revision.SmartRevisionService") as MockSvc:
            MockSvc.return_value.revise_weak_chapters.return_value = {
                "revised_count": 2,
                "total_weak": 3,
            }
            assert _call() == 2

    def test_it_uses_the_gates_own_chapter_threshold(self):
        """Revising a different set than the gate named would be a new bug."""
        with patch("services.smart_revision.SmartRevisionService") as MockSvc:
            MockSvc.return_value.revise_weak_chapters.return_value = {
                "revised_count": 1
            }
            _call(chapter_threshold=3.75)
            assert MockSvc.call_args.kwargs["threshold"] == 3.75

    def test_a_revision_failure_is_non_fatal_and_falls_back(self):
        with patch("services.smart_revision.SmartRevisionService") as MockSvc:
            MockSvc.return_value.revise_weak_chapters.side_effect = RuntimeError(
                "provider down"
            )
            assert _call() == 0

    def test_reviews_are_passed_through_when_present(self):
        review = SimpleNamespace(chapter_number=1, issues=["a", "b", "c"])
        with patch("services.smart_revision.SmartRevisionService") as MockSvc:
            MockSvc.return_value.revise_weak_chapters.return_value = {
                "revised_count": 1
            }
            _call(reviews=[review])
            assert MockSvc.return_value.revise_weak_chapters.call_args.kwargs[
                "reviews"
            ] == [review]

    def test_none_reviews_become_an_empty_list_not_a_crash(self):
        with patch("services.smart_revision.SmartRevisionService") as MockSvc:
            MockSvc.return_value.revise_weak_chapters.return_value = {
                "revised_count": 1
            }
            _call(reviews=None)
            assert (
                MockSvc.return_value.revise_weak_chapters.call_args.kwargs["reviews"]
                == []
            )


def _gate_branches():
    """Every `if <targeted>: ... else: <wholesale>` in run_full_pipeline."""
    tree = ast.parse(inspect.cleandoc(inspect.getsource(ol.run_full_pipeline)))
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        if not (isinstance(node.test, ast.Name) and node.test.id == "_revised"):
            continue
        found.append(node)
    return found


def _calls_in(node) -> set:
    """Every function named in a subtree, called or merely referenced.

    `generate_full_story` is handed to asyncio.to_thread rather than called, so
    matching on ast.Call alone would miss exactly the branch under test.
    """
    names = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Attribute):
            names.add(n.attr)
        elif isinstance(n, ast.Name):
            names.add(n.id)
    return names


class TestBothGatesTryTargetedFirst:
    def test_there_is_a_targeted_branch_at_each_gate(self):
        assert len(_gate_branches()) == 2, "layer 1 and layer 2 gates"

    @pytest.mark.parametrize("wholesale", ["generate_full_story", "enhance_with_feedback_async"])
    def test_the_wholesale_path_moved_into_the_fallback(self, wholesale):
        """It must be what happens when targeting found nothing, not the default."""
        in_else = set()
        for branch in _gate_branches():
            for stmt in branch.orelse:
                in_else |= _calls_in(stmt)
        assert wholesale in in_else, (
            f"{wholesale} is not gated behind a failed targeted revision"
        )

    @pytest.mark.parametrize("wholesale", ["generate_full_story", "enhance_with_feedback_async"])
    def test_the_wholesale_path_is_not_also_run_on_the_targeted_branch(self, wholesale):
        in_body = set()
        for branch in _gate_branches():
            for stmt in branch.body:
                in_body |= _calls_in(stmt)
        assert wholesale not in in_body

    def test_both_gates_call_the_targeted_helper(self):
        source = inspect.getsource(ol.run_full_pipeline)
        assert source.count("_targeted_gate_revision(") == 2
