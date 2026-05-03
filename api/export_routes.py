"""Export API routes — PDF, EPUB, TTS, ZIP, share."""

import logging
import os
import pathlib
from typing import Optional, TYPE_CHECKING
from fastapi import APIRouter, HTTPException

if TYPE_CHECKING:
    from models.schemas import PipelineOutput
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


def _load_story_from_checkpoint(filename: str) -> Optional["_DBStoryWrapper"]:
    """Load story from checkpoint file and wrap it for export handlers."""
    from models.schemas import PipelineOutput
    import json

    checkpoint_dir = (_PROJECT_ROOT / "output" / "checkpoints").resolve()
    safe_name = pathlib.Path(filename).name
    checkpoint_path = (checkpoint_dir / safe_name).resolve()

    try:
        checkpoint_path.relative_to(checkpoint_dir)
    except ValueError:
        logger.warning(f"Path traversal attempt in checkpoint load: {filename}")
        return None

    if not checkpoint_path.exists():
        logger.warning(f"Checkpoint file not found: {checkpoint_path}")
        return None

    try:
        with open(checkpoint_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        output = PipelineOutput.model_validate(data)
        return _DBStoryWrapper(output)
    except Exception as e:
        logger.warning(f"Failed to load checkpoint {filename}: {e}")
        return None


async def _load_story_from_db(story_id: str) -> Optional["_DBStoryWrapper"]:
    """Load story from database by ID and wrap it for export handlers."""
    try:
        from services.infra.database import get_session
        from models.db_models import Story
        from models.schemas import Chapter, StoryDraft, PipelineOutput
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        async with get_session() as session:
            if session is None:
                return None
            result = await session.execute(
                select(Story)
                .options(selectinload(Story.chapters))
                .where(Story.id == story_id)
            )
            story = result.scalar_one_or_none()
            if not story:
                return None

            chapters = [
                Chapter(
                    chapter_number=ch.chapter_number,
                    title=ch.title or f"Chương {ch.chapter_number}",
                    content=ch.content or "",
                    word_count=ch.word_count or len((ch.content or "").split()),
                )
                for ch in sorted(story.chapters, key=lambda c: c.chapter_number)
            ]

            story_draft = StoryDraft(
                title=story.title,
                genre=story.genre or "",
                synopsis=story.synopsis or "",
                chapters=chapters,
            )

            output = PipelineOutput(story_draft=story_draft, status="complete")
            return _DBStoryWrapper(output)
    except Exception as e:
        logger.warning(f"Failed to load story from DB: {e}")
        return None


class _DBStoryWrapper:
    """Minimal wrapper to provide orch_state-like interface for export handlers."""

    def __init__(self, output: "PipelineOutput"):
        self.output = output

    def export_output(self, formats: list[str]) -> Optional[list[str]]:
        from pipeline.orchestrator_export import PipelineExporter
        exporter = PipelineExporter(self.output)
        return exporter.export_output(formats=formats) or None

    def export_zip(self, formats: list[str]) -> Optional[str]:
        from pipeline.orchestrator_export import PipelineExporter
        exporter = PipelineExporter(self.output)
        return exporter.export_zip(formats=formats) or None


async def _get_story_data(session_id: str):
    """Get story data from memory, checkpoint file, or database."""
    orch = _get_orch(session_id)
    if orch:
        return orch
    if session_id.endswith(".json"):
        ckpt = _load_story_from_checkpoint(session_id)
        if ckpt:
            return ckpt
    return await _load_story_from_db(session_id)


@router.post("/files/{session_id}")
async def export_files(session_id: str, formats: list[str] = ["TXT", "Markdown", "JSON"]):
    """Export story files in requested formats."""
    orch = await _get_story_data(session_id)
    if not orch:
        return JSONResponse({"error": "Chưa có truyện"}, status_code=404)
    from services.handlers import handle_export_files
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


@router.post("/zip/{session_id}")
async def export_zip(session_id: str):
    """Export all files as ZIP."""
    orch = await _get_story_data(session_id)
    if not orch:
        return JSONResponse({"error": "Chưa có truyện"}, status_code=404)
    from services.i18n import I18n
    _t = I18n().t
    from services.handlers import handle_export_zip
    files = handle_export_zip(orch, ["TXT", "Markdown", "JSON", "HTML"], _t)
    if files and len(files) > 0:
        return _safe_file_response(files[0], "storyforge_export.zip")
    return JSONResponse({"error": "Không có file"}, status_code=500)


@router.post("/pdf/{session_id}")
async def export_pdf(session_id: str):
    """Export story as PDF."""
    orch = await _get_story_data(session_id)
    if not orch:
        return JSONResponse({"error": "Chưa có truyện"}, status_code=404)
    from services.i18n import I18n
    from services.handlers import handle_export_pdf
    files, stats = handle_export_pdf(orch, I18n().t)
    if files:
        return _safe_file_response(files[0], "storyforge.pdf")
    return JSONResponse({"error": "Xuất PDF thất bại"}, status_code=500)


@router.post("/epub/{session_id}")
async def export_epub(session_id: str):
    """Export story as EPUB."""
    orch = await _get_story_data(session_id)
    if not orch:
        return JSONResponse({"error": "Chưa có truyện"}, status_code=404)
    from services.i18n import I18n
    from services.handlers import handle_export_epub
    files, stats = handle_export_epub(orch, I18n().t)
    if files:
        return _safe_file_response(files[0], "storyforge.epub")
    return JSONResponse({"error": "Xuất EPUB thất bại"}, status_code=500)
