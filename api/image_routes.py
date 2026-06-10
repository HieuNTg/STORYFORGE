"""Image generation API routes — wraps services.handlers.handle_generate_images.

Accepts either an active in-memory session id OR a checkpoint filename
(*.json) so library/reader pages can trigger image generation post-hoc.

Image generation is sync + slow (per-chapter HTTP calls), so we run it
on a worker thread and guard against duplicate concurrent runs per
session_id with an in-memory in-flight set.
"""

import asyncio
import json
import logging
import pathlib
import time
import urllib.parse
import uuid
from dataclasses import dataclass, field
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Response, UploadFile, File
from pydantic import BaseModel, Field

from api.export_routes import (
    _PROJECT_ROOT,
    _get_story_data,
    _LibraryStoryPayload,
    _payload_to_story_draft,
)
from middleware.rbac import Permission, require_permission_if_enabled

# Reference-image upload constraints
_REF_MAX_BYTES = 8 * 1024 * 1024  # 8 MB
_REF_ALLOWED_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
}

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/images", tags=["images"])
_READ_STORIES = Depends(require_permission_if_enabled(Permission.READ_STORIES))
_CREATE_STORIES = Depends(require_permission_if_enabled(Permission.CREATE_STORIES))

_in_flight: set[str] = set()
_in_flight_lock = asyncio.Lock()

MAX_CHAPTERS_PER_IMAGE_CALL = 10


# ---------------------------------------------------------------------------
# Phase B — async background comic-generation job store (§2.3)
#
# In-process ``dict`` + ``asyncio.Task`` — correct for a single-process
# open-source app (single Uvicorn worker, locked §7.4). Generated panels are
# already durable on disk under ``OUTPUT_ROOT/<story-slug>/images`` (served via
# ``/media``); the job record holds only transient progress + the URL map.
# Losing it on restart costs a re-poll, not data.
# ---------------------------------------------------------------------------

_JOB_TTL_SECONDS = 30 * 60  # lazy-evict finished jobs after this long
_MAX_JOBS = 100  # hard cap on retained job records (oldest finished evicted first)


@dataclass
class _LibraryJob:
    job_id: str
    title_key: str
    state: str  # queued | running | done | error | cancelled
    provider: str
    panels_per_chapter: int
    target_numbers: list[int]
    chapters: dict[int, dict] = field(default_factory=dict)  # ch -> {title,state,image_urls,error}
    chapter_images: dict[int, list[str]] = field(default_factory=dict)
    skipped_chapters: list[int] = field(default_factory=list)
    count: int = 0
    error: Optional[str] = None
    task: Optional[asyncio.Task] = None
    cancel: bool = False
    created_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None
    in_flight_key: Optional[str] = None  # the _in_flight slot this job reserved


_jobs: dict[str, _LibraryJob] = {}
_jobs_lock = asyncio.Lock()  # guards _jobs + _in_flight together


def _sweep_jobs() -> None:
    """Lazy evictor: drop finished jobs past TTL, then enforce the job cap.

    Called (under ``_jobs_lock``) on every submit and poll — no background
    timer. A job is evictable once it has a ``finished_at`` (terminal state)
    and that timestamp is older than ``_JOB_TTL_SECONDS``. If still over
    ``_MAX_JOBS`` afterwards, the oldest *finished* jobs are dropped first;
    running jobs are never evicted.
    """
    now = time.time()
    expired = [
        jid
        for jid, job in _jobs.items()
        if job.finished_at is not None and (now - job.finished_at) > _JOB_TTL_SECONDS
    ]
    for jid in expired:
        _jobs.pop(jid, None)

    if len(_jobs) <= _MAX_JOBS:
        return
    # Over cap: evict oldest finished jobs first (by finished_at).
    finished = sorted(
        (job for job in _jobs.values() if job.finished_at is not None),
        key=lambda j: j.finished_at or 0.0,
    )
    overflow = len(_jobs) - _MAX_JOBS
    for job in finished[:overflow]:
        _jobs.pop(job.job_id, None)


def _resolve_target_chapters(
    draft, chapter: Optional[int], only_missing: bool
) -> tuple[Optional[list[int]], list[int]]:
    """Resolve which chapters a Library generation call targets (§2.1).

    Lifts the mode-selection logic shared by submit-validation and the worker:

    * ``chapter=N`` → ``([N], [])`` — single chapter.
    * ``only_missing=True`` → chapters with no ``images`` yet; the rest are
      reported as ``skipped_chapters``.
    * full regenerate → ``(None, [])`` meaning "all chapters", capped at
      ``MAX_CHAPTERS_PER_IMAGE_CALL`` (raises 400 over cap).

    Returns ``(target_numbers, skipped_chapters)`` where ``target_numbers`` is
    ``None`` to mean "all chapters" (the handle_generate_images all-chapters
    sentinel), or an explicit list. "has images" is read from the payload draft.
    """
    all_chapters = list(draft.chapters) if draft and draft.chapters else []
    skipped_chapters: list[int] = []
    if chapter is not None:
        return [chapter], skipped_chapters
    if only_missing:
        target_numbers = [
            ch.chapter_number for ch in all_chapters if not getattr(ch, "images", None)
        ]
        skipped_chapters = [
            ch.chapter_number for ch in all_chapters if getattr(ch, "images", None)
        ]
        return target_numbers, skipped_chapters
    # Full regenerate — keep the cost cap for one job.
    if len(all_chapters) > MAX_CHAPTERS_PER_IMAGE_CALL:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Full regenerate is limited to {MAX_CHAPTERS_PER_IMAGE_CALL} "
                f"chapters per call. Use only_missing=true (incremental) or "
                f"pass chapter=N to regenerate a single chapter."
            ),
        )
    return None, skipped_chapters


