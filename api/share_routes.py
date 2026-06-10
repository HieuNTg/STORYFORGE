"""Share API routes — create, view, list, and delete public story shares."""

import logging
import pathlib
import re

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from middleware.rbac import Permission, require_permission_if_enabled
from services.share_manager import ShareManager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/share", tags=["share"])
_CREATE_STORIES = Depends(require_permission_if_enabled(Permission.CREATE_STORIES))
_DELETE_ANY_STORIES = Depends(require_permission_if_enabled(Permission.DELETE_ANY_STORIES))

_share_manager = ShareManager()

# Shares are always stored under data/shares — resolve once for path checks
_PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
_SHARES_DIR = (_PROJECT_ROOT / "data" / "shares").resolve()

# share_id is a 12-char hex/UUID fragment — validate strictly to block traversal
_SHARE_ID_RE = re.compile(r"^[a-f0-9\-]{8,36}$")


def _validate_share_id(share_id: str) -> None:
    """Raise 400 if share_id looks malicious."""
    if not _SHARE_ID_RE.match(share_id):
        raise HTTPException(status_code=400, detail="Invalid share ID")


class CreateShareRequest(BaseModel):
    """Request body for creating a share from an active pipeline session."""

    session_id: str
    is_public: bool = False
    expires_days: int = 30


class LibraryCharacterPayload(BaseModel):
    """Character card data from a localStorage library story."""

    name: str = Field(max_length=200)
    role: str = Field(default="", max_length=200)
    personality: str = Field(default="", max_length=2000)
    motivation: str = Field(default="", max_length=2000)


class LibraryChapterPayload(BaseModel):
    """Chapter data from a localStorage library story (incl. comic pages)."""

    title: str = Field(max_length=500)
    content: str = Field(default="", max_length=400_000)
    summary: str = Field(default="", max_length=10_000)
    images: list[str] = Field(default_factory=list, max_length=200)


class LibraryShareRequest(BaseModel):
    """Share a library story (localStorage-only, no server session) to the
    public gallery. The frontend serializes the story and POSTs it here."""

    title: str = Field(min_length=1, max_length=500)
    genre: str = Field(default="", max_length=200)
    synopsis: str = Field(default="", max_length=10_000)
    chapters: list[LibraryChapterPayload] = Field(min_length=1, max_length=500)
    characters: list[LibraryCharacterPayload] = Field(default_factory=list, max_length=50)
    is_public: bool = True
    expires_days: int = Field(default=30, ge=1, le=365)
    replace_share_id: str = Field(default="", max_length=36)


@router.post("/create", dependencies=[_CREATE_STORIES])
def create_share(req: CreateShareRequest):
    """Create a share from an active pipeline session's output."""
    # Import here to avoid circular imports at module load time
    from api.pipeline_routes import _orchestrators

    orch = _orchestrators.get(req.session_id)
    if not orch or not orch.output:
        return JSONResponse({"error": "No story output found for session"}, status_code=404)

    story = orch.output
    characters = getattr(orch, "characters", None)

    try:
        share = _share_manager.create_share(
            story,
            characters=characters,
            expires_days=req.expires_days,
            is_public=req.is_public,
        )
    except Exception:
        logger.exception("Failed to create share")
        return JSONResponse({"error": "Share creation failed"}, status_code=500)

    return {
        "share_id": share.share_id,
        "story_title": share.story_title,
        "created_at": share.created_at,
        "expires_at": share.expires_at,
        "is_public": share.is_public,
    }


@router.post("/create-from-library", dependencies=[_CREATE_STORIES])
def create_share_from_library(req: LibraryShareRequest):
    """Create a public share from a serialized library story.

    Library stories live only in the browser's localStorage, so unlike
    /create there is no server session to read from — the story payload
    (chapters, prose, comic page `/media/...` URLs) arrives in the request.
    """
    from models.schemas import Character, Chapter, StoryDraft

    chapters = []
    for i, ch in enumerate(req.chapters, start=1):
        # Only same-origin /media/ URLs survive — anything else is dropped so
        # shared HTML can never embed external or traversal image sources.
        safe_images = [
            u.strip() for u in ch.images
            if isinstance(u, str) and u.strip().startswith("/media/") and ".." not in u
        ]
        chapters.append(
            Chapter(
                chapter_number=i,
                title=ch.title,
                content=ch.content,
                summary=ch.summary,
                images=safe_images,
            )
        )

    story = StoryDraft(
        title=req.title,
        genre=req.genre or "Khác",
        synopsis=req.synopsis,
        characters=[
            Character(
                name=c.name,
                role=c.role or "phụ",
                personality=c.personality or "Chưa xác định",
                motivation=c.motivation,
            )
            for c in req.characters
        ],
        chapters=chapters,
    )

    # Re-publish: one gallery entry per library story — drop the old share
    # before creating the replacement (id is validated like the GET route).
    if req.replace_share_id and _SHARE_ID_RE.match(req.replace_share_id):
        _share_manager.delete_share(req.replace_share_id)

    try:
        share = _share_manager.create_share(
            story,
            characters=story.characters or None,
            expires_days=req.expires_days,
            is_public=req.is_public,
        )
    except Exception:
        logger.exception("Failed to create library share")
        return JSONResponse({"error": "Share creation failed"}, status_code=500)

    return {
        "share_id": share.share_id,
        "story_title": share.story_title,
        "created_at": share.created_at,
        "expires_at": share.expires_at,
        "is_public": share.is_public,
        "cover_url": share.cover_url,
        "url": f"/api/share/{share.share_id}",
    }


@router.get("/gallery")
def gallery(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List active public shares with pagination (no auth required)."""
    all_shares = _share_manager.list_public_shares()
    total = len(all_shares)
    page = all_shares[offset: offset + limit]
    return {
        "items": [
            {
                "share_id": s.share_id,
                "story_title": s.story_title,
                "created_at": s.created_at,
                "expires_at": s.expires_at,
                "genre": s.genre,
                "cover_url": s.cover_url,
            }
            for s in page
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/{share_id}")
def get_share(share_id: str):
    """Serve the HTML for a share."""
    _validate_share_id(share_id)

    html_path = _share_manager.get_share(share_id)
    if not html_path:
        raise HTTPException(status_code=404, detail="Share not found or expired")

    resolved = pathlib.Path(html_path).resolve()
    try:
        resolved.relative_to(_SHARES_DIR)
    except ValueError:
        logger.warning("Path traversal blocked for share %s -> %s", share_id, resolved)
        raise HTTPException(status_code=400, detail="Invalid share path")

    if not resolved.exists():
        raise HTTPException(status_code=404, detail="Share file not found")

    return FileResponse(str(resolved), media_type="text/html")


@router.delete("/{share_id}", dependencies=[_DELETE_ANY_STORIES])
def delete_share(share_id: str):
    """Delete a share and its HTML file."""
    _validate_share_id(share_id)

    deleted = _share_manager.delete_share(share_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Share not found")
    return {"deleted": share_id}
