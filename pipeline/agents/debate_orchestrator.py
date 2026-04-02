"""Multi-agent debate orchestrator for Layer 2 enhancement."""
import logging
from models.schemas import AgentReview, DebateEntry, DebateResult, DebateStance

logger = logging.getLogger(__name__)

# Agents used in lite mode — editor aggregates, drama_critic spots tension issues,
# continuity_checker catches consistency breaks.  These cover the highest-ROI checks.
_LITE_MODE_AGENTS = {"editor_in_chief", "drama_critic", "continuity_checker"}

# ---------------------------------------------------------------------------
# Budget cap configuration for agent debate
# These defaults can be overridden via constructor kwargs or subclassing.
# ---------------------------------------------------------------------------
MAX_DEBATE_TOKENS_PER_ROUND: int = 4_000    # token budget per debate round
MAX_DEBATE_TOTAL_TOKENS: int = 30_000       # cumulative token cap for the whole debate
MAX_DEBATE_COST_USD: float = 0.50           # cumulative USD cap for the whole debate
# Action when a budget limit is exceeded:
#   "warn"  — log a warning and continue (default)
#   "skip"  — skip remaining rounds, use best result collected so far
#   "abort" — raise BudgetExceededError immediately
DEBATE_BUDGET_ACTION: str = "warn"


class BudgetExceededError(RuntimeError):
    """Raised when DEBATE_BUDGET_ACTION == 'abort' and a budget cap is hit."""


class DebateOrchestrator:
    def __init__(
        self,
        max_rounds: int = 3,
        debate_mode: str = "full",
        *,
        max_tokens_per_round: int = MAX_DEBATE_TOKENS_PER_ROUND,
        max_total_tokens: int = MAX_DEBATE_TOTAL_TOKENS,
        max_cost_usd: float = MAX_DEBATE_COST_USD,
        budget_action: str = DEBATE_BUDGET_ACTION,
        story_id: str = "",
    ) -> None:
        self.max_rounds = max_rounds
        self.debate_mode = debate_mode  # "full" | "lite"

        # Budget cap settings
        self._max_tokens_per_round = max_tokens_per_round
        self._max_total_tokens = max_total_tokens
        self._max_cost_usd = max_cost_usd
        self._budget_action = budget_action
        self._story_id = story_id

        # Session accumulators (reset each run_debate call)
        self._session_tokens: int = 0
        self._session_cost_usd: float = 0.0

    def run_debate(self, agents, story_draft, layer, round1_reviews, progress_callback=None):
        """Run debate protocol on top of existing Round 1 reviews.

        Lite mode: restricts participants to _LITE_MODE_AGENTS and caps at 1 round,
        saving ~85% of debate API calls while retaining the most impactful checks.

        Budget caps (MAX_DEBATE_TOKENS_PER_ROUND, MAX_DEBATE_TOTAL_TOKENS,
        MAX_DEBATE_COST_USD) are checked before each round.  Behaviour when a
        cap is exceeded is controlled by DEBATE_BUDGET_ACTION / budget_action:
          "warn"  — log warning and continue
          "skip"  — stop further rounds, return best result so far
          "abort" — raise BudgetExceededError

        Returns DebateResult with final_reviews.
        """
        # Reset per-run accumulators
        self._session_tokens = 0
        self._session_cost_usd = 0.0

        # Import tracker lazily to avoid circular imports; silently skip on failure
        try:
            from services.token_cost_tracker import TokenCostTracker
            _tracker = TokenCostTracker()
        except Exception:
            _tracker = None

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

        # ------------------------------------------------------------------
        # Round 2: Each agent responds to all reviews
        # ------------------------------------------------------------------
        if self._budget_exceeded(round_label="Round 2", progress_callback=progress_callback):
            return DebateResult(
                rounds=[[], []],
                final_reviews=round1_reviews,
                debate_skipped=True,
                total_challenges=0,
            )

        round2_entries = []
        round2_tokens = 0
        for agent in active_agents:
            own_review = _find_review(round1_reviews, agent.name)
            if own_review is None:
                continue
            entries = agent.debate_response(story_draft, layer, own_review, round1_reviews)
            round2_entries.extend(entries)

            # Estimate token usage for this agent's debate response calls.
            # Agents don't expose token counts directly, so we approximate via
            # the system/user prompts used (rough estimate: 200 tokens per call).
            # This is replaced by exact counts when agents expose llm.last_usage.
            agent_tokens = _estimate_agent_tokens(agent)
            round2_tokens += agent_tokens
            agent_cost = _estimate_agent_cost(agent_tokens, agent)

            self._session_tokens += agent_tokens
            self._session_cost_usd += agent_cost

            if _tracker is not None:
                try:
                    model = _get_agent_model(agent)
                    pt = agent_tokens // 2
                    ct = agent_tokens - pt
                    _tracker.track_usage(
                        story_id=self._story_id or "debate",
                        layer=layer,
                        agent=getattr(agent, "name", str(agent)),
                        model=model,
                        prompt_tokens=pt,
                        completion_tokens=ct,
                    )
                except Exception as exc:
                    logger.debug("TokenCostTracker.track_usage failed: %s", exc)

            # Per-round token budget check mid-round
            if round2_tokens > self._max_tokens_per_round:
                msg = (
                    f"[DEBATE] Round 2 token budget exceeded "
                    f"({round2_tokens} > {self._max_tokens_per_round})"
                )
                if self._budget_action == "abort":
                    raise BudgetExceededError(msg)
                logger.warning(msg)
                if progress_callback:
                    progress_callback(msg)
                if self._budget_action == "skip":
                    logger.info("[DEBATE] Skipping remaining Round 2 agents due to budget cap")
                    break

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

        # ------------------------------------------------------------------
        # Round 3: Challenged agents rebut (full mode only)
        # ------------------------------------------------------------------
        if self._budget_exceeded(round_label="Round 3", progress_callback=progress_callback):
            # Graceful early stop: use what we have from Round 2
            final_reviews = _merge_debate_into_reviews(round1_reviews, round2_entries)
            consensus = (
                sum(r.score for r in final_reviews) / len(final_reviews) if final_reviews else 0.0
            )
            return DebateResult(
                rounds=[[], round2_entries, []],
                final_reviews=final_reviews,
                consensus_score=consensus,
                total_challenges=len(challenges),
                debate_skipped=False,
            )

        round3_entries = []
        round3_tokens = 0
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

            agent_tokens = _estimate_agent_tokens(agent)
            round3_tokens += agent_tokens
            agent_cost = _estimate_agent_cost(agent_tokens, agent)

            self._session_tokens += agent_tokens
            self._session_cost_usd += agent_cost

            if _tracker is not None:
                try:
                    model = _get_agent_model(agent)
                    pt = agent_tokens // 2
                    ct = agent_tokens - pt
                    _tracker.track_usage(
                        story_id=self._story_id or "debate",
                        layer=layer,
                        agent=getattr(agent, "name", str(agent)),
                        model=model,
                        prompt_tokens=pt,
                        completion_tokens=ct,
                    )
                except Exception as exc:
                    logger.debug("TokenCostTracker.track_usage failed: %s", exc)

            # Per-round and total budget checks mid-round
            if round3_tokens > self._max_tokens_per_round:
                msg = (
                    f"[DEBATE] Round 3 token budget exceeded "
                    f"({round3_tokens} > {self._max_tokens_per_round})"
                )
                if self._budget_action == "abort":
                    raise BudgetExceededError(msg)
                logger.warning(msg)
                if progress_callback:
                    progress_callback(msg)
                if self._budget_action == "skip":
                    logger.info("[DEBATE] Stopping Round 3 early due to per-round budget cap")
                    break

            if self._session_tokens > self._max_total_tokens:
                msg = (
                    f"[DEBATE] Total token budget exceeded "
                    f"({self._session_tokens} > {self._max_total_tokens})"
                )
                if self._budget_action == "abort":
                    raise BudgetExceededError(msg)
                logger.warning(msg)
                if progress_callback:
                    progress_callback(msg)
                if self._budget_action == "skip":
                    logger.info("[DEBATE] Stopping Round 3 early due to total token budget cap")
                    break

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
                f"challenges={len(challenges)}, "
                f"total_tokens={self._session_tokens}, "
                f"est_cost=${self._session_cost_usd:.4f}"
            )

        return DebateResult(
            rounds=[[], round2_entries, round3_entries],
            final_reviews=final_reviews,
            consensus_score=consensus,
            total_challenges=len(challenges),
            debate_skipped=False,
        )

    # ------------------------------------------------------------------
    # Budget helpers
    # ------------------------------------------------------------------

    def _budget_exceeded(self, round_label: str, progress_callback=None) -> bool:
        """Check cumulative budget before starting a new round.

        Returns True if the budget_action is "skip" and a cap is hit,
        meaning the caller should stop and return the best result so far.
        Raises BudgetExceededError if budget_action is "abort".
        Never returns True when budget_action is "warn".
        """
        violations: list[str] = []

        if self._session_tokens >= self._max_total_tokens:
            violations.append(
                f"total tokens {self._session_tokens} >= {self._max_total_tokens}"
            )
        if self._session_cost_usd >= self._max_cost_usd:
            violations.append(
                f"total cost ${self._session_cost_usd:.4f} >= ${self._max_cost_usd:.2f}"
            )

        if not violations:
            return False

        msg = f"[DEBATE] Budget cap hit before {round_label}: {'; '.join(violations)}"

        if self._budget_action == "abort":
            raise BudgetExceededError(msg)

        logger.warning(msg)
        if progress_callback:
            progress_callback(msg)

        return self._budget_action == "skip"