class GenerateImagesRequest(BaseModel):
    provider: Optional[str] = None
    chapter: Optional[int] = None  # if set, (re)generate only this chapter
    # Incremental comic generation: when True (and ``chapter`` is None), only
    # chapters that have NO images yet are generated; chapters that already
    # have panels are skipped. This is the default Library "Generate comic"
    # behaviour — running it again after "Continue" produces panels for ONLY
    # the new chapters, reusing the same consistency anchors. Set False (with
    # ``chapter`` None) to force a full regenerate of every chapter.
    only_missing: bool = True


class GenerateImagesResponse(BaseModel):
    image_paths: list[str]
    message: str
    count: int
    chapter_images: dict[int, list[str]] = {}
    # Chapters that were skipped because they already had panels (only_missing).
    skipped_chapters: list[int] = []


class LibraryJobAcceptedResponse(BaseModel):
    """202 response for async Library comic generation (Phase B, §2.1).

    Returned immediately when a background job is accepted (or when an
    identical-scope job is already active — ``already_running=True``, 200).
    """

    job_id: str
    state: str  # "queued" | "running" (if reattached)
    title: str  # idempotency key
    total_chapters: int
    target_chapters: list[int]
    already_running: bool = False


class LibraryJobChapterStatus(BaseModel):
    """Per-chapter progress within a Library comic job (Phase B, §2.2)."""

    chapter_number: int
    title: str = ""
    has_images: bool = False
    image_count: int = 0
    image_urls: list[str] = []  # /media/... ready to render
    state: str = "pending"  # pending | running | done | error
    error: Optional[str] = None


class LibraryJobStatusResponse(BaseModel):
    """Polling response for a Library comic job (Phase B, §2.2).

    ``chapter_images`` accretes as chapters finish and shares the exact
    ``dict[int, list[str]]`` shape ``GenerateImagesResponse`` returns, so the
    FE persistence path (``setStoryChapterImages``) is byte-for-byte compatible.
    """

    job_id: str
    state: str  # queued | running | done | error | cancelled
    title: str
    provider: str
    panels_per_chapter: int
    total_chapters: int
    chapters_done: int
    chapters: list[LibraryJobChapterStatus] = []
    chapter_images: dict[int, list[str]] = {}  # accretes; FE persists incrementally
    error: Optional[str] = None
    count: int = 0
    skipped_chapters: list[int] = []


class LibraryGenerateImagesRequest(BaseModel):
    """Payload-based comic generation for localStorage-only Library stories.

    These stories have no backend checkpoint, so they cannot be addressed by the
    ``/{session_id}/generate`` path. Instead the full localStorage Story travels
    in the request body (the SAME shape the export endpoint accepts —
    ``api.export_routes._LibraryStoryPayload``). The engine is reused verbatim;
    only the in-memory orch is built from the payload instead of a checkpoint.

    Mode semantics mirror :class:`GenerateImagesRequest` exactly:

    * ``chapter=N`` — (re)generate ONLY chapter N.
    * ``chapter=None, only_missing=True`` (default) — INCREMENTAL: generate
      panels only for chapters whose ``images`` list is empty in the payload.
      Idempotent, and the consistency-safe default for "Continue" (new chapters
      get panels matching the existing ones via the shared profile store).
    * ``chapter=None, only_missing=False`` — full regenerate (capped at
      ``MAX_CHAPTERS_PER_IMAGE_CALL``).
    """

    story: _LibraryStoryPayload = Field(...)
    provider: Optional[str] = None
    chapter: Optional[int] = None
    only_missing: bool = True


class ChapterComicStatus(BaseModel):
    chapter_number: int
    title: str = ""
    has_images: bool = False
    image_count: int = 0
    image_urls: list[str] = []


class ComicStatusResponse(BaseModel):
    provider: str
    panels_per_chapter: int
    total_chapters: int
    chapters_with_images: int
    chapters: list[ChapterComicStatus] = []


class CharacterProfile(BaseModel):
    name: str
    frozen_prompt: str
    prompt_version: Optional[int] = None
    has_reference_image: bool = False
    reference_url: Optional[str] = None


class CharacterProfilesResponse(BaseModel):
    profiles: list[CharacterProfile]


