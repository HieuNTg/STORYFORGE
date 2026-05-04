"""Legacy structural issue types — kept for one release cycle (Sprint 2).

The keyword-based `StructuralIssueDetector` class has been removed in Sprint 2
P4 and replaced by `pipeline.semantic.structural_detector.detect_structural_issues`
(NER + embedding-based).

This module retains only:
- `StructuralIssueType` enum  — consumed by `models.semantic_schemas.StructuralFinding.to_legacy_issue()`
- `StructuralIssue` dataclass — adapter target used by `enhancer.py` until migration complete

Do NOT add new logic here. New structural checks go in `pipeline.semantic.structural_detector`.
"""

from dataclasses import dataclass
from enum import Enum

import logging

logger = logging.getLogger(__name__)


class StructuralIssueType(Enum):
    MISSING_KEY_EVENT = "missing_key_event"
    WRONG_CHARACTERS = "wrong_characters"
    MISSED_ARC_WAYPOINT = "missed_arc_waypoint"
    PACING_VIOLATION = "pacing_violation"


@dataclass
class StructuralIssue:
    """Legacy dataclass. Use `models.semantic_schemas.StructuralFinding` for new code.

    Kept for one release cycle so that `enhancer.py` and `orchestrator_layers.py`
    continue to work without modification.  Will be removed in Sprint 3.
    """

    issue_type: StructuralIssueType
    severity: float  # 0.0-1.0
    description: str
    chapter_number: int
    fix_hint: str
