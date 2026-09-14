"""Tests for the bounded L1 chapter repair loop (Sprint 2, Batch K).

Context: post-write repair used to be five independent passes, each regenerating
the whole chapter knowing only its own concern. Worst case was 8 LLM calls per
chapter with 5 full regenerations, and the passes overwrote each other — the
payoff rewrite could shorten a chapter below target and the length expansion
could then drop the payoff it had just inserted. `test_length_survives_payoff_fix`
is that bug, written as a test.

Every test here runs without an LLM: the loop's verifier is deterministic by
design, so its behaviour has to be provable without one.
"""

from types import SimpleNamespace

from pipeline.layer1_story.repair.collector import collect_findings
from pipeline.layer1_story.repair.context import RepairContext
from pipeline.layer1_story.repair.coordinator import repair_chapter
from pipeline.layer1_story.repair.executor import execute_repair
from pipeline.layer1_story.repair.findings import (
    RepairBudget,
    RepairFinding,
    Severity,
)
from pipeline.layer1_story.repair.planner import plan_repair


# ---------------------------------------------------------------------------
# Fixtures / fakes
# ---------------------------------------------------------------------------


def _words(n: int) -> str:
    return " ".join(["tu"] * n)


class _Chapter:
    def __init__(self, content: str):
        self.content = content
        self.word_count = len(content.split())


class _StoryContext:
    """Stand-in for the pydantic StoryContext (which allows extra attrs)."""

    def __init__(self, **kw):
        self.name_warnings = []
        self.arc_drift_warnings = []
        self.arc_execution_warnings = []
        self.world_rule_violations = []
        self.foreshadowing_payoff_missing = []
        self.character_states = []
        self.total_chapters = 10
        self.repair_pending_critique = None
        self.__dict__.update(kw)


def _config(**kw):
    base = {
        # repair loop
        "enable_agentic_repair": True,
        "repair_max_rounds": 2,
        "repair_budget_calls": 4,
        "repair_regression_tolerance": 0.0,
        "repair_fallback_to_legacy": False,
        "repair_min_severity": "major",
        # detectors the collector reads
        "enable_length_gate": True,
        "length_gate_min_ratio": 0.85,
        "consistency_name_warning_threshold": 3,
        "consistency_arc_drift_threshold": 2,
        "consistency_location_warning_threshold": 2,
        "enable_pacing_enforcement": False,
        "pacing_mismatch_rewrite": False,
        "pacing_enforcement_confidence": 0.7,
        "enable_foreshadowing_payoff_verify": False,
        "enable_semantic_foreshadowing": False,
        "semantic_foreshadowing_threshold": 0.7,
    }
    base.update(kw)
    return SimpleNamespace(**base)


class _LLM:
    """Returns a fixed body and counts calls."""

    def __init__(self, *bodies: str):
        self.bodies = list(bodies)
        self.calls: list[dict] = []

    def generate(self, **kwargs):
        self.calls.append(kwargs)
        if not self.bodies:
            raise AssertionError("LLM called more times than the test allowed")
        return self.bodies.pop(0)


class _ExplodingLLM:
    def generate(self, **kwargs):
        raise RuntimeError("bridge down")


def _ctx(chapter, config=None, story_context=None, **kw):
    base = dict(
        pipeline_config=config or _config(),
        llm=_LLM(),
        chapter=chapter,
        outline=SimpleNamespace(chapter_number=3, pacing_type="", title="T", summary="S"),
        story_context=story_context if story_context is not None else _StoryContext(),
        characters=[],
        draft=None,
        foreshadowing_plan=None,
        word_count=2000,
        layer_model=None,
        progress_callback=None,
    )
    base.update(kw)
    return RepairContext(**base)


# ---------------------------------------------------------------------------
# The bug this batch exists to fix
# ---------------------------------------------------------------------------


