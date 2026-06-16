"""Agent-review aggregation helpers for the smart revision service.

Internal module for ``smart_revision``: stateless functions that scan agent
reviews to (a) collect the issues/suggestions relevant to one chapter and
(b) find chapters with enough reported issues to warrant revision. They hold
no LLM/scorer state, so they live outside ``SmartRevisionService`` and are
imported by it. Kept separate so the service module stays under the
200-line rule.
"""

import re

from models.schemas import AgentReview


def aggregate_review_guidance(
    chapter_number: int, reviews: list[AgentReview]
) -> tuple[list[str], list[str]]:
    """Collect relevant issues and suggestions for a specific chapter.

    Returns (issues, suggestions) capped at 5 each.
    """
    issues = []
    suggestions = []
    # Word-boundary regex to avoid false positives (e.g. "1" matching "chương 10")
    ch_pattern = re.compile(rf"\bch(?:ương\s*)?{chapter_number}\b", re.IGNORECASE)

    def _mentions_chapter(text: str) -> bool:
        return bool(ch_pattern.search(text))

    for review in reviews:
        # Chapter-specific: mentions this chapter number
        for issue in review.issues:
            if _mentions_chapter(issue):
                issues.append(f"[{review.agent_name}] {issue}")
        for suggestion in review.suggestions:
            sug_text = str(suggestion)
            if _mentions_chapter(sug_text):
                suggestions.append(f"[{review.agent_name}] {sug_text}")

        # General issues from low-scoring agents (not chapter-specific)
        if review.score < 0.6:
            for issue in review.issues:
                if not _mentions_chapter(issue) and len(issues) < 5:
                    issues.append(f"[{review.agent_name}] {issue}")
            for suggestion in review.suggestions:
                sug_text = str(suggestion)
                if not _mentions_chapter(sug_text) and len(suggestions) < 5:
                    suggestions.append(f"[{review.agent_name}] {sug_text}")

    return issues[:5], suggestions[:5]


def find_chapters_with_agent_issues(
    reviews: list[AgentReview], min_issues: int = 3
) -> set[int]:
    """Find chapters that have significant issues from agent reviews.

    Even if overall quality score is OK, chapters with many agent-reported
    issues should be revised.

    Returns set of chapter numbers with >= min_issues total issues.
    """
    chapter_issue_count: dict[int, int] = {}
    ch_pattern = re.compile(r"\bch(?:ương\s*)?(\d+)\b", re.IGNORECASE)

    for review in reviews:
        # Count issues per chapter
        for issue in review.issues:
            matches = ch_pattern.findall(issue)
            for ch_num_str in matches:
                ch_num = int(ch_num_str)
                chapter_issue_count[ch_num] = chapter_issue_count.get(ch_num, 0) + 1

        # Also count suggestions as potential issues
        for suggestion in review.suggestions:
            matches = ch_pattern.findall(str(suggestion))
            for ch_num_str in matches:
                ch_num = int(ch_num_str)
                chapter_issue_count[ch_num] = chapter_issue_count.get(ch_num, 0) + 1

    return {ch for ch, count in chapter_issue_count.items() if count >= min_issues}