class CharacterProfileRebuildResponse(BaseModel):
    name: str
    frozen_prompt: str
    prompt_version: Optional[int] = None
    has_reference_image: bool = False
    reference_url: Optional[str] = None
    rebuilt: bool = True


class CharacterReferenceUploadResponse(BaseModel):
    name: str
    frozen_prompt: str
    prompt_version: Optional[int] = None
    has_reference_image: bool = True
    reference_url: str


def _session_basename(session_id: str) -> str:
    """Strip any path/extension to a filesystem-safe slug for grouping uploads."""
    base = pathlib.Path(session_id).stem or session_id
    return "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in base).strip("_") or "session"


def _safe_char_name(name: str) -> str:
    return "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in name).strip("_") or "char"


def _reference_url_for(rel_path: str) -> Optional[str]:
    """Convert a stored reference path into a /media URL if it lives under OUTPUT_ROOT.

    The ``/media`` mount now serves the whole output root (per-story layout), so
    a valid asset path is anything under ``output/`` — the URL is its path
    relative to that root.
    """
    if not rel_path:
        return None
    from services.output_paths import OUTPUT_ROOT
    p = pathlib.Path(rel_path)
    output_root = (_PROJECT_ROOT / OUTPUT_ROOT).resolve()
    try:
        resolved = p.resolve() if p.is_absolute() else (_PROJECT_ROOT / p).resolve()
        rel = resolved.relative_to(output_root)
    except (ValueError, OSError):
        return None
    return "/media/" + rel.as_posix()


def _persist_to_checkpoint(session_id: str, output) -> None:
    """If session_id is a checkpoint filename, rewrite the file with updated chapter.images."""
    if not session_id.endswith(".json"):
        return
    from pipeline.orchestrator_checkpoint import find_checkpoint_path
    safe_name = pathlib.Path(session_id).name
    if ".." in session_id or safe_name != session_id:
        logger.warning(f"Refusing to write outside checkpoint dir: {session_id}")
        return
    resolved = find_checkpoint_path(safe_name)
    if not resolved:
        return
    checkpoint_path = pathlib.Path(resolved)
    try:
        with open(checkpoint_path, "w", encoding="utf-8") as f:
            json.dump(output.model_dump(mode="json"), f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"Failed to persist images into checkpoint {safe_name}: {e}")


def _to_media_url(path: str) -> str:
    """Normalize a stored image path to a ``/media/...`` URL for the client.

    Accepts the three shapes that reach the library pipeline:

    * OUTPUT_ROOT-relative panel paths (``handle_generate_images`` stores
      ``rel_to_output_root(p)`` onto ``chapter.images`` — e.g.
      ``"<story-slug>/images/ch01_panel01.png"``). Since the ``/media`` mount
      serves OUTPUT_ROOT, the URL is just that path with a ``/media/`` prefix.
    * RAW filesystem paths still carrying the ``output/`` segment — the
      *return value* of ``handle_generate_images`` is the cwd-relative
      ``ch_paths`` (e.g. ``"output\\<slug>\\images\\ch01_panel01.png"``).
      The OUTPUT_ROOT prefix is stripped, otherwise the emitted URL would
      double the segment (``/media/output/...`` → 404).
    * Already-illustrated chapters in the payload carry the URLs a PRIOR
      response returned — already ``/media/...``-prefixed (or absolute
      http(s)) — so they are echoed back unchanged.
    """
    if not path:
        return path
    if path.startswith(("/media/", "http://", "https://")):
        return path
    # Absolute filesystem path that happens to live under OUTPUT_ROOT → resolve.
    if pathlib.Path(path).is_absolute():
        return _reference_url_for(path) or path
    from services.output_paths import OUTPUT_ROOT

    norm = path.lstrip("/").replace("\\", "/")
    root = OUTPUT_ROOT.replace("\\", "/").strip("/")
    if norm.startswith(root + "/"):
        norm = norm[len(root) + 1 :]
    return "/media/" + norm


class _PayloadOrchWrapper:
    """Minimal orch_state shim built from a localStorage Story payload.

    Provides the exact attribute surface ``handle_generate_images`` reads:

    * ``.output.story_draft`` — the StoryDraft built from the payload (its
      ``chapters[].images`` carry whatever panels the payload already had, so
      the incremental selector can skip them).
    * ``.output.enhanced_story`` — ``None``; the handler falls back to the draft.
    * ``.session_id`` — deliberately ``None`` so both the ImageGenerator output
      folder AND the CharacterVisualProfileStore resolve to ``slug(title)``
      (no session suffix). This is the SAME slug the checkpoint path lands on
      (``_DBStoryWrapper`` has no ``session_id``), guaranteeing first-generation
      and later "Continue" generations share one per-story folder + one frozen
      profile set → visually consistent chapters.
    """

    session_id = None

    def __init__(self, output):
        self.output = output


def _resolve_provider(provider: Optional[str]) -> str:
    """Resolve the image provider, falling back to config (default ``none``)."""
    if provider:
        return provider
    try:
        from config import ConfigManager
        return getattr(ConfigManager().load().pipeline, "image_provider", "none") or "none"
    except Exception:
        return "none"


