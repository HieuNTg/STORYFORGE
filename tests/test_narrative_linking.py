"""Tests for Phase 3: Narrative Linking — thread deps, semantic foreshadowing, conflict escalation."""

from models.schemas import PlotThread, ForeshadowingEntry, ConflictEntry
from pipeline.layer1_story.plot_thread_tracker import (
    validate_thread_resolution,
    escalate_urgency,
    format_threads_for_prompt,
    update_threads,
)
from pipeline.layer1_story.foreshadowing_manager import mark_planted
from pipeline.layer1_story.conflict_web_builder import (
    format_conflicts_for_prompt,
    update_conflict_status,
)


def _thread(tid="t1", status="open", planted=1, last=1, deps=None, blocks=None, urgency=3, chars=None):
    return PlotThread(
        thread_id=tid, description=f"Thread {tid}", planted_chapter=planted,
        status=status, last_mentioned_chapter=last,
        depends_on=deps or [], blocks=blocks or [], urgency=urgency,
        involved_characters=chars or [],
    )


def _seed(hint="dark omen", plant=3, payoff=8, planted=False, paid=False, conf=0.0):
    return ForeshadowingEntry(
        hint=hint, plant_chapter=plant, payoff_chapter=payoff,
        planted=planted, paid_off=paid, planted_confidence=conf,
    )


def _conflict(cid="c1", status="active", intensity=1, chars=None, desc="test conflict"):
    return ConflictEntry(
        conflict_id=cid, conflict_type="external",
        characters=chars or ["A", "B"], description=desc,
        status=status, intensity=intensity,
    )


class TestThreadDependencyValidation:
    def test_no_deps_always_allowed(self):
        t = _thread("t1")
        allowed, _ = validate_thread_resolution(t, [t])
        assert allowed

    def test_resolved_dep_allows(self):
        dep = _thread("dep1", status="resolved")
        t = _thread("t1", deps=["dep1"])
        allowed, _ = validate_thread_resolution(t, [t, dep])
        assert allowed

    def test_unresolved_dep_blocks(self):
        dep = _thread("dep1", status="open")
        t = _thread("t1", deps=["dep1"])
        allowed, reason = validate_thread_resolution(t, [t, dep])
        assert not allowed
        assert "dep1" in reason

    def test_missing_dep_allows(self):
        t = _thread("t1", deps=["nonexistent"])
        allowed, _ = validate_thread_resolution(t, [t])
        assert allowed

    def test_update_threads_blocks_resolution(self):
        dep = _thread("dep1", status="open")
        t = _thread("t1", deps=["dep1"])
        result = update_threads(
            [t, dep],
            {"resolved_threads": ["t1"], "progressed_threads": [], "new_threads": []},
            chapter_number=5,
        )
        t1 = next(x for x in result if x.thread_id == "t1")
        assert t1.status != "resolved"


class TestUrgencyEscalation:
    def test_escalates_after_gap(self):
        t = _thread("t1", urgency=2, last=1)
        escalate_urgency([t], current_chapter=7, gap=5)
        assert t.urgency == 3

    def test_caps_at_5(self):
        t = _thread("t1", urgency=5, last=1)
        escalate_urgency([t], current_chapter=100, gap=5)
        assert t.urgency == 5

    def test_no_escalate_if_recent(self):
        t = _thread("t1", urgency=2, last=8)
        escalate_urgency([t], current_chapter=10, gap=5)
        assert t.urgency == 2

    def test_resolved_skipped(self):
        t = _thread("t1", urgency=2, last=1, status="resolved")
        escalate_urgency([t], current_chapter=100, gap=5)
        assert t.urgency == 2


class TestThreadFormatting:
    def test_urgency_sorting(self):
        t_low = _thread("low", urgency=1, last=1)
        t_high = _thread("high", urgency=5, last=1)
        text = format_threads_for_prompt([t_low, t_high])
        assert text.index("high") < text.index("low")

    def test_high_urgency_marker(self):
        t = _thread("urgent", urgency=4)
        text = format_threads_for_prompt([t])
        assert "⚡4" in text

    def test_deps_shown(self):
        t = _thread("t1", deps=["dep1"])
        text = format_threads_for_prompt([t])
        assert "chờ: dep1" in text


class TestNewThreadsCaptureDeps:
    def test_new_thread_with_deps(self):
        result = update_threads(
            [],
            {
                "new_threads": [{"thread_id": "t1", "description": "test",
                                 "depends_on": ["t0"], "urgency": 4}],
                "progressed_threads": [],
                "resolved_threads": [],
            },
            chapter_number=1,
        )
        assert len(result) == 1
        assert result[0].depends_on == ["t0"]
        assert result[0].urgency == 4


class TestSemanticForeshadowing:
    """Tests for foreshadowing verification.

    The LLM-based verify_seeds_semantic / verify_payoffs_semantic were removed in
    Sprint 2 P3 and replaced with embedding-based verification in
    `pipeline.semantic.foreshadowing_verifier`. See tests/test_foreshadowing_verifier.py
    for comprehensive coverage of the new implementation.
    """

    def test_keyword_fallback_mark_planted(self):
        """mark_planted (keyword fallback) still works for legacy/degraded paths."""
        s = _seed("hero journey begins", plant=1)
        mark_planted([s], 1, "the hero journey begins now")
        assert s.planted is True
        assert s.planted_confidence > 0

    def test_mark_planted_below_threshold_not_planted(self):
        """mark_planted: low keyword overlap → not marked planted."""
        s = _seed("mysterious ancient artifact", plant=2)
        mark_planted([s], 2, "rain falls on the city streets")
        # "mysterious" (9 chars), "ancient" (7 chars), "artifact" (8 chars) — none in content
        assert s.planted is False

    def test_keyword_fallback_empty_hint(self):
        """mark_planted: hint with no words > 3 chars → always planted."""
        s = _seed("ok go", plant=1)
        mark_planted([s], 1, "any content at all")
        assert s.planted is True


class TestConflictEscalation:
    def test_intensity_increases_on_escalation_words(self):
        c = _conflict(intensity=1, status="active")
        update_conflict_status([c], "nhân vật đối đầu với kẻ thù", chapter_number=5)
        assert c.intensity > 1

    def test_heavy_escalation_jumps_two(self):
        c = _conflict(intensity=1, status="active")
        update_conflict_status([c], "phản bội đối đầu bùng nổ giết chết", chapter_number=5)
        assert c.intensity >= 3

    def test_intensity_capped_at_5(self):
        c = _conflict(intensity=5, status="escalating")
        update_conflict_status([c], "phản bội đối đầu bùng nổ", chapter_number=10)
        assert c.intensity == 5

    def test_escalation_timeline_recorded(self):
        c = _conflict(intensity=1, status="active")
        update_conflict_status([c], "đối đầu", chapter_number=3)
        assert len(c.escalation_timeline) == 1
        assert c.escalation_timeline[0]["chapter"] == 3

    def test_format_includes_intensity(self):
        c = _conflict(intensity=3)
        text = format_conflicts_for_prompt([c])
        assert "3/5" in text
        assert "gay gắt" in text

    def test_dormant_not_tracked(self):
        c = _conflict(status="dormant", intensity=1)
        update_conflict_status([c], "đối đầu", chapter_number=5)
        assert c.intensity == 1
        assert len(c.escalation_timeline) == 0
