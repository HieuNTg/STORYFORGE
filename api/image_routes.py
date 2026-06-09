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
import urllib.parse
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, UploadFile, File
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

    Newly generated panels arrive as OUTPUT_ROOT-relative paths (``handle_generate_images``
    stores ``rel_to_output_root(p)`` onto ``chapter.images`` — e.g.
    ``"<story-slug>/images/ch01_panel01.png"``). Since the ``/media`` mount
    serves OUTPUT_ROOT, the URL is just that path with a ``/media/`` prefix.

    Already-illustrated chapters in the payload carry the URLs a PRIOR response
    returned — already ``/media/...``-prefixed (or absolute http(s)) — so they
    are echoed back unchanged.
    """
    if not path:
        return path
    if path.startswith(("/media/", "http://", "https://")):
        return path
    # Absolute filesystem path that happens to live under OUTPUT_ROOT → resolve.
    if pathlib.Path(path).is_absolute():
        return _reference_url_for(path) or path
    # OUTPUT_ROOT-relative panel path (the common case).
    return "/media/" + path.lstrip("/").replace("\\", "/")


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


@router.post(
    "/library/generate",
    response_model=GenerateImagesResponse,
    dependencies=[_CREATE_STORIES],
)
async def generate_library_images(body: LibraryGenerateImagesRequest = Body(...)):
    """Generate comic panels for a localStorage-only Library story (payload-based).

    Mirrors ``POST /{session_id}/generate`` but for stories that have no backend
    checkpoint: the full Story payload (title + characters + chapters incl. each
    chapter's current ``images``) is sent in the body — the same shape the FE
    already sends to ``POST /api/export/library/{fmt}``.

    The engine (``services.handlers.handle_generate_images``) and the
    consistency anchors (``CharacterVisualProfileStore`` keyed by story title,
    auto-built via ``CharacterVisualExtractor``) are reused verbatim. Nothing is
    persisted server-side except the generated panels under
    ``output/<story-slug>/images`` (served via ``/media``). The client persists
    the returned ``chapter_images`` map back into its localStorage Story.

    Declared BEFORE ``/{session_id}/generate`` so the literal ``library`` path
    segment is matched first (FastAPI resolves routes in declaration order).
    """
    from models.schemas import PipelineOutput

    draft = _payload_to_story_draft(body.story)
    if not draft.chapters:
        raise HTTPException(status_code=400, detail="Truyện chưa có chương để tạo truyện tranh")

    # Title is the consistency key (same as the checkpoint path). Guard against
    # duplicate concurrent generation for the SAME story+chapter scope, mirroring
    # the 409 behaviour of the session endpoint.
    title_key = draft.title or "untitled"
    in_flight_key = (
        f"library::{title_key}::{body.chapter}"
        if body.chapter is not None
        else f"library::{title_key}"
    )
    async with _in_flight_lock:
        if in_flight_key in _in_flight:
            raise HTTPException(status_code=409, detail="Image generation already in progress for this story")
        _in_flight.add(in_flight_key)

    try:
        orch = _PayloadOrchWrapper(PipelineOutput(story_draft=draft, status="complete"))
        all_chapters = list(draft.chapters)

        # Resolve which chapters this call targets — identical logic to the
        # session endpoint, but "has images" is read from the payload.
        skipped_chapters: list[int] = []
        if body.chapter is not None:
            target_numbers: Optional[list[int]] = [body.chapter]
        elif body.only_missing:
            target_numbers = [
                ch.chapter_number for ch in all_chapters if not getattr(ch, "images", None)
            ]
            skipped_chapters = [
                ch.chapter_number for ch in all_chapters if getattr(ch, "images", None)
            ]
        else:
            if len(all_chapters) > MAX_CHAPTERS_PER_IMAGE_CALL:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Full regenerate is limited to {MAX_CHAPTERS_PER_IMAGE_CALL} "
                        f"chapters per call. Use only_missing=true (incremental) or "
                        f"pass chapter=N to regenerate a single chapter."
                    ),
                )
            target_numbers = None

        provider = body.provider
        if not provider:
            try:
                from config import ConfigManager
                provider = getattr(ConfigManager().load().pipeline, "image_provider", "none") or "none"
            except Exception:
                provider = "none"

        from services.handlers import handle_generate_images

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

        # No checkpoint to persist into — the client owns persistence. Return the
        # full per-chapter image map as /media URLs so the FE can write them onto
        # each Chapter.images and re-render.
        story = orch.output.enhanced_story or orch.output.story_draft
        chapter_images: dict[int, list[str]] = {}
        if story and story.chapters:
            for ch in story.chapters:
                imgs = getattr(ch, "images", None)
                if imgs:
                    chapter_images[ch.chapter_number] = [
                        _to_media_url(p) for p in imgs
                    ]

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
