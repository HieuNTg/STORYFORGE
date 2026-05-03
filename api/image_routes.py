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

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel

from api.export_routes import _PROJECT_ROOT, _get_story_data

# Reference-image upload constraints
_REF_MAX_BYTES = 8 * 1024 * 1024  # 8 MB
_REF_ALLOWED_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
}

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/images", tags=["images"])

_in_flight: set[str] = set()
_in_flight_lock = asyncio.Lock()


class GenerateImagesRequest(BaseModel):
    provider: Optional[str] = None
    chapter: Optional[int] = None  # if set, regenerate only this chapter


class GenerateImagesResponse(BaseModel):
    image_paths: list[str]
    message: str
    count: int
    chapter_images: dict[int, list[str]] = {}


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
    """Convert a stored reference path into a /media URL if it lives under output/images."""
    if not rel_path:
        return None
    p = pathlib.Path(rel_path)
    images_root = (_PROJECT_ROOT / "output" / "images").resolve()
    try:
        resolved = p.resolve() if p.is_absolute() else (_PROJECT_ROOT / p).resolve()
        rel = resolved.relative_to(images_root)
    except (ValueError, OSError):
        return None
    return "/media/" + rel.as_posix()


def _persist_to_checkpoint(session_id: str, output) -> None:
    """If session_id is a checkpoint filename, rewrite the file with updated chapter.images."""
    if not session_id.endswith(".json"):
        return
    checkpoint_dir = (_PROJECT_ROOT / "output" / "checkpoints").resolve()
    safe_name = pathlib.Path(session_id).name
    checkpoint_path = (checkpoint_dir / safe_name).resolve()
    try:
        checkpoint_path.relative_to(checkpoint_dir)
    except ValueError:
        logger.warning(f"Refusing to write outside checkpoint dir: {session_id}")
        return
    if not checkpoint_path.exists():
        return
    try:
        with open(checkpoint_path, "w", encoding="utf-8") as f:
            json.dump(output.model_dump(mode="json"), f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"Failed to persist images into checkpoint {safe_name}: {e}")


@router.post("/{session_id}/generate", response_model=GenerateImagesResponse)
async def generate_images(session_id: str, body: GenerateImagesRequest = GenerateImagesRequest()):
    """Generate one image per chapter for the given session or checkpoint.

    `session_id` may be an active orchestrator session UUID or a checkpoint
    filename (e.g. ``story_<id>.json``). Provider falls back to
    ``config.pipeline.image_provider`` (default ``"none"`` short-circuits).
    Pass ``chapter`` to regenerate a single chapter only — the in-flight guard
    is per-(session, chapter) so different chapters can be generated in parallel.
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

        provider = body.provider
        if not provider:
            try:
                from config import ConfigManager
                provider = getattr(ConfigManager().load().pipeline, "image_provider", "none") or "none"
            except Exception:
                provider = "none"

        from services.handlers import handle_generate_images
        # handle_generate_images is sync + does N blocking HTTP calls — run off-loop
        paths, msg = await asyncio.to_thread(
            handle_generate_images, orch, provider, None, body.chapter
        )

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
        )
    finally:
        async with _in_flight_lock:
            _in_flight.discard(in_flight_key)


@router.get("/{session_id}/profiles", response_model=CharacterProfilesResponse)
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
    store = CharacterVisualProfileStore()

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
        store = CharacterVisualProfileStore()

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
)
async def upload_character_reference(
    session_id: str,
    character_name: str,
    file: UploadFile = File(...),
):
    """Upload a reference image for a character.

    Accepts PNG/JPEG/WEBP up to 8 MB. The file is stored under
    ``output/images/references/<session>/<character>.<ext>`` so it is reachable
    via the ``/media`` static mount. The on-disk profile's ``reference_image``
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

        # Resolve storage path with traversal guard
        ext = _REF_ALLOWED_TYPES[content_type]
        refs_root = (_PROJECT_ROOT / "output" / "images" / "references").resolve()
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
        store = CharacterVisualProfileStore()
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