# ---------------------------------------------------------------------------
# Private utility functions
# ---------------------------------------------------------------------------

def _get_agent_model(agent) -> str:
    """Return the model name used by an agent (best-effort)."""
    try:
        from config import ConfigManager
        config = ConfigManager()
        return config.llm.model or "unknown"
    except Exception:
        return "unknown"


def _estimate_agent_tokens(agent) -> int:
    """Return token count for the agent's last LLM call.

    Agents currently do not expose per-call token counts, so we fall back
    to a conservative estimate of 300 tokens per debate response call.
    When agents are updated to expose last_usage, this will use exact counts.
    """
    # Future: return agent.llm.last_usage.total_tokens if available
    try:
        # If agent exposes last_usage from a patched LLMClient, prefer it
        usage = getattr(agent, "_last_token_usage", None)
        if usage and isinstance(usage, dict):
            return int(usage.get("total_tokens", 300))
    except Exception:
        pass
    return 300  # conservative default


def _estimate_agent_cost(tokens: int, agent) -> float:
    """Estimate USD cost for given token count using the agent's model pricing."""
    try:
        from services.token_cost_tracker import TokenCostTracker, DEFAULT_PRICING
        model = _get_agent_model(agent)
        # TokenCostTracker is a singleton — use its pricing table
        tracker = TokenCostTracker()
        pt = tokens // 2
        ct = tokens - pt
        return tracker._compute_cost(model, pt, ct)
    except Exception:
        return 0.0


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