def test_length_survives_payoff_fix():
    """A payoff fix must not be allowed to shorten the chapter below target.

    Legacy behaviour: the payoff pass rewrote the chapter with only "±15% of the
    current draft" as its length instruction, the consistency pass shortened it
    again, and the length gate then expanded a draft with no instruction to keep
    the payoff. Three regenerations, and no single request ever held both
    requirements at once.
    """
    sc = _StoryContext(
        foreshadowing_payoff_missing=[{"hint": "con dao trong ngăn kéo"}],
    )
    chapter = _Chapter(_words(1300))  # 65% of the 2000-word target
    ctx = _ctx(chapter, story_context=sc)

    findings = collect_findings(ctx)
    plan = plan_repair(findings)

    sources = {f.source for f in findings}
    assert "payoff" in sources, "missing payoff must be detected"
    assert "length" in sources, "short chapter must be detected"

    # Both requirements reach the model in the SAME request.
    joined = "\n".join(plan.constraints)
    assert "con dao trong ngăn kéo" in joined
    assert "1700" in joined, "the absolute word floor must be stated, not a ±% of the current draft"

    # And the blocker is instructed before the length fix, so a model forced to
    # choose sacrifices length rather than the payoff.
    assert plan.ordered_fixes[0].startswith("Foreshadowing")


def test_repair_constraints_merged():
    """Every hard_constraint from every finding reaches the one rewrite prompt."""
    findings = [
        RepairFinding("payoff", Severity.BLOCKER, "p", hard_constraint="GIU_PAYOFF"),
        RepairFinding("length", Severity.MAJOR, "l", hard_constraint="GIU_DO_DAI"),
        RepairFinding("name", Severity.MAJOR, "n", hard_constraint="GIU_TEN"),
    ]
    plan = plan_repair(findings)
    llm = _LLM(_words(2100))
    ctx = _ctx(_Chapter(_words(1300)), llm=llm)

    execute_repair(plan, ctx, RepairBudget(2, 4))

    prompt = llm.calls[0]["user_prompt"]
    for constraint in ("GIU_PAYOFF", "GIU_DO_DAI", "GIU_TEN"):
        assert constraint in prompt


# ---------------------------------------------------------------------------
# Budget
# ---------------------------------------------------------------------------


def test_repair_budget_hard_cap():
    """The budget refuses to overspend rather than trusting the caller."""
    budget = RepairBudget(max_rounds=5, max_calls=2)
    assert budget.spend()
    assert budget.spend()
    assert not budget.has_calls(1)
    assert not budget.spend()
    assert budget.calls_used == 2


def test_loop_stops_at_the_call_ceiling():
    """No matter how many rounds are allowed, calls are capped."""
    sc = _StoryContext(name_warnings=["a", "b", "c"])
    # Each rewrite comes back still short, so the loop always has work to do.
    llm = _LLM(*[_words(1300 + i) for i in range(10)])
    ctx = _ctx(
        _Chapter(_words(1200)),
        config=_config(repair_max_rounds=9, repair_budget_calls=2),
        story_context=sc,
        llm=llm,
    )
    outcome = repair_chapter(ctx)
    assert outcome.calls_used <= 2
    assert len(llm.calls) <= 2


# ---------------------------------------------------------------------------
# Rollback
# ---------------------------------------------------------------------------


def test_repair_rollback_on_regression():
    """A rewrite that measures worse is rejected and the chapter kept as-is.

    Legacy passes 2-5 accepted any rewrite that merely differed from the
    original; only self-critique could roll back.
    """
    original = _words(1800)  # 90% of target — above the length floor
    chapter = _Chapter(original)
    sc = _StoryContext(name_warnings=["Lan/Làn", "Nam/Nãm", "Hoa/Hòa"])
    # The "fix" comes back far under target: strictly worse by the only
    # measurement that can be re-run.
    llm = _LLM(_words(900))
    ctx = _ctx(chapter, story_context=sc, llm=llm)

    outcome = repair_chapter(ctx)

    assert outcome.rolled_back is True
    assert outcome.applied is False
    assert chapter.content == original
    assert chapter.word_count == 1800


def test_improvement_is_accepted():
    """The mirror image: a rewrite that measures better is committed."""
    chapter = _Chapter(_words(1200))
    ctx = _ctx(chapter, llm=_LLM(_words(2050)))

    outcome = repair_chapter(ctx)

    assert outcome.applied is True
    assert outcome.rolled_back is False
    assert chapter.word_count == 2050


# ---------------------------------------------------------------------------
# Purity — the contract the whole loop rests on
# ---------------------------------------------------------------------------


