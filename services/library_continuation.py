"""Bridge the localStorage Library to the real continuation pipeline.

The Library is client-side only (see CLAUDE.md / library-store.ts): a story lives
in localStorage and has no server-side id. The continuation stack
(`StoryContinuation`), by contrast, is checkpoint-based — it needs a
``PipelineOutput`` with a ``StoryDraft`` before it can plan outlines and write
chapters with real context.

This module is that bridge. It takes the client's story payload and produces a
``PipelineOutput`` suitable for `PipelineOrchestrator.continue_story`, using the
best source available:

``checkpoint``
    The story was produced by `/api/pipeline/run`, so a checkpoint exists on
    disk under a deterministic name derived from the title (see
    ``orchestrator_checkpoint.save``). That file carries the full L1 signal set
    — voice profiles, macro arcs, conflict web, foreshadowing plan, story bible,
    character states, open threads — none of which survive the trip through
    localStorage. We load it and graft the client's prose on top, because the
    client is the source of truth for what the reader has actually read.

``payload``
    Forge-born or imported stories have no checkpoint. We build a draft from the
    payload alone. Planning signals start empty; the continuation still gets
    title/genre/world/characters/summaries, which is the context that matters
    most for coherence.

Nothing here calls an LLM — hydration is pure data assembly.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Literal, Optional

from pydantic import BaseModel, Field

from models.schemas import (
    Chapter,
    Character,
    PipelineOutput,
    StoryDraft,
    WorldSetting,
)

logger = logging.getLogger(__name__)

HydrationSource = Literal["checkpoint", "payload"]

# Summary fallback for chapters that reach us without one. Cheap and
# deterministic: `rebuild_context` warns (and loses context) on empty summaries,
# and an excerpt beats nothing without burning a model call per chapter.
_SUMMARY_FALLBACK_CHARS = 400


class LibraryChapterPayload(BaseModel):
    """One chapter as persisted by the frontend library store."""

    title: str = ""
    content: str = ""
    summary: str = ""


class LibraryCharacterPayload(BaseModel):
    """A ForgeCharacter as persisted by the frontend library store."""

    name: str = ""
    role: str = ""
    description: str = ""
    backstory: str = ""
    secret: str = ""
    conflict: str = ""


class LibraryStoryPayload(BaseModel):
    """The localStorage `Story` shape, as far as continuation cares about it.

    Deliberately lenient: every field defaults, because stories predate several
    of these fields and a missing one must degrade quality, not 422 the request.
    """

    id: str = ""
    title: str = "Untitled"
    genre: str = ""
    setting: str = ""
    tone: str = ""
    description: str = ""
    language: str = "vi"
    targetChapters: Optional[int] = Field(default=None, ge=1, le=500)
    characters: list[LibraryCharacterPayload] = Field(default_factory=list)
    chapters: list[LibraryChapterPayload] = Field(default_factory=list, max_length=500)


def _fallback_summary(content: str) -> str:
    """Excerpt a chapter's opening as a stand-in summary."""
    text = " ".join((content or "").split())
    if len(text) <= _SUMMARY_FALLBACK_CHARS:
        return text
    return text[:_SUMMARY_FALLBACK_CHARS].rsplit(" ", 1)[0] + "…"


def _checkpoint_basename(title: str, layer: int) -> str:
    """Reproduce ``CheckpointManager.save``'s filename for a title.

    Must stay in lockstep with `pipeline/orchestrator_checkpoint.py::save`.
    """
    hash_id = hashlib.sha256(title.encode()).hexdigest()[:16]
    slug = re.sub(r"[^\w\-]", "_", title[:30])
    return f"{slug}_layer{layer}_{hash_id}.json"


def resolve_story_checkpoint(title: str) -> Optional[str]:
    """Find the on-disk checkpoint for a story title, newest layer first.

    Returns None when the story never went through `/api/pipeline/run` (forge or
    imported stories), which is a normal, non-error condition.
    """
    if not title:
        return None
    from pipeline.orchestrator_checkpoint import find_checkpoint_path

    for layer in (2, 1):
        found = find_checkpoint_path(_checkpoint_basename(title, layer))
        if found:
            return found
    return None