def _resolve_panels_per_chapter() -> int:
    """Best-effort read of configured panels-per-chapter (for status reporting)."""
    try:
        from config import ConfigManager
        cfg = ConfigManager().load().pipeline
        return max(1, int(getattr(cfg, "panels_per_chapter", 8)))
    except Exception:
        return 8


async def _run_library_job(job: _LibraryJob, draft, body: "LibraryGenerateImagesRequest") -> None:
    """Background worker that drives one whole-story Library comic job (§2.3/§2.5).

    Per target chapter it calls the SAME ``handle_generate_images`` as the sync
    path (off-loop via ``asyncio.to_thread``), maps results through
    ``_to_media_url``, and accretes them into ``job.chapter_images`` /
    ``job.chapters`` so polls deliver incremental progress. A per-chapter
    exception marks ONLY that chapter ``error`` and the run CONTINUES (partial
    value > all-or-nothing). ``job.cancel`` is checked at the top of each
    iteration for cooperative cancellation at chapter boundaries — the in-flight
    chapter is never force-killed (``to_thread`` workers can't be cancelled).
    """
    from models.schemas import PipelineOutput
    from services.handlers import handle_generate_images

    orch = _PayloadOrchWrapper(PipelineOutput(story_draft=draft, status="complete"))
    by_number = {ch.chapter_number: ch for ch in (draft.chapters or [])}

    # job.target_numbers is ALWAYS the explicit, already-expanded chapter list:
    # submit resolves the "all chapters" sentinel (None) to the full list before
    # the job is created. An empty list therefore legitimately means "nothing to
    # do" (only_missing with every chapter already illustrated) — it must NOT
    # fall back to all chapters, or a no-op "generate missing" would regenerate
    # the whole story.
    iteration = list(job.target_numbers)

    # Seed per-chapter state as pending.
    for n in iteration:
        ch = by_number.get(n)
        job.chapters[n] = {
            "title": (getattr(ch, "title", "") or "") if ch else "",
            "state": "pending",
            "image_urls": [],
            "error": None,
        }

    cancelled = False
    any_done = False
    any_error = False
    try:
        job.state = "running"
        for ch_num in iteration:
            if job.cancel:
                cancelled = True
                break
            entry = job.chapters.setdefault(
                ch_num, {"title": "", "state": "pending", "image_urls": [], "error": None}
            )
            entry["state"] = "running"
            try:
                ch_paths, _msg = await asyncio.to_thread(
                    handle_generate_images, orch, job.provider, None, ch_num
                )
                urls = [_to_media_url(p) for p in (ch_paths or [])]
                job.chapter_images[ch_num] = urls
                entry["image_urls"] = urls
                entry["state"] = "done"
                entry["error"] = None
                job.count += len(urls)
                any_done = True
            except Exception as exc:  # noqa: BLE001 — per-chapter isolation
                logger.warning(
                    "Library comic job %s: chapter %s failed: %s",
                    job.job_id,
                    ch_num,
                    exc,
                )
                entry["state"] = "error"
                entry["error"] = str(exc)
                any_error = True
                continue

        if cancelled:
            job.state = "cancelled"
        elif iteration and not any_done and any_error:
            # Every targeted chapter failed → terminal error.
            job.state = "error"
            job.error = "All targeted chapters failed to generate."
        else:
            job.state = "done"
    except Exception as exc:  # noqa: BLE001 — never strand the job
        logger.exception("Library comic job %s crashed: %s", job.job_id, exc)
        job.state = "error"
        job.error = str(exc)
    finally:
        job.finished_at = time.time()
        if job.in_flight_key is not None:
            async with _jobs_lock:
                _in_flight.discard(job.in_flight_key)