def test_collector_is_pure():
    """`collect_findings` must not mutate story_context.

    The loop re-measures candidates that may be rejected. A collector with side
    effects would leak a discarded draft's measurements into the chapter that
    actually ships.
    """
    sc = _StoryContext(
        name_warnings=["Lan/Làn"],
        arc_drift_warnings=["arc"],
        world_rule_violations=["[VỊ TRÍ] Lan: nhà → chợ"],
        foreshadowing_payoff_missing=[{"hint": "dao"}],
    )
    before = {
        "name": list(sc.name_warnings),
        "arc": list(sc.arc_drift_warnings),
        "world": list(sc.world_rule_violations),
        "payoff": list(sc.foreshadowing_payoff_missing),
    }
    ctx = _ctx(_Chapter(_words(1200)), story_context=sc)

    collect_findings(ctx)

    assert list(sc.name_warnings) == before["name"]
    assert list(sc.arc_drift_warnings) == before["arc"]
    assert list(sc.world_rule_violations) == before["world"]
    assert list(sc.foreshadowing_payoff_missing) == before["payoff"]


# ---------------------------------------------------------------------------
# Failure containment
# ---------------------------------------------------------------------------


def test_repair_exception_non_fatal():
    """An LLM failure leaves the chapter exactly as written."""
    original = _words(1200)
    chapter = _Chapter(original)
    ctx = _ctx(chapter, llm=_ExplodingLLM())

    outcome = repair_chapter(ctx)

    assert chapter.content == original
    assert chapter.word_count == 1200
    assert outcome.applied is False


def test_summarising_rewrite_is_discarded():
    """A 'rewrite' that comes back as a fragment is the model summarising."""
    chapter = _Chapter(_words(1200))
    plan = plan_repair([RepairFinding("length", Severity.MAJOR, "short")])
    ctx = _ctx(chapter, llm=_LLM("ngắn"))

    assert execute_repair(plan, ctx, RepairBudget(2, 4)) is None


# ---------------------------------------------------------------------------
# Trigger surface — repair must fire exactly where legacy fired
# ---------------------------------------------------------------------------


def test_below_threshold_warnings_do_not_trigger_a_rewrite():
    """Two name warnings never justified a rewrite; they still don't."""
    sc = _StoryContext(name_warnings=["Lan/Làn", "Nam/Nãm"])  # threshold is 3
    llm = _LLM()  # any call is a failure
    ctx = _ctx(_Chapter(_words(1900)), story_context=sc, llm=llm)

    outcome = repair_chapter(ctx)

    assert outcome.applied is False
    assert llm.calls == []


def test_short_chapter_alone_triggers_repair():
    """Length is MAJOR on purpose: repair must not stop expanding short chapters."""
    chapter = _Chapter(_words(900))
    ctx = _ctx(chapter, llm=_LLM(_words(2050)))

    outcome = repair_chapter(ctx)

    assert outcome.applied is True
    assert chapter.word_count == 2050


def test_clean_chapter_costs_nothing():
    """No findings, no calls — the common case must stay free."""
    llm = _LLM()
    ctx = _ctx(_Chapter(_words(2000)), llm=llm)

    outcome = repair_chapter(ctx)

    assert outcome.applied is False
    assert outcome.findings_before == 0
    assert llm.calls == []


# ---------------------------------------------------------------------------
# Planner contract (guards the K-C swap)
# ---------------------------------------------------------------------------


def test_planner_skips_empty_findings():
    plan = plan_repair([])
    assert plan.strategy == "skip"


# ---------------------------------------------------------------------------
# The legacy path must stay exactly as it was
# ---------------------------------------------------------------------------


def _patch_finalizer(monkeypatch, calls: list):
    """Replace finalize_chapter's five collaborators with order-recording stubs."""
    import pipeline.layer1_story.chapter_finalizer as cf

    monkeypatch.setattr(
        cf, "process_chapter_post_write", lambda *a, **k: calls.append("post_write")
    )
    monkeypatch.setattr(
        cf,
        "_verify_and_rewrite_missing_payoffs",
        lambda *a, **k: calls.append("payoff"),
    )
    monkeypatch.setattr(
        cf,
        "_rewrite_for_consistency_violations",
        lambda *a, **k: calls.append("consistency"),
    )
    monkeypatch.setattr(cf, "_enforce_pacing", lambda *a, **k: calls.append("pacing"))
    monkeypatch.setattr(
        cf, "expand_chapter_if_short", lambda *a, **k: calls.append("length")
    )
    return cf


