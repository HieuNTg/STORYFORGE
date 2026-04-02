"""Export API routes — PDF, EPUB, TTS, ZIP, share."""

import logging
import os
import pathlib
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse

from api.pipeline_routes import _orchestrators

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/export", tags=["export"])

# Directories that export files may legally reside in
_PROJECT_ROOT = pathlib.Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))).resolve()
_ALLOWED_EXPORT_DIRS = (
    _PROJECT_ROOT / "output",
    _PROJECT_ROOT / "data",
)


def _safe_file_response(path: "str | pathlib.Path", filename: str) -> FileResponse:
    """Return FileResponse only if path is inside an allowed export directory.

    Raises HTTPException 400 on path traversal attempts.
    Raises HTTPException 404 if file does not exist.
    """
    resolved = pathlib.Path(path).resolve()
    in_allowed = any(
        str(resolved).startswith(str(allowed))
        for allowed in _ALLOWED_EXPORT_DIRS
    )
    if not in_allowed:
        logger.warning(f"Path traversal attempt blocked: {resolved}")
        raise HTTPException(status_code=400, detail="Invalid export path")
    if not resolved.exists():
        raise HTTPException(status_code=404, detail="Export file not found")
    # Sanitize the download filename — strip any directory components
    safe_name = pathlib.Path(filename).name or "export"
    return FileResponse(str(resolved), filename=safe_name)


def _get_orch(session_id: str):
    """Retrieve orchestrator by session ID."""
    orch = _orchestrators.get(session_id)
    if not orch or not orch.output:
        return None
    return orch


@router.post("/files/{session_id}")
def export_files(session_id: str, formats: list[str] = ["TXT", "Markdown", "JSON"]):
    """Export story files in requested formats."""
    orch = _get_orch(session_id)
    if not orch:
        return JSONResponse({"error": "Chưa có truyện"}, status_code=404)
    try:
        from ui.handlers import handle_export_files
        files = handle_export_files(orch, formats)
        if not files:
            return {"files": []}
        # Validate each returned path stays within allowed dirs
        safe_files = []
        for f in files:
            resolved = pathlib.Path(f).resolve()
            if any(str(resolved).startswith(str(d)) for d in _ALLOWED_EXPORT_DIRS):
                safe_files.append(str(resolved))
            else:
                logger.warning(f"Skipping disallowed export path: {resolved}")
        return {"files": safe_files}
    except Exception as e:
        logger.error(f"Export error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/zip/{session_id}")
def export_zip(session_id: str):
    """Export all files as ZIP."""
    orch = _get_orch(session_id)
    if not orch:
        return JSONResponse({"error": "Chưa có truyện"}, status_code=404)
    try:
        from services.i18n import I18n
        _t = I18n().t
        from ui.handlers import handle_export_zip
        files = handle_export_zip(orch, ["TXT", "Markdown", "JSON", "HTML"], _t)
        if files and len(files) > 0:
            return _safe_file_response(files[0], "storyforge_export.zip")
        return JSONResponse({"error": "Không có file"}, status_code=500)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"ZIP export error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/pdf/{session_id}")
def export_pdf(session_id: str):
    """Export story as PDF."""
    orch = _get_orch(session_id)
    if not orch:
        return JSONResponse({"error": "Chưa có truyện"}, status_code=404)
    try:
        from services.i18n import I18n
        from ui.handlers import handle_export_pdf
        files, stats = handle_export_pdf(orch, I18n().t)
        if files:
            return _safe_file_response(files[0], "storyforge.pdf")
        return JSONResponse({"error": "Xuất PDF thất bại"}, status_code=500)
    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/epub/{session_id}")
def export_epub(session_id: str):
    """Export story as EPUB."""
    orch = _get_orch(session_id)
    if not orch:
        return JSONResponse({"error": "Chưa có truyện"}, status_code=404)
    try:
        from services.i18n import I18n
        from ui.handlers import handle_export_epub
        files, stats = handle_export_epub(orch, I18n().t)
        if files:
            return _safe_file_response(files[0], "storyforge.epub")
        return JSONResponse({"error": "Xuất EPUB thất bại"}, status_code=500)
    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