@router.post(
    "/library/generate",
    response_model=LibraryJobAcceptedResponse,
    status_code=202,
    dependencies=[_CREATE_STORIES],
)
async def generate_library_images(
    response: Response, body: LibraryGenerateImagesRequest = Body(...)
):
    """Submit an async background comic-generation job for a Library story (Phase B).

    Mirrors the scope semantics of ``POST /{session_id}/generate`` but for
    localStorage-only stories that have no backend checkpoint: the full Story
    payload travels in the body (same shape as ``POST /api/export/library/{fmt}``).

    Returns ``202`` with a ``job_id`` immediately; generation runs off the request
    thread in a detached ``asyncio.Task`` so it survives client disconnect. Poll
    ``GET /library/jobs/{job_id}`` for per-chapter progress and the accreting
    ``chapter_images`` map (the client owns persistence into localStorage).

    Empty-chapter (400) and over-cap full-regenerate (400) are raised
    SYNCHRONOUSLY here, before the 202. Dedup (§2.4): an identical-scope active
    job returns its existing ``job_id`` with ``already_running=True`` (200); an
    overlapping-but-different scope returns 409.

    Declared BEFORE ``/{session_id}/generate`` so the literal ``library`` path
    segment is matched first (FastAPI resolves routes in declaration order).
    """
    draft = _payload_to_story_draft(body.story)
    if not draft.chapters:
        raise HTTPException(status_code=400, detail="Truyện chưa có chương để tạo truyện tranh")

    # Resolve scope SYNCHRONOUSLY (raises 400 over-cap) before accepting the job.
    target_numbers, skipped_chapters = _resolve_target_chapters(
        draft, body.chapter, body.only_missing
    )

    title_key = draft.title or "untitled"
    in_flight_key = (
        f"library::{title_key}::{body.chapter}"
        if body.chapter is not None
        else f"library::{title_key}"
    )
    whole_key = f"library::{title_key}"
    provider = _resolve_provider(body.provider)

    total_chapters = len(draft.chapters)
    # The concrete chapter list this job will iterate (None == all chapters).
    if target_numbers is not None:
        accepted_targets = list(target_numbers)
    else:
        accepted_targets = [ch.chapter_number for ch in draft.chapters]

    async with _jobs_lock:
        _sweep_jobs()

        # Dedup (§2.4): is there an ACTIVE job (queued|running) for this story?
        for existing in _jobs.values():
            if existing.title_key != title_key:
                continue
            if existing.state not in ("queued", "running"):
                continue
            same_scope = existing.in_flight_key == in_flight_key
            if same_scope:
                # Identical scope already running → reattach. This is NOT a fresh
                # accept, so override the route's 202 default with 200 (§2.4).
                response.status_code = 200
                return LibraryJobAcceptedResponse(
                    job_id=existing.job_id,
                    state=existing.state,
                    title=title_key,
                    total_chapters=total_chapters,
                    target_chapters=list(existing.target_numbers),
                    already_running=True,
                )
            # Overlapping-but-different scope (e.g. single-chapter vs whole-story
            # covering it, or vice versa) → conflict.
            covers = (
                # a whole-story job conflicts with any single-chapter request
                existing.in_flight_key == whole_key
                or in_flight_key == whole_key
                or existing.in_flight_key == in_flight_key
            )
            if covers:
                raise HTTPException(
                    status_code=409,
                    detail="Image generation already in progress for this story",
                )

        # No active job → reserve the in-flight slot and create the job.
        _in_flight.add(in_flight_key)
        job_id = uuid.uuid4().hex
        job = _LibraryJob(
            job_id=job_id,
            title_key=title_key,
            state="queued",
            provider=provider,
            panels_per_chapter=_resolve_panels_per_chapter(),
            target_numbers=accepted_targets,
            skipped_chapters=skipped_chapters,
            in_flight_key=in_flight_key,
        )
        _jobs[job_id] = job
        job.task = asyncio.create_task(_run_library_job(job, draft, body))

    return LibraryJobAcceptedResponse(
        job_id=job_id,
        state="queued",
        title=title_key,
        total_chapters=total_chapters,
        target_chapters=accepted_targets,
        already_running=False,
    )


def _job_to_status(job: _LibraryJob) -> LibraryJobStatusResponse:
    """Project a ``_LibraryJob`` into its public polling shape (§2.2)."""
    chapters_out: list[LibraryJobChapterStatus] = []
    chapters_done = 0
    for ch_num in sorted(job.chapters.keys()):
        entry = job.chapters[ch_num]
        urls = list(entry.get("image_urls") or [])
        state = entry.get("state", "pending")
        if state == "done":
            chapters_done += 1
        chapters_out.append(
            LibraryJobChapterStatus(
                chapter_number=ch_num,
                title=entry.get("title", "") or "",
                has_images=bool(urls),
                image_count=len(urls),
                image_urls=urls,
                state=state,
                error=entry.get("error"),
            )
        )
    return LibraryJobStatusResponse(
        job_id=job.job_id,
        state=job.state,
        title=job.title_key,
        provider=job.provider,
        panels_per_chapter=job.panels_per_chapter,
        total_chapters=len(job.target_numbers),
        chapters_done=chapters_done,
        chapters=chapters_out,
        chapter_images={k: list(v) for k, v in job.chapter_images.items()},
        error=job.error,
        count=job.count,
        skipped_chapters=list(job.skipped_chapters),
    )


@router.get(
    "/library/jobs/{job_id}",
    response_model=LibraryJobStatusResponse,
    dependencies=[_READ_STORIES],
)
async def get_library_job(job_id: str):
    """Poll progress for an async Library comic job (Phase B, §2.2).

    Returns the accreting ``chapter_images`` map + per-chapter state. ``404`` if
    the job is unknown or has been TTL-evicted (the FE then re-derives state from
    localStorage and re-submits via ``only_missing``). Sweeps expired jobs on
    every poll.
    """
    async with _jobs_lock:
        _sweep_jobs()
        job = _jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found or expired")
        return _job_to_status(job)


