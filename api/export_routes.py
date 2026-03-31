"""Export API routes — PDF, EPUB, TTS, ZIP, share."""

import logging
from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse

from api.pipeline_routes import _orchestrators

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/export", tags=["export"])


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
        return {"files": [str(f) for f in files] if files else []}
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
            return FileResponse(str(files[0]), filename="storyforge_export.zip")
        return JSONResponse({"error": "Không có file"}, status_code=500)
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
            return FileResponse(str(files[0]), filename="storyforge.pdf")
        return JSONResponse({"error": "Xuất PDF thất bại"}, status_code=500)
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
            return FileResponse(str(files[0]), filename="storyforge.epub")
        return JSONResponse({"error": "Xuất EPUB thất bại"}, status_code=500)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