def _finalize_kwargs(config):
    return dict(
        pipeline_config=config,
        llm=_LLM(),
        chapter=_Chapter(_words(1200)),
        outline=SimpleNamespace(
            chapter_number=3, pacing_type="", title="T", summary="S"
        ),
        story_context=_StoryContext(),
        characters=[],
        context_window=4000,
        executor=None,
        draft=SimpleNamespace(world=SimpleNamespace(rules=[]), voice_profiles=[]),
        bible_manager=None,
        progress_callback=None,
        genre="",
        word_count=2000,
        enable_self_review=False,
        self_reviewer=None,
        open_threads=[],
        foreshadowing_plan=None,
        layer_model=None,
    )


def test_repair_disabled_is_byte_identical(monkeypatch):
    """Flag off: the four legacy passes run, in their original order."""
    calls: list[str] = []
    cf = _patch_finalizer(monkeypatch, calls)

    cf.finalize_chapter(**_finalize_kwargs(_config(enable_agentic_repair=False)))

    assert calls == ["post_write", "payoff", "consistency", "pacing", "length"]


def test_repair_enabled_replaces_the_legacy_passes(monkeypatch):
    """Flag on: post-write still runs, the four rewrite passes do not."""
    calls: list[str] = []
    cf = _patch_finalizer(monkeypatch, calls)

    cf.finalize_chapter(**_finalize_kwargs(_config(enable_agentic_repair=True)))

    assert calls[0] == "post_write"
    assert "payoff" not in calls
    assert "consistency" not in calls
    assert "pacing" not in calls
    assert "length" not in calls


def test_fallback_reaches_the_legacy_passes(monkeypatch):
    """Budget spent with work still outstanding falls back to legacy behaviour."""
    import pipeline.layer1_story.repair.coordinator as coord

    calls: list[str] = []
    monkeypatch.setattr(coord, "_run_legacy_passes", lambda ctx: calls.append("legacy"))

    sc = _StoryContext(name_warnings=["a", "b", "c"])
    ctx = _ctx(
        _Chapter(_words(1200)),
        config=_config(
            repair_max_rounds=1,
            repair_budget_calls=1,
            repair_fallback_to_legacy=True,
        ),
        story_context=sc,
        # Still short after the rewrite, so a finding survives the round.
        llm=_LLM(_words(1250)),
    )

    outcome = repair_chapter(ctx)

    assert outcome.fallback_used is True
    assert calls == ["legacy"]


# ---------------------------------------------------------------------------
# The existing user-facing toggles must keep working through the new path
# ---------------------------------------------------------------------------


def test_length_gate_toggle_still_disables_expansion():
    """Unchecking "length gate" in Settings must stop repair expanding chapters too.

    The toggle is exposed in the UI (advancedL1FormSchema) and predates this
    batch. Repair replaced the pass behind it, so the flag has to be honoured by
    the collector or the control would silently become a no-op.
    """
    llm = _LLM()  # any call is a failure
    ctx = _ctx(
        _Chapter(_words(900)),
        config=_config(enable_length_gate=False),
        llm=llm,
    )

    outcome = repair_chapter(ctx)

    assert outcome.findings_before == 0
    assert llm.calls == []


def test_min_severity_can_be_widened_to_minor():
    """`repair_min_severity=minor` lets craft-only findings start a rewrite."""
    sc = _StoryContext(
        repair_pending_critique={
            "weak_sections": [{"location": "end", "issue": "kết chương nhạt"}]
        }
    )
    ctx = _ctx(
        _Chapter(_words(1900)),  # above the length floor: no other finding
        config=_config(repair_min_severity="minor"),
        story_context=sc,
        llm=_LLM(_words(1950)),
    )

    outcome = repair_chapter(ctx)

    assert outcome.applied is True


def test_unknown_min_severity_falls_back_to_major():
    """A typo in config must not widen the trigger surface silently."""
    from pipeline.layer1_story.repair.coordinator import _min_severity

    assert _min_severity(_config(repair_min_severity="urgent")) is Severity.MAJOR
