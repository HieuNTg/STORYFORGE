"""Share API routes — create, view, list, and delete public story shares."""

import logging
import pathlib
import re

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from services.share_manager import ShareManager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/share", tags=["share"])

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


@router.post("/create")
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


@router.delete("/{share_id}")
def delete_share(share_id: str):
    """Delete a share and its HTML file."""
    _validate_share_id(share_id)

    deleted = _share_manager.delete_share(share_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Share not found")
    return {"deleted": share_id}