@router.delete(
    "/library/jobs/{job_id}",
    response_model=LibraryJobStatusResponse,
    dependencies=[_CREATE_STORIES],
)
async def cancel_library_job(job_id: str):
    """Cooperatively cancel a running Library comic job (Phase B, §2.5).

    Sets ``job.cancel=True``; the worker breaks before the NEXT chapter (the
    in-flight chapter runs to completion — ``to_thread`` workers can't be
    force-killed). Partial results are kept. ``404`` if the job is unknown or
    already evicted. Returns the (now ``cancelled``-pending) job status.
    """
    async with _jobs_lock:
        _sweep_jobs()
        job = _jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found or expired")
        if job.state in ("queued", "running"):
            job.cancel = True
        return _job_to_status(job)


@router.post("/{session_id}/generate", response_model=GenerateImagesResponse, dependencies=[_CREATE_STORIES])
async def generate_images(session_id: str, body: GenerateImagesRequest = GenerateImagesRequest()):
    """Generate comic panels for the given session or checkpoint — on-demand.

    `session_id` may be an active orchestrator session UUID or a checkpoint
    filename (e.g. ``story_<id>.json``). Provider falls back to
    ``config.pipeline.image_provider`` (default ``"none"`` short-circuits).

    Three modes:

    * ``chapter=N`` — (re)generate ONLY chapter N (single-chapter regen). The
      in-flight guard is per-(session, chapter) so different chapters can be
      generated in parallel.
    * ``chapter=None, only_missing=True`` (default) — INCREMENTAL: generate
      panels only for chapters that have no images yet, skipping ones that
      already do. Idempotent: re-running after "Continue" added chapters
      produces panels for ONLY the new chapters. This is consistency-safe —
      every chapter is generated through the same
      ``CharacterVisualProfileStore`` frozen prompts + reference images, so new
      chapters match existing ones.
    * ``chapter=None, only_missing=False`` — full regenerate of every chapter.

    The ``only_missing`` and single-chapter modes have no chapter cap; the
    full-regenerate bulk mode is still capped at
    ``MAX_CHAPTERS_PER_IMAGE_CALL`` to bound a single request's cost.
    """
    in_flight_key = f"{session_id}::{body.chapter}" if body.chapter is not None else session_id
    async with _in_flight_lock:
        if in_flight_key in _in_flight:
            raise HTTPException(status_code=409, detail="Image generation already in progress for this story")
        _in_flight.add(in_flight_key)

    try:
        orch = await _get_story_data(session_id)
        if not orch or not orch.output:
            raise HTTPException(status_code=404, detail="Session or checkpoint not found")

        story = orch.output.enhanced_story or orch.output.story_draft
        all_chapters = list(story.chapters) if story and story.chapters else []

        # Resolve which chapters this call targets.
        skipped_chapters: list[int] = []
        if body.chapter is not None:
            target_numbers: Optional[list[int]] = [body.chapter]
        elif body.only_missing:
            # Incremental: only chapters with no panels yet.
            target_numbers = [
                ch.chapter_number for ch in all_chapters if not getattr(ch, "images", None)
            ]
            skipped_chapters = [
                ch.chapter_number for ch in all_chapters if getattr(ch, "images", None)
            ]
        else:
            # Full regenerate — keep the cost cap for one request.
            if len(all_chapters) > MAX_CHAPTERS_PER_IMAGE_CALL:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Full regenerate is limited to {MAX_CHAPTERS_PER_IMAGE_CALL} "
                        f"chapters per call. Use only_missing=true (incremental) or "
                        f"pass chapter=N to regenerate a single chapter."
                    ),
                )
            target_numbers = None  # None == all chapters in handle_generate_images

        provider = body.provider
        if not provider:
            try:
                from config import ConfigManager
                provider = getattr(ConfigManager().load().pipeline, "image_provider", "none") or "none"
            except Exception:
                provider = "none"

        from services.handlers import handle_generate_images

        # handle_generate_images is sync + does N blocking HTTP calls — run off-loop.
        # It regenerates either a single chapter (chapter_number set) or all
        # chapters (None). For incremental mode we loop over only the missing
        # chapter numbers so already-done chapters are never touched.
        paths: list[str] = []
        msg = ""
        if target_numbers is None:
            paths, msg = await asyncio.to_thread(
                handle_generate_images, orch, provider, None, None
            )
        else:
            if not target_numbers:
                msg = "All chapters already have comic panels — nothing to generate."
            for ch_num in target_numbers:
                ch_paths, msg = await asyncio.to_thread(
                    handle_generate_images, orch, provider, None, ch_num
                )
                paths.extend(ch_paths)

        _persist_to_checkpoint(session_id, orch.output)

        story = orch.output.enhanced_story or orch.output.story_draft
        chapter_images: dict[int, list[str]] = {}
        if story and story.chapters:
            for ch in story.chapters:
                if getattr(ch, "images", None):
                    chapter_images[ch.chapter_number] = list(ch.images)

        return GenerateImagesResponse(
            image_paths=paths,
            message=msg,
            count=len(paths),
            chapter_images=chapter_images,
            skipped_chapters=skipped_chapters,
        )
    finally:
        async with _in_flight_lock:
            _in_flight.discard(in_flight_key)


