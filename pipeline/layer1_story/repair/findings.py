"""Data contracts for the L1 chapter repair loop.

See `docs/agentic-repair-loop-spec.md`. These types are deliberately plain
dataclasses: the repair loop must stay testable without an LLM in the room.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Severity(str, Enum):
    """How badly a finding needs fixing.

    Ordered by `SEVERITY_WEIGHT` below — used both to gate whether repair runs
    at all (`repair_min_severity`) and to weight the regression score.
    """

    BLOCKER = "blocker"  # missing payoff, world-rule violation
    MAJOR = "major"  # arc drift, wrong character name, pacing mismatch
    MINOR = "minor"  # under target length, thin sensory detail


# Weight per severity, used for both jobs: ordering (is this severe enough to
# spend a rewrite on?) and scoring (a rewrite that trades one blocker for two
# minors is an improvement; the weights say so).
SEVERITY_WEIGHT: dict[Severity, float] = {
    Severity.MINOR: 1.0,
    Severity.MAJOR: 3.0,
    Severity.BLOCKER: 9.0,
}

# Sources whose findings can be re-measured from chapter text alone, cheaply and
# without an LLM. Only these take part in the regression comparison — see
# `coordinator._score`.
#
# Excluded on purpose:
#   "pacing"   — detection costs an LLM call; re-running it every round would
#                spend the budget on measurement instead of repair.
#   "arc"      — `detect_arc_drift` reads `story_context.character_states`, not
#                the chapter text, so rewriting the chapter cannot change its
#                verdict. Carried as a constraint, never re-scored.
#   "critique" — an LLM grading its own prose. Re-scoring it is exactly the
#                intrinsic self-correction signal the spec forbids as a loop
#                condition (spec §1.3).
RECHECKABLE_SOURCES: frozenset[str] = frozenset(
    {"payoff", "name", "location", "length"}
)


@dataclass(frozen=True)
class RepairFinding:
    """One defect found in a written chapter."""

    source: str  # "payoff" | "name" | "location" | "arc" | "pacing" | "length" | "critique"
    severity: Severity
    detail: str  # human- and model-readable description
    evidence: str = ""  # supporting excerpt, trimmed by the caller
    hard_constraint: str = ""  # invariant the rewrite MUST preserve

    def __post_init__(self) -> None:
        if not self.source:
            raise ValueError("RepairFinding.source is required")
        if not self.detail:
            raise ValueError("RepairFinding.detail is required")

    @property
    def recheckable(self) -> bool:
        return self.source in RECHECKABLE_SOURCES


@dataclass
class RepairPlan:
    """What the planner decided to do about a set of findings."""

    strategy: str = "full_rewrite"  # "full_rewrite" | "skip"
    ordered_fixes: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    skip_reason: str = ""


@dataclass
class RepairOutcome:
    """What the repair loop actually did — mirrored into the pipeline trace."""

    applied: bool = False
    rounds_used: int = 0
    calls_used: int = 0
    findings_before: int = 0
    findings_after: int = 0
    rolled_back: bool = False
    fallback_used: bool = False
    strategy: str = ""


class RepairBudget:
    """Hard ceiling on LLM calls and rounds for one chapter's repair.

    Not advisory. `spend()` refuses once the ceiling is reached so a bug in the
    loop cannot quietly turn into an unbounded spend.
    """

    def __init__(self, max_rounds: int, max_calls: int) -> None:
        self.max_rounds = max(0, int(max_rounds))
        self.max_calls = max(0, int(max_calls))
        self.rounds_used = 0
        self.calls_used = 0

    def can_continue(self) -> bool:
        return self.rounds_used < self.max_rounds and self.calls_used < self.max_calls

    def has_calls(self, n: int = 1) -> bool:
        return self.calls_used + n <= self.max_calls

    def spend(self, n: int = 1) -> bool:
        """Charge `n` calls. False (and no charge) once the ceiling is reached."""
        if not self.has_calls(n):
            return False
        self.calls_used += n
        return True

    def start_round(self) -> None:
        self.rounds_used += 1
