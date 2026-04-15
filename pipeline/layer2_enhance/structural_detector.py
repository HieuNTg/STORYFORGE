"""Detect structural issues that require L1 chapter rewrite."""

from dataclasses import dataclass
from enum import Enum
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class StructuralIssueType(Enum):
    MISSING_KEY_EVENT = "missing_key_event"
    WRONG_CHARACTERS = "wrong_characters"
    MISSED_ARC_WAYPOINT = "missed_arc_waypoint"
    PACING_VIOLATION = "pacing_violation"


@dataclass
class StructuralIssue:
    issue_type: StructuralIssueType
    severity: float  # 0.0-1.0
    description: str
    chapter_number: int
    fix_hint: str


class StructuralIssueDetector:
    """Detect structural issues that L2 enhancement cannot fix."""

    SEVERITY_THRESHOLD = 0.7  # Issues above this trigger rewrite

    def __init__(self, severity_threshold: float = 0.7):
        self.severity_threshold = severity_threshold

    def detect(
        self,
        chapter,
        outline=None,
        contract=None,
        arc_waypoints: Optional[list] = None,
    ) -> list[StructuralIssue]:
        """Detect structural issues. Returns issues at or above severity threshold."""
        issues: list[StructuralIssue] = []
        ch_num = getattr(chapter, "chapter_number", 0)
        content = getattr(chapter, "content", "") or ""

        if outline:
            issues.extend(self._check_key_events(content, outline, ch_num))

        if outline:
            issues.extend(self._check_characters(content, outline, ch_num))

        if arc_waypoints:
            issues.extend(self._check_arc_waypoints(content, arc_waypoints, ch_num))

        if outline:
            issues.extend(self._check_pacing(content, outline, ch_num))

        return [i for i in issues if i.severity >= self.severity_threshold]

    def _check_key_events(self, content: str, outline, ch_num: int) -> list[StructuralIssue]:
        """Check if key events from outline appear in content."""
        issues: list[StructuralIssue] = []
        key_events = getattr(outline, "key_events", []) or []
        content_lower = content.lower()

        missing = []
        for event in key_events[:3]:  # Check top 3 key events
            event_keywords = str(event).lower().split()[:3]  # First 3 words
            if not any(kw in content_lower for kw in event_keywords if len(kw) > 3):
                missing.append(event)

        if len(missing) >= 2:  # 2+ missing = structural issue
            issues.append(StructuralIssue(
                issue_type=StructuralIssueType.MISSING_KEY_EVENT,
                severity=0.8,
                description=f"Missing {len(missing)} key events from outline",
                chapter_number=ch_num,
                fix_hint=f"Must include: {'; '.join(str(e)[:50] for e in missing[:2])}",
            ))
        return issues

    def _check_characters(self, content: str, outline, ch_num: int) -> list[StructuralIssue]:
        """Check if required characters appear in content."""
        issues: list[StructuralIssue] = []
        chars = getattr(outline, "characters_involved", []) or []
        content_lower = content.lower()

        missing = [c for c in chars if c.lower() not in content_lower]
        if len(missing) >= 2:  # 2+ missing = structural issue
            issues.append(StructuralIssue(
                issue_type=StructuralIssueType.WRONG_CHARACTERS,
                severity=0.75,
                description=f"Missing {len(missing)} required characters",
                chapter_number=ch_num,
                fix_hint=f"Must include characters: {', '.join(missing[:3])}",
            ))
        return issues

    def _check_arc_waypoints(self, content: str, arc_waypoints: list, ch_num: int) -> list[StructuralIssue]:
        """Check if arc waypoint milestones are addressed."""
        issues: list[StructuralIssue] = []
        for wp in arc_waypoints:
            wp_dict = wp if isinstance(wp, dict) else (wp.model_dump() if hasattr(wp, "model_dump") else {})
            ch_range = wp_dict.get("chapter_range", "")
            if not ch_range:
                continue
            try:
                parts = str(ch_range).replace(" ", "").split("-")
                start, end = int(parts[0]), int(parts[-1])
                if not (start <= ch_num <= end):
                    continue
            except Exception:
                continue

            milestone = wp_dict.get("milestone", "") or wp_dict.get("stage_name", "")
            if milestone:
                milestone_words = str(milestone).lower().split()[:2]
                if not any(w in content.lower() for w in milestone_words if len(w) > 3):
                    issues.append(StructuralIssue(
                        issue_type=StructuralIssueType.MISSED_ARC_WAYPOINT,
                        severity=0.7,
                        description=f"Arc waypoint not addressed: {milestone[:40]}",
                        chapter_number=ch_num,
                        fix_hint=f"Include arc milestone: {milestone[:60]}",
                    ))
                    break  # One waypoint issue per chapter max
        return issues

    def _check_pacing(self, content: str, outline, ch_num: int) -> list[StructuralIssue]:
        """Check if pacing matches outline expectation."""
        issues: list[StructuralIssue] = []
        pacing = getattr(outline, "pacing_type", "") or ""
        if not pacing:
            return issues

        content_lower = content.lower()
        pacing_lower = pacing.lower()

        # Heuristic: climax chapters should have dramatic action words
        if "climax" in pacing_lower or "cao trào" in pacing_lower:
            action_words = ["đánh", "chạy", "la hét", "nổ", "chết", "giết", "đau"]
            if not any(w in content_lower for w in action_words):
                issues.append(StructuralIssue(
                    issue_type=StructuralIssueType.PACING_VIOLATION,
                    severity=0.7,
                    description="Climax chapter lacks dramatic action",
                    chapter_number=ch_num,
                    fix_hint="Add intense action/conflict befitting climax pacing",
                ))
        return issues