@router.get("/{session_id}/status", response_model=ComicStatusResponse, dependencies=[_READ_STORIES])
async def get_comic_status(session_id: str):
    """Per-chapter comic-panel status for a session or checkpoint.

    Lets the Library render which chapters already have comic panels (and how
    many), which are empty, and how many panels-per-chapter the generator
    targets. ``session_id`` may be an active session UUID or a checkpoint
    filename (e.g. ``story_<id>.json``). Read-only — generates nothing.

    A chapter "has images" iff its ``images`` list is non-empty. After
    "Continue" appends chapters, the new ones report ``has_images=false`` until
    POST /generate (only_missing) fills them in.
    """
    orch = await _get_story_data(session_id)
    if not orch or not orch.output:
        raise HTTPException(status_code=404, detail="Session or checkpoint not found")

    try:
        from config import ConfigManager
        cfg = ConfigManager().load().pipeline
        provider = getattr(cfg, "image_provider", "none") or "none"
        panels_per_chapter = max(1, int(getattr(cfg, "panels_per_chapter", 8)))
    except Exception:
        provider = "none"
        panels_per_chapter = 8

    story = orch.output.enhanced_story or orch.output.story_draft
    chapters_out: list[ChapterComicStatus] = []
    with_images = 0
    if story and story.chapters:
        for ch in story.chapters:
            imgs = list(getattr(ch, "images", None) or [])
            has = bool(imgs)
            if has:
                with_images += 1
            chapters_out.append(
                ChapterComicStatus(
                    chapter_number=ch.chapter_number,
                    title=getattr(ch, "title", "") or "",
                    has_images=has,
                    image_count=len(imgs),
                    image_urls=[_reference_url_for(p) or p for p in imgs],
                )
            )

    return ComicStatusResponse(
        provider=provider,
        panels_per_chapter=panels_per_chapter,
        total_chapters=len(chapters_out),
        chapters_with_images=with_images,
        chapters=chapters_out,
    )



@router.get("/{session_id}/profiles", response_model=CharacterProfilesResponse, dependencies=[_READ_STORIES])
async def get_character_profiles(session_id: str):
    """Return per-character visual profiles for a session or checkpoint.

    Read-only: omits characters with no stored profile rather than auto-building
    (the POST /generate route handles profile creation).
    """
    orch = await _get_story_data(session_id)
    if not orch or not orch.output:
        raise HTTPException(status_code=404, detail="Session or checkpoint not found")

    draft = orch.output.story_draft
    characters = list(draft.characters) if draft and draft.characters else []

    from services.character_visual_profile import CharacterVisualProfileStore
    store = CharacterVisualProfileStore(story_title=getattr(draft, "title", None))

    profiles: list[CharacterProfile] = []
    for char in characters:
        name = getattr(char, "name", "") or ""
        if not name:
            continue
        raw = store.load_profile(name)
        if not raw:
            continue
        ref = raw.get("reference_image") or ""
        has_ref = bool(ref) and pathlib.Path(ref).exists()
        profiles.append(
            CharacterProfile(
                name=name,
                frozen_prompt=raw.get("frozen_prompt") or raw.get("description") or "",
                prompt_version=raw.get("prompt_version"),
                has_reference_image=has_ref,
                reference_url=_reference_url_for(ref) if has_ref else None,
            )
        )

    return CharacterProfilesResponse(profiles=profiles)


@router.post(
    "/{session_id}/profiles/{character_name}/rebuild",
    response_model=CharacterProfileRebuildResponse,
    dependencies=[_CREATE_STORIES],
)
async def rebuild_character_profile(session_id: str, character_name: str):
    """Re-extract attributes + frozen prompt for a single character.

    The on-disk store overwrites in place via ``save_enhanced_profile`` (prompt_version
    auto-bumps when the frozen prompt actually changes), so no explicit invalidate
    primitive is needed. The in-flight key is per-(session, character) so different
    characters can rebuild concurrently.
    """
    decoded_name = urllib.parse.unquote(character_name)
    in_flight_key = f"{session_id}::profile::{decoded_name}"
    async with _in_flight_lock:
        if in_flight_key in _in_flight:
            raise HTTPException(status_code=409, detail="Profile rebuild already in progress")
        _in_flight.add(in_flight_key)

    try:
        orch = await _get_story_data(session_id)
        if not orch or not orch.output:
            raise HTTPException(status_code=404, detail="Session or checkpoint not found")

        draft = orch.output.story_draft
        characters = list(draft.characters) if draft and draft.characters else []
        target = next(
            (c for c in characters
             if (getattr(c, "name", "") or "").lower() == decoded_name.lower()),
            None,
        )
        if target is None:
            raise HTTPException(status_code=404, detail=f"Character '{decoded_name}' not found")

        from services.character_visual_extractor import CharacterVisualExtractor
        from services.character_visual_profile import CharacterVisualProfileStore

        extractor = CharacterVisualExtractor()
        store = CharacterVisualProfileStore(story_title=getattr(draft, "title", None))

        # extract_and_generate is sync + LLM-bound — run off-loop
        attributes, frozen_prompt = await asyncio.to_thread(
            extractor.extract_and_generate, target
        )
        desc = store.build_visual_description(target)
        # save_enhanced_profile overwrites the existing JSON and bumps prompt_version
        # if frozen_prompt actually changed.
        store.save_enhanced_profile(target.name, desc, attributes, frozen_prompt, "")

        _persist_to_checkpoint(session_id, orch.output)

        raw = store.load_profile(target.name) or {}
        ref = raw.get("reference_image") or ""
        has_ref = bool(ref) and pathlib.Path(ref).exists()
        return CharacterProfileRebuildResponse(
            name=target.name,
            frozen_prompt=raw.get("frozen_prompt") or frozen_prompt,
            prompt_version=raw.get("prompt_version"),
            has_reference_image=has_ref,
            reference_url=_reference_url_for(ref) if has_ref else None,
            rebuilt=True,
        )
    finally:
        async with _in_flight_lock:
            _in_flight.discard(in_flight_key)