def _payload_characters(payload: LibraryStoryPayload) -> list[Character]:
    out: list[Character] = []
    for c in payload.characters:
        if not (c.name or "").strip():
            continue
        # `secret` has no home on Character; fold it into background so the
        # continuation prompts can still see it rather than dropping it.
        background = c.backstory or ""
        if c.secret:
            background = f"{background}\nBí mật: {c.secret}".strip()
        out.append(
            Character(
                name=c.name,
                role=c.role or "supporting",
                personality=c.description or "Chưa xác định",
                background=background,
                motivation=c.conflict or "",
                internal_conflict=c.conflict or "",
            )
        )
    return out


def _payload_chapters(payload: LibraryStoryPayload) -> list[Chapter]:
    return [
        Chapter(
            chapter_number=i + 1,
            title=ch.title or f"Chương {i + 1}",
            content=ch.content or "",
            word_count=len((ch.content or "").split()),
            summary=ch.summary or _fallback_summary(ch.content),
        )
        for i, ch in enumerate(payload.chapters)
    ]


def _payload_world(payload: LibraryStoryPayload) -> Optional[WorldSetting]:
    if not (payload.setting or payload.description):
        return None
    return WorldSetting(
        name=payload.setting or payload.title,
        description=payload.setting or payload.description,
        era=payload.tone or "",
    )


def payload_to_draft(payload: LibraryStoryPayload) -> StoryDraft:
    """Build a StoryDraft from the client story alone (no checkpoint available)."""
    return StoryDraft(
        title=payload.title or "Untitled",
        genre=payload.genre or "",
        synopsis=payload.description or "",
        characters=_payload_characters(payload),
        chapters=_payload_chapters(payload),
        world=_payload_world(payload),
        original_idea=payload.description or "",
        target_total_chapters=payload.targetChapters,
    )


def _graft_client_prose(draft: StoryDraft, payload: LibraryStoryPayload) -> None:
    """Reconcile a checkpoint draft with what the client actually holds.

    The client is authoritative for prose: the reader may have continued the
    story via the old forge path, or edited chapters, after the checkpoint was
    written. Chapters the checkpoint already knows keep their rich metadata
    (structured_summary, contracts) and only take the client's text when it
    differs; chapters the client has beyond the checkpoint are appended.

    A checkpoint holding MORE chapters than the client is left alone — that is a
    stale-client situation, and truncating the server's story to match would
    destroy work.
    """
    client_chapters = payload.chapters
    for i, ch in enumerate(client_chapters):
        if i < len(draft.chapters):
            existing = draft.chapters[i]
            if ch.content and ch.content != existing.content:
                existing.content = ch.content
                existing.word_count = len(ch.content.split())
                existing.summary = ch.summary or _fallback_summary(ch.content)
                # Rich metadata described the superseded text — drop it rather
                # than let stale contracts steer the continuation.
                existing.structured_summary = None
            elif not existing.summary:
                existing.summary = ch.summary or _fallback_summary(existing.content)
            if ch.title:
                existing.title = ch.title
        else:
            draft.chapters.append(
                Chapter(
                    chapter_number=i + 1,
                    title=ch.title or f"Chương {i + 1}",
                    content=ch.content or "",
                    word_count=len((ch.content or "").split()),
                    summary=ch.summary or _fallback_summary(ch.content),
                )
            )

    if payload.targetChapters is not None:
        draft.target_total_chapters = payload.targetChapters
    if payload.description and not draft.synopsis:
        draft.synopsis = payload.description
    if not draft.characters:
        draft.characters = _payload_characters(payload)
    if draft.world is None:
        draft.world = _payload_world(payload)


def hydrate_output(
    payload: LibraryStoryPayload,
) -> tuple[PipelineOutput, HydrationSource]:
    """Produce a PipelineOutput ready for the continuation stack.

    Returns the output plus which source it came from, so the caller can tell the
    user whether they are getting full-fidelity continuation or the reduced one.
    """
    checkpoint_path = resolve_story_checkpoint(payload.title)
    if checkpoint_path:
        try:
            with open(checkpoint_path, "r", encoding="utf-8") as f:
                output = PipelineOutput(**json.load(f))
            if output.story_draft is not None:
                _graft_client_prose(output.story_draft, payload)
                logger.info(
                    "Library continuation hydrated from checkpoint %s (%d chapters)",
                    checkpoint_path,
                    len(output.story_draft.chapters),
                )
                return output, "checkpoint"
            logger.warning(
                "Checkpoint %s has no story_draft; falling back to payload",
                checkpoint_path,
            )
        except (OSError, ValueError, TypeError) as e:
            # A corrupt or schema-drifted checkpoint must not block the user —
            # payload hydration always works.
            logger.warning(
                "Failed to load checkpoint %s (%s); falling back to payload",
                checkpoint_path,
                e,
            )

    return (
        PipelineOutput(story_draft=payload_to_draft(payload), status="loaded"),
        "payload",
    )


