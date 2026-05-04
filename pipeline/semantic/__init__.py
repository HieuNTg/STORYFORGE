"""pipeline.semantic — embedding-based semantic verification modules (Sprint 2).

Shared exception `SemanticVerificationError` and strict-mode helper live here
so P3 (foreshadowing_verifier), P4 (structural_detector), and P5
(outline_critic) can all use them without a circular import or duplicated
env-reads.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from models.semantic_schemas import SemanticPayoffMatch, StructuralFinding

_STRICT_ENV = "STORYFORGE_SEMANTIC_STRICT"


def is_strict_mode() -> bool:
    """Return True when STORYFORGE_SEMANTIC_STRICT=1 is set in the environment.

    Single canonical helper — use this instead of reading os.environ directly
    in P3, P4, and P5 to avoid three duplicated env-reads (DRY).
    """
    return os.environ.get(_STRICT_ENV, "0").strip() == "1"


class SemanticVerificationError(Exception):
    """Raised in strict mode (STORYFORGE_SEMANTIC_STRICT=1) when semantic
    verification detects critical failures.

    `missed_payoffs` and `critical_findings` are populated by the respective
    verifier; at most one will be non-empty per raise.

    `missed` is a backward-compat alias for `missed_payoffs` (used by P3 tests).
    """

    def __init__(
        self,
        message: str,
        missed_payoffs: "list[SemanticPayoffMatch] | None" = None,
        critical_findings: "list[StructuralFinding] | None" = None,
    ) -> None:
        super().__init__(message)
        self.missed_payoffs: list = missed_payoffs or []
        self.critical_findings: list = critical_findings or []
        # Backward-compat alias: P3 tests access .missed
        self.missed: list = self.missed_payoffs


__all__ = ["is_strict_mode", "SemanticVerificationError"]