@router.post(
    "/{session_id}/profiles/{character_name}/reference",
    response_model=CharacterReferenceUploadResponse,
    dependencies=[_CREATE_STORIES],
)
async def upload_character_reference(
    session_id: str,
    character_name: str,
    file: UploadFile = File(...),
):
    """Upload a reference image for a character.

    Accepts PNG/JPEG/WEBP up to 8 MB. The file is stored under the per-story
    images dir ``output/<story-slug>/images/references/<session>/<character>.<ext>``
    so it is reachable via the ``/media`` static mount. The profile's ``reference_image``
    field is updated in place — no LLM extraction runs (use the rebuild route
    for that).
    """
    decoded_name = urllib.parse.unquote(character_name)
    in_flight_key = f"{session_id}::ref::{decoded_name}"
    async with _in_flight_lock:
        if in_flight_key in _in_flight:
            raise HTTPException(status_code=409, detail="Reference upload already in progress")
        _in_flight.add(in_flight_key)

    try:
        content_type = (file.content_type or "").lower()
        if content_type not in _REF_ALLOWED_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported content type: {content_type or 'unknown'}. Use PNG, JPEG, or WEBP.",
            )

        # Read with a hard cap — UploadFile streams from a SpooledTemporaryFile,
        # so we don't trust Content-Length alone.
        data = await file.read(_REF_MAX_BYTES + 1)
        if len(data) > _REF_MAX_BYTES:
            raise HTTPException(status_code=413, detail="File too large (max 8 MB)")
        if not data:
            raise HTTPException(status_code=400, detail="Empty file")

        orch = await _get_story_data(session_id)
        if not orch or not orch.output:
            raise HTTPException(status_code=404, detail="Session or checkpoint not found")

        draft = orch.output.story_draft
        characters = list(draft.characters) if draft and draft.characters else []
        target = next(
            (c for c in characters
             if (getattr(c, "name", "") or "").lower() == decoded_name.lower()),
            None,
        )
        if target is None:
            raise HTTPException(status_code=404, detail=f"Character '{decoded_name}' not found")

        # Resolve storage path with traversal guard. References live under the
        # per-story images dir: output/<story-slug>/images/references/<session>/
        from services.output_paths import images_dir as _images_dir
        ext = _REF_ALLOWED_TYPES[content_type]
        refs_root = (
            _PROJECT_ROOT / _images_dir(getattr(draft, "title", None)) / "references"
        ).resolve()
        session_dir = (refs_root / _session_basename(session_id)).resolve()
        try:
            session_dir.relative_to(refs_root)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid session path")
        session_dir.mkdir(parents=True, exist_ok=True)
        target_path = (session_dir / f"{_safe_char_name(target.name)}{ext}").resolve()
        try:
            target_path.relative_to(refs_root)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid character path")

        # Replace any older reference for this character that used a different ext.
        for old in session_dir.glob(f"{_safe_char_name(target.name)}.*"):
            if old != target_path:
                try:
                    old.unlink()
                except OSError:
                    pass

        target_path.write_bytes(data)

        # Update the profile's reference_image without re-running the LLM extractor.
        # If no profile exists yet, seed a minimal one so the reference is retained.
        from services.character_visual_profile import CharacterVisualProfileStore
        store = CharacterVisualProfileStore(story_title=getattr(draft, "title", None))
        rel_path = target_path.relative_to(_PROJECT_ROOT).as_posix()
        if not store.set_reference_image(target.name, rel_path):
            desc = store.build_visual_description(target)
            store.save_enhanced_profile(target.name, desc, {}, "", "")
            store.set_reference_image(target.name, rel_path)

        _persist_to_checkpoint(session_id, orch.output)

        raw = store.load_profile(target.name) or {}
        return CharacterReferenceUploadResponse(
            name=target.name,
            frozen_prompt=raw.get("frozen_prompt") or raw.get("description") or "",
            prompt_version=raw.get("prompt_version"),
            has_reference_image=True,
            reference_url=_reference_url_for(rel_path) or "",
        )
    finally:
        async with _in_flight_lock:
            _in_flight.discard(in_flight_key)