def enhance_tail(
    continuation,
    draft: StoryDraft,
    previous_count: int,
    *,
    num_sim_rounds: int = 3,
    word_count: int = 2000,
    progress_callback=None,
) -> int:
    """Run L2 over ONLY the chapters written by this continuation.

    `StoryContinuation.enhance_chapters` enhances the entire story and writes a
    layer-2 checkpoint from whatever draft it is holding. Neither fits here: the
    reader already has the earlier chapters (rewriting them would silently change
    text they've read, and cost a full-story L2 pass every time they add one
    chapter). So we drive the L2 components directly against a copy of the draft
    holding just the new chapters — full cast, world and synopsis included, so
    the simulator and enhancer keep their context — and merge the enhanced prose
    back into the real draft. The checkpoint is written by the caller.

    Returns the number of chapters actually enhanced; 0 means L2 was skipped and
    the L1 prose stands.
    """

    def _log(msg: str) -> None:
        logger.info(msg)
        if progress_callback:
            progress_callback(msg)

    tail = draft.chapters[previous_count:]
    if not tail:
        return 0

    sub = draft.model_copy(deep=True)
    sub.chapters = [ch.model_copy(deep=True) for ch in tail]

    try:
        analysis = continuation.analyzer.analyze(sub)
        sim_result = continuation.simulator.run_simulation(
            characters=sub.characters,
            relationships=analysis["relationships"],
            genre=sub.genre,
            num_rounds=num_sim_rounds,
            progress_callback=lambda m: _log(f"[L2] {m}"),
        )
        enhanced = continuation.enhancer.enhance_with_feedback(
            draft=sub,
            sim_result=sim_result,
            word_count=word_count,
            progress_callback=lambda m: _log(f"[L2] {m}"),
        )
    except Exception as e:
        # L2 is an enhancement pass, not a gate: the L1 chapters are already
        # written and checkpointed. Losing them because the simulator choked on
        # a malformed LLM payload would be a far worse outcome than shipping
        # un-enhanced prose.
        logger.exception("L2 enhancement failed; keeping L1 prose: %s", e)
        _log(f"[L2] Tăng cường thất bại, giữ nguyên bản L1: {e}")
        return 0
    if enhanced is None or not getattr(enhanced, "chapters", None):
        _log("[L2] Không có chương nào được tăng cường; giữ nguyên bản L1.")
        return 0

    by_number = {ch.chapter_number: ch for ch in enhanced.chapters}
    merged = 0
    for ch in draft.chapters[previous_count:]:
        new_ch = by_number.get(ch.chapter_number)
        if new_ch is None or not getattr(new_ch, "content", ""):
            continue
        ch.content = new_ch.content
        ch.word_count = len(new_ch.content.split())
        if getattr(new_ch, "title", ""):
            ch.title = new_ch.title
        changelog = list(getattr(new_ch, "enhancement_changelog", []) or [])
        if changelog:
            ch.enhancement_changelog = changelog
        merged += 1

    _log(f"[L2] Đã tăng cường {merged}/{len(tail)} chương mới.")
    return merged


def new_chapters_response(draft: StoryDraft, previous_count: int) -> list[dict]:
    """Serialize chapters written past `previous_count` for the client to merge.

    Content is sanitized here rather than by `_sanitize_summary`, which only
    knows the generic `draft`/`enhanced` sections of a run summary.
    """
    from services.text_utils import sanitize_story_html

    return [
        {
            "number": ch.chapter_number,
            "title": ch.title,
            "content": sanitize_story_html(ch.content or ""),
            "summary": ch.summary or "",
            "wordCount": ch.word_count,
        }
        for ch in draft.chapters[previous_count:]
    ]
