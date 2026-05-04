"""pipeline.semantic — embedding-based semantic verification modules (Sprint 2).

Shared exception `SemanticVerificationError` lives here so both
`foreshadowing_verifier` (P3) and `structural_detector` (P4) can raise it
without a circular import.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from models.semantic_schemas import SemanticPayoffMatch, StructuralFinding


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


__all__ = ["SemanticVerificationError"]
