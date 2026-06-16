"""Shared chapter-contract construction for batch generation paths.

Extracted from batch_generator.py, where _run_batch_sequential and
_write_chapter_parallel each carried a near-identical inline block that
builds a ChapterContract and its prompt text. The two variants differ only
in what they feed build_contract:

- sequential passes proactive constraints (world rules + character secrets,
  gated by ``enable_proactive_constraints``) and the running list of
  previous contract failures;
- parallel may receive an already-built contract (``override_contract``)
  from a retry loop, in which case only the prompt text is (re)formatted.

Contract building is best-effort: failures are logged and the chapter is
written without a contract.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def build_contract_for_chapter(
    config,
    outline,
    *,
    threads,
    macro_arcs,
    conflicts,
    foreshadowing_plan,
    characters,
    draft=None,
    previous_failures=None,
    include_proactive=False,
    override_contract=None,
):
    """Build (contract, contract_text) for one chapter, or (None, "").

    Args:
        config: Pipeline config root (``config.pipeline`` holds the flags).
        outline: ChapterOutline being written.
        threads: Plot threads visible to this chapter (live or frozen).
        macro_arcs / conflicts / foreshadowing_plan / characters: L1 handoff
            inputs forwarded verbatim to ``build_contract``.
        draft: StoryDraft; only needed when *include_proactive* is True
            (source of ``draft.world.rules``).
        previous_failures: Running list of contract-failure feedback from
            earlier chapters in the batch (sequential path).
        include_proactive: Pass world rules + character secrets when the
            ``enable_proactive_constraints`` flag is also on.
        override_contract: Pre-built contract from a retry loop — skips
            building and only formats the prompt text.

    Returns:
        Tuple of (ChapterContract | None, prompt text). The text is ""
        whenever no contract is available.
    """
    contract = override_contract
    contract_text = ""
    if contract is None and getattr(config.pipeline, "enable_chapter_contracts", False):
        try:
            from pipeline.layer1_story.chapter_contract_builder import (
                build_contract,
                format_contract_for_prompt,
            )

            world_rules = None
            character_secrets = None
            if include_proactive and getattr(
                config.pipeline, "enable_proactive_constraints", False
            ):
                world_rules = getattr(draft.world, "rules", None) or []
                character_secrets = {
                    c.name: getattr(c, "secret", "")
                    for c in characters
                    if hasattr(c, "secret") and getattr(c, "secret", "")
                }
            contract = build_contract(
                outline.chapter_number,
                outline,
                threads=threads,
                macro_arcs=macro_arcs,
                conflicts=conflicts,
                foreshadowing_plan=foreshadowing_plan,
                characters=characters,
                previous_failures=previous_failures,
                world_rules=world_rules,
                character_secrets=character_secrets,
            )
            contract_text = format_contract_for_prompt(contract)
        except Exception as e:
            logger.warning(
                "Contract build failed for ch%d (non-fatal): %s",
                outline.chapter_number,
                e,
            )
    elif contract:
        from pipeline.layer1_story.chapter_contract_builder import (
            format_contract_for_prompt,
        )

        contract_text = format_contract_for_prompt(contract)
    return contract, contract_text
