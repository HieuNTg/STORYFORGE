"""Multi-agent debate orchestrator for Layer 2 enhancement."""
import logging
from models.schemas import AgentReview, DebateEntry, DebateResult, DebateStance

logger = logging.getLogger(__name__)

# Agents used in lite mode — editor aggregates, drama_critic spots tension issues,
# continuity_checker catches consistency breaks.  These cover the highest-ROI checks.
_LITE_MODE_AGENTS = {"editor_in_chief", "drama_critic", "continuity_checker"}


class DebateOrchestrator:
    def __init__(self, max_rounds=3, debate_mode: str = "full"):
        self.max_rounds = max_rounds
        self.debate_mode = debate_mode  # "full" | "lite"

    def run_debate(self, agents, story_draft, layer, round1_reviews, progress_callback=None):
        """Run debate protocol on top of existing Round 1 reviews.

        Lite mode: restricts participants to _LITE_MODE_AGENTS and caps at 1 round,
        saving ~85% of debate API calls while retaining the most impactful checks.

        Returns DebateResult with final_reviews.
        """
        if self.debate_mode == "lite":
            active_agents = [a for a in agents if a.role in _LITE_MODE_AGENTS]
            if not active_agents:
                # No lite agents found — skip entirely
                return DebateResult(
                    rounds=[[], []],
                    final_reviews=round1_reviews,
                    debate_skipped=True,
                    total_challenges=0,
                )
            if progress_callback:
                progress_callback(
                    f"[DEBATE-LITE] Using {len(active_agents)} key agents "
                    f"({', '.join(a.name for a in active_agents)})"
                )
        else:
            active_agents = agents

        # Round 2: Each agent responds to all reviews
        round2_entries = []
        for agent in active_agents:
            own_review = _find_review(round1_reviews, agent.name)
            if own_review is None:
                continue
            entries = agent.debate_response(story_draft, layer, own_review, round1_reviews)
            round2_entries.extend(entries)

        challenges = [e for e in round2_entries if e.stance == DebateStance.CHALLENGE]

        # If no challenges, skip debate
        if not challenges:
            return DebateResult(
                rounds=[[], round2_entries],
                final_reviews=round1_reviews,
                debate_skipped=True,
                total_challenges=0,
            )

        if progress_callback:
            progress_callback(
                f"[DEBATE] {len(challenges)} challenge(s) raised — running rebuttal round"
            )

        # Lite mode: skip rebuttal round (Round 3) — 1 round is sufficient
        if self.debate_mode == "lite":
            final_reviews = _merge_debate_into_reviews(round1_reviews, round2_entries)
            consensus = (
                sum(r.score for r in final_reviews) / len(final_reviews) if final_reviews else 0.0
            )
            if progress_callback:
                progress_callback(
                    f"[DEBATE-LITE] Done. consensus_score={consensus:.2f}, "
                    f"challenges={len(challenges)}"
                )
            return DebateResult(
                rounds=[[], round2_entries],
                final_reviews=final_reviews,
                consensus_score=consensus,
                total_challenges=len(challenges),
                debate_skipped=False,
            )

        # Round 3: Challenged agents rebut (full mode only)
        round3_entries = []
        challenged_agents = {c.target_agent for c in challenges}
        for agent in active_agents:
            if agent.name not in challenged_agents:
                continue
            own_review = _find_review(round1_reviews, agent.name)
            if own_review is None:
                continue
            # Pass round 2 entries as context for rebuttal
            entries = agent.debate_response(story_draft, layer, own_review, round1_reviews)
            for entry in entries:
                entry.round_number = 3
            round3_entries.extend(entries)

        # Synthesize final reviews: merge scores from debate entries with original reviews
        final_reviews = _merge_debate_into_reviews(
            round1_reviews, round2_entries + round3_entries
        )
        consensus = (
            sum(r.score for r in final_reviews) / len(final_reviews) if final_reviews else 0.0
        )

        if progress_callback:
            progress_callback(
                f"[DEBATE] Done. consensus_score={consensus:.2f}, "
                f"challenges={len(challenges)}"
            )

        return DebateResult(
            rounds=[[], round2_entries, round3_entries],
            final_reviews=final_reviews,
            consensus_score=consensus,
            total_challenges=len(challenges),
            debate_skipped=False,
        )


def _find_review(reviews, agent_name):
    for r in reviews:
        if r.agent_name == agent_name:
            return r
    return None


def _merge_debate_into_reviews(original_reviews, debate_entries):
    """Merge debate entries into original reviews — adjust scores based on challenges/supports."""
    reviews_map = {r.agent_name: r.model_copy() for r in original_reviews}
    for entry in debate_entries:
        if entry.target_agent in reviews_map and entry.revised_score is not None:
            # Average original score with revised score from debate
            target = reviews_map[entry.target_agent]
            target.score = (target.score + entry.revised_score) / 2
        # Append debate reasoning to suggestions
        if entry.target_agent in reviews_map and entry.reasoning:
            target = reviews_map[entry.target_agent]
            target.suggestions.append(f"[Debate-{entry.agent_name}] {entry.reasoning}")
    return list(reviews_map.values())
