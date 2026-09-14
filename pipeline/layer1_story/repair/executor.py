"""Turn a `RepairPlan` into exactly one rewritten chapter.

One plan, one LLM call, no retries of its own — retrying is the coordinator's
job and it pays for it out of the same budget.
"""

from __future__ import annotations

import logging

from pipeline.layer1_story.repair.prompts import REPAIR_CHAPTER, REPAIR_SYSTEM

logger = logging.getLogger(__name__)

# Same ceiling the legacy length gate used; the unified rewrite has strictly
# more to say than any single legacy pass, never less.
_MAX_TOKENS = 8192

# A "rewrite" that comes back as a fragment is the model summarising the chapter
# instead of repairing it. Mirrors the guard in `rewrite_for_consistency`.
_MIN_RATIO_OF_ORIGINAL = 0.5


def execute_repair(plan, ctx, budget) -> str | None:
    """Run the unified rewrite. Returns new content, or None if nothing usable.

    Spends exactly one call from `budget`. Never raises: every failure path
    returns None so the coordinator can fall back with the chapter intact.
    """
    if plan.strategy == "skip":
        return None
    content = getattr(ctx.chapter, "content", "") or ""
    if not content:
        return None

    from services.text_utils import build_idea_header
    from pipeline.layer1_story.chapter_self_critique import strip_llm_preamble

    idea_header = build_idea_header(ctx.idea, ctx.idea_summary) if ctx.idea else ""

    fixes = "\n".join(f"{i}. {t}" for i, t in enumerate(plan.ordered_fixes, 1))
    constraints = "\n".join(f"- {c}" for c in plan.constraints) or "- (không có)"

    user_prompt = REPAIR_CHAPTER.format(
        user_story_idea_header=idea_header,
        n_issues=len(plan.ordered_fixes),
        fixes=fixes,
        constraints=constraints,
        content=content,
    )

    if not budget.spend(1):
        return None
    try:
        revised = ctx.llm.generate(
            system_prompt=REPAIR_SYSTEM,
            user_prompt=user_prompt,
            model=ctx.layer_model,
            max_tokens=_MAX_TOKENS,
        )
    except Exception as exc:
        logger.warning(
            "Ch%s repair rewrite failed (non-fatal): %s", ctx.chapter_number, exc
        )
        return None

    if not isinstance(revised, str):
        return None
    revised = strip_llm_preamble(revised)
    if len(revised) < max(100, int(len(content) * _MIN_RATIO_OF_ORIGINAL)):
        logger.warning(
            "Ch%s repair rewrite came back at %d chars (was %d) — discarding",
            ctx.chapter_number,
            len(revised),
            len(content),
        )
        return None
    if revised == content:
        return None
    return revised
