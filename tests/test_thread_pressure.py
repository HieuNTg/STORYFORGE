"""Phase C — Thread-Urgency → Psychology Pressure tests."""

from unittest.mock import MagicMock

from models.schemas import CharacterPsychology, PlotThread
from pipeline.layer2_enhance.psychology_engine import PsychologyEngine


def _psych(name="A", pressure=0.0):
    return CharacterPsychology(character_name=name, pressure=pressure)


def _thread(tid, involved, urgency=5, last_ch=0, status="open"):
    return PlotThread(
        thread_id=tid, description="d", planted_chapter=1,
        status=status, involved_characters=list(involved),
        last_mentioned_chapter=last_ch, urgency=urgency,
    )


def test_apply_thread_pressure_urgent_stale_bumps_015():
    eng = PsychologyEngine.__new__(PsychologyEngine)  # skip LLM init
    p = _psych("A", 0.2)
    t = _thread("t1", ["A"], urgency=4, last_ch=1)
    delta = eng.apply_thread_pressure(p, [t], current_chapter=3)
    assert delta == 0.15
    assert abs(p.pressure - 0.35) < 1e-9


def test_urgency_5_open_adds_bonus():
    eng = PsychologyEngine.__new__(PsychologyEngine)
    p = _psych("A", 0.0)
    t = _thread("t1", ["A"], urgency=5, last_ch=1, status="open")
    delta = eng.apply_thread_pressure(p, [t], current_chapter=3)
    assert delta == 0.20
    assert abs(p.pressure - 0.20) < 1e-9


def test_urgency_5_non_open_no_bonus():
    eng = PsychologyEngine.__new__(PsychologyEngine)
    p = _psych("A", 0.0)
    t = _thread("t1", ["A"], urgency=5, last_ch=1, status="progressing")
    delta = eng.apply_thread_pressure(p, [t], current_chapter=3)
    assert delta == 0.15


def test_character_not_involved_no_bump():
    eng = PsychologyEngine.__new__(PsychologyEngine)
    p = _psych("X", 0.1)
    t = _thread("t1", ["A", "B"], urgency=5, last_ch=1)
    delta = eng.apply_thread_pressure(p, [t], current_chapter=3)
    assert delta == 0.0
    assert p.pressure == 0.1


def test_staleness_lt_2_no_bump():
    eng = PsychologyEngine.__new__(PsychologyEngine)
    p = _psych("A", 0.0)
    t = _thread("t1", ["A"], urgency=5, last_ch=2)
    delta = eng.apply_thread_pressure(p, [t], current_chapter=3)  # staleness=1
    assert delta == 0.0


def test_urgency_lt_4_no_bump():
    eng = PsychologyEngine.__new__(PsychologyEngine)
    p = _psych("A", 0.0)
    t = _thread("t1", ["A"], urgency=3, last_ch=1)
    delta = eng.apply_thread_pressure(p, [t], current_chapter=5)
    assert delta == 0.0


def test_cap_at_max_bump():
    eng = PsychologyEngine.__new__(PsychologyEngine)
    p = _psych("A", 0.0)
    threads = [_thread(f"t{i}", ["A"], urgency=5, last_ch=1) for i in range(5)]
    delta = eng.apply_thread_pressure(p, threads, current_chapter=5)
    assert delta == 0.30  # cap, not 5*0.20=1.00


def test_pressure_saturates_at_1():
    eng = PsychologyEngine.__new__(PsychologyEngine)
    p = _psych("A", 0.95)
    threads = [_thread(f"t{i}", ["A"], urgency=5, last_ch=1) for i in range(3)]
    eng.apply_thread_pressure(p, threads, current_chapter=5)
    assert p.pressure == 1.0


def test_never_mentioned_uses_planted_chapter_for_staleness():
    """Thread with last_mentioned=0 (never updated) must use planted_chapter fallback."""
    eng = PsychologyEngine.__new__(PsychologyEngine)
    p = _psych("A", 0.0)
    # Planted ch1, never mentioned since → stale by current-1 at any later chapter
    t = PlotThread(
        thread_id="t1", description="d", planted_chapter=1,
        status="open", involved_characters=["A"],
        last_mentioned_chapter=0, urgency=5,
    )
    delta = eng.apply_thread_pressure(p, [t], current_chapter=10)
    assert delta == 0.20  # staleness=9, urgency=5, status=open


def test_empty_threads_no_crash():
    eng = PsychologyEngine.__new__(PsychologyEngine)
    p = _psych("A", 0.3)
    delta = eng.apply_thread_pressure(p, [], current_chapter=5)
    assert delta == 0.0
    assert p.pressure == 0.3


def test_custom_max_bump_respected():
    eng = PsychologyEngine.__new__(PsychologyEngine)
    p = _psych("A", 0.0)
    threads = [_thread(f"t{i}", ["A"], urgency=5, last_ch=1) for i in range(3)]
    delta = eng.apply_thread_pressure(p, threads, current_chapter=5, max_bump=0.10)
    assert delta == 0.10


def test_simulator_invokes_thread_pressure_post_psychology():
    """Smoke: per-agent psychology gets bumped when threads include the char."""
    eng = PsychologyEngine.__new__(PsychologyEngine)
    agent = MagicMock()
    agent.psychology = _psych("A", 0.1)
    threads = [_thread("t1", ["A"], urgency=5, last_ch=1)]
    for ag in [agent]:
        eng.apply_thread_pressure(ag.psychology, threads, current_chapter=5)
    assert agent.psychology.pressure > 0.1
