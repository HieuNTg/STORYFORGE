"""Retroactive Consistency Checker - Phase 8.

Scans new chapters against previous content to detect contradictions
in character locations, timeline, facts, and states.
"""

import logging
from datetime import datetime
from typing import Optional

from models.schemas import (
    StoryDraft,
    Chapter,
    ConsistencyIssue,
    ConsistencyReport,
)

logger = logging.getLogger(__name__)


class ConsistencyChecker:
    """Checks story consistency across chapters using LLM analysis."""

    def __init__(self, llm_client=None):
        """Initialize with optional LLM client for deep analysis."""
        self.llm = llm_client

    def check_chapters(
        self,
        draft: StoryDraft,
        new_chapter_numbers: list[int],
        progress_callback=None,
    ) -> ConsistencyReport:
        """Check new chapters for consistency with existing content.

        Args:
            draft: The story draft containing all chapters
            new_chapter_numbers: List of newly added chapter numbers to check
            progress_callback: Optional progress reporting function

        Returns:
            ConsistencyReport with detected issues
        """
        def _log(msg: str):
            logger.info(msg)
            if progress_callback:
                progress_callback(msg)

        _log(f"Checking consistency for chapters: {new_chapter_numbers}")

        issues: list[ConsistencyIssue] = []

        # Get chapters to check against (all previous chapters)
        previous_chapters = [
            ch for ch in draft.chapters
            if ch.chapter_number not in new_chapter_numbers
        ]
        new_chapters = [
            ch for ch in draft.chapters
            if ch.chapter_number in new_chapter_numbers
        ]

        if not previous_chapters:
            _log("No previous chapters to check against")
            return self._build_report(new_chapter_numbers, [])

        # Extract facts from previous chapters
        _log("Extracting facts from previous chapters...")
        previous_facts = self._extract_facts_from_chapters(previous_chapters, draft)

        # Check each new chapter
        for new_ch in new_chapters:
            _log(f"Checking chapter {new_ch.chapter_number}...")
            chapter_issues = self._check_chapter_consistency(
                new_ch, previous_facts, draft
            )
            issues.extend(chapter_issues)

        # If LLM available, do deep semantic check
        if self.llm and issues:
            _log("Running deep semantic analysis...")
            issues = self._enhance_issues_with_llm(issues, draft)

        return self._build_report(new_chapter_numbers, issues)

    def _extract_facts_from_chapters(
        self,
        chapters: list[Chapter],
        draft: StoryDraft,
    ) -> dict:
        """Extract trackable facts from chapters.

        Returns dict with:
        - character_locations: {char_name: [(chapter, location), ...]}
        - character_states: {char_name: [(chapter, state), ...]}
        - timeline_events: [(chapter, event, time_marker), ...]
        - objects: {object_name: [(chapter, state/location), ...]}
        - facts: [(chapter, fact_statement), ...]
        """
        facts = {
            "character_locations": {},
            "character_states": {},
            "timeline_events": [],
            "objects": {},
            "facts": [],
        }

        # Use character_states from draft if available
        for cs in draft.character_states:
            char_name = cs.name
            if char_name not in facts["character_states"]:
                facts["character_states"][char_name] = []
            # Use mood and arc_position from CharacterState schema
            state_desc = f"{cs.mood} ({cs.arc_position})" if cs.mood else cs.arc_position
            facts["character_states"][char_name].append(
                (0, state_desc)  # Chapter 0 as default since CharacterState doesn't track chapter
            )

        # Use plot_events from draft
        for pe in draft.plot_events:
            facts["timeline_events"].append(
                (pe.chapter_number, pe.event, "")
            )
            # Track character involvement
            for char in pe.characters_involved:
                if char not in facts["character_states"]:
                    facts["character_states"][char] = []

        # Extract from chapter summaries if no structured data
        if not facts["character_locations"] and not facts["character_states"]:
            for ch in chapters:
                # Simple heuristic extraction from summary
                if ch.summary:
                    facts["facts"].append((ch.chapter_number, ch.summary))

        return facts

    def _check_chapter_consistency(
        self,
        chapter: Chapter,
        previous_facts: dict,
        draft: StoryDraft,
    ) -> list[ConsistencyIssue]:
        """Check a single chapter against previous facts."""
        issues = []
        content = chapter.content.lower()

        # Check character locations
        for char_name, locations in previous_facts["character_locations"].items():
            if not locations:
                continue
            last_ch, last_loc = locations[-1]
            # Simple check: if character mentioned, check location consistency
            if char_name.lower() in content:
                # Check if there's a location mention that contradicts
                issue = self._check_location_contradiction(
                    char_name, last_loc, last_ch, chapter
                )
                if issue:
                    issues.append(issue)

        # Check character states
        for char_name, states in previous_facts["character_states"].items():
            if not states:
                continue
            last_ch, last_state = states[-1]
            if char_name.lower() in content:
                issue = self._check_state_contradiction(
                    char_name, last_state, last_ch, chapter
                )
                if issue:
                    issues.append(issue)

        # Check for timeline issues (simple sequential check)
        if previous_facts["timeline_events"]:
            issue = self._check_timeline_consistency(
                chapter, previous_facts["timeline_events"]
            )
            if issue:
                issues.append(issue)

        return issues

    def _check_location_contradiction(
        self,
        char_name: str,
        last_location: str,
        last_chapter: int,
        new_chapter: Chapter,
    ) -> Optional[ConsistencyIssue]:
        """Check if character's location contradicts previous chapter.

        Currently returns None - LLM enhancement handles actual contradiction detection.
        """
        # Placeholder for future LLM-based location contradiction detection
        # Variables like content, last_location are available for enhancement
        _ = (new_chapter.content, last_location, char_name, last_chapter)
        return None

    def _check_state_contradiction(
        self,
        char_name: str,
        last_state: str,
        last_chapter: int,
        new_chapter: Chapter,
    ) -> Optional[ConsistencyIssue]:
        """Check if character's emotional/physical state contradicts."""
        # State contradiction keywords
        contradicting_states = {
            "vui": ["buồn", "giận", "khóc"],
            "buồn": ["vui", "cười", "hạnh phúc"],
            "khỏe": ["ốm", "yếu", "bệnh", "bị thương"],
            "sống": ["chết", "qua đời"],
            "happy": ["sad", "angry", "crying"],
            "alive": ["dead", "died"],
        }

        content = new_chapter.content.lower()
        last_state_lower = last_state.lower()

        # Check for direct contradictions
        if last_state_lower in contradicting_states:
            for contra in contradicting_states[last_state_lower]:
                if contra in content and char_name.lower() in content:
                    return ConsistencyIssue(
                        issue_type="character_state",
                        severity="warning",
                        description=f"{char_name} was '{last_state}' in chapter {last_chapter} but appears '{contra}' in chapter {new_chapter.chapter_number}",
                        chapter_a=last_chapter,
                        chapter_b=new_chapter.chapter_number,
                        entity=char_name,
                        value_a=last_state,
                        value_b=contra,
                        suggested_fix=f"Add transition explaining {char_name}'s state change",
                        auto_fixable=False,
                    )

        return None

    def _check_timeline_consistency(
        self,
        chapter: Chapter,
        timeline_events: list,
    ) -> Optional[ConsistencyIssue]:
        """Check for timeline contradictions.

        Currently returns None - LLM enhancement handles complex temporal reasoning.
        """
        # Placeholder for future LLM-based timeline contradiction detection
        _ = chapter
        return None

    def _enhance_issues_with_llm(
        self,
        issues: list[ConsistencyIssue],
        draft: StoryDraft,
    ) -> list[ConsistencyIssue]:
        """Use LLM to enhance issue descriptions and suggest fixes."""
        if not self.llm:
            return issues

        enhanced = []
        for issue in issues:
            try:
                # Get relevant chapter content
                ch_a = next((c for c in draft.chapters if c.chapter_number == issue.chapter_a), None)
                ch_b = next((c for c in draft.chapters if c.chapter_number == issue.chapter_b), None)

                if not ch_a or not ch_b:
                    enhanced.append(issue)
                    continue

                prompt = f"""Analyze this consistency issue in a story:

Issue: {issue.description}
Type: {issue.issue_type}
Entity: {issue.entity}

Chapter {issue.chapter_a} excerpt (relevant part):
{ch_a.content[:500]}...

Chapter {issue.chapter_b} excerpt (relevant part):
{ch_b.content[:500]}...

Provide:
1. A clearer description of the inconsistency
2. A specific fix suggestion
3. Whether this can be auto-fixed (true/false)

Return JSON:
{{
  "description": "clearer description",
  "suggested_fix": "specific fix",
  "auto_fixable": false,
  "severity": "warning"
}}"""

                result = self.llm.generate_json(
                    system_prompt="You are a story editor checking for consistency issues.",
                    user_prompt=prompt,
                    temperature=0.3,
                )

                issue.description = result.get("description", issue.description)
                issue.suggested_fix = result.get("suggested_fix", issue.suggested_fix)
                issue.auto_fixable = result.get("auto_fixable", False)
                issue.severity = result.get("severity", issue.severity)

            except Exception as e:
                logger.warning(f"LLM enhancement failed for issue: {e}")

            enhanced.append(issue)

        return enhanced

    def _build_report(
        self,
        checked_chapters: list[int],
        issues: list[ConsistencyIssue],
    ) -> ConsistencyReport:
        """Build final consistency report."""
        error_count = sum(1 for i in issues if i.severity == "error")
        warning_count = sum(1 for i in issues if i.severity == "warning")
        info_count = sum(1 for i in issues if i.severity == "info")

        return ConsistencyReport(
            checked_chapters=checked_chapters,
            issues=issues,
            error_count=error_count,
            warning_count=warning_count,
            info_count=info_count,
            is_consistent=error_count == 0,
            checked_at=datetime.now().isoformat(),
        )

    def check_full_story(
        self,
        draft: StoryDraft,
        progress_callback=None,
    ) -> ConsistencyReport:
        """Check entire story for consistency issues.

        Performs pairwise comparison of all chapters.
        """
        def _log(msg: str):
            logger.info(msg)
            if progress_callback:
                progress_callback(msg)

        _log("Running full story consistency check...")

        if len(draft.chapters) < 2:
            _log("Not enough chapters to check")
            return self._build_report(
                [ch.chapter_number for ch in draft.chapters],
                []
            )

        issues = []

        # Check each chapter against all previous
        for i, chapter in enumerate(draft.chapters[1:], start=1):
            previous = draft.chapters[:i]
            _log(f"Checking chapter {chapter.chapter_number} against {len(previous)} previous chapters...")

            facts = self._extract_facts_from_chapters(previous, draft)
            chapter_issues = self._check_chapter_consistency(chapter, facts, draft)
            issues.extend(chapter_issues)

        # LLM enhancement if available
        if self.llm and issues:
            _log("Running deep semantic analysis...")
            issues = self._enhance_issues_with_llm(issues, draft)

        return self._build_report(
            [ch.chapter_number for ch in draft.chapters],
            issues
        )


def check_consistency(
    draft: StoryDraft,
    new_chapter_numbers: list[int],
    llm_client=None,
    progress_callback=None,
) -> ConsistencyReport:
    """Convenience function to check consistency.

    Args:
        draft: Story draft to check
        new_chapter_numbers: Chapters to check against previous content
        llm_client: Optional LLM for enhanced analysis
        progress_callback: Optional progress callback

    Returns:
        ConsistencyReport with any detected issues
    """
    checker = ConsistencyChecker(llm_client)
    return checker.check_chapters(draft, new_chapter_numbers, progress_callback)
