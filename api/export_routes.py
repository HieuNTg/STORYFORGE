"""Export API routes — PDF, EPUB, TTS, ZIP, share."""

import logging
import os
import pathlib
import re
import tempfile
import uuid
from typing import Any, Optional, TYPE_CHECKING
from fastapi import APIRouter, Body, Depends, HTTPException

if TYPE_CHECKING:
    from models.schemas import PipelineOutput
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from api.pipeline_routes import _orchestrators
from middleware.rbac import Permission, require_permission_if_enabled

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/export", tags=["export"])
_READ_STORIES = Depends(require_permission_if_enabled(Permission.READ_STORIES))

# Directories that export files may legally reside in
_PROJECT_ROOT = pathlib.Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))).resolve()
_ALLOWED_EXPORT_DIRS = (
    _PROJECT_ROOT / "output",
    _PROJECT_ROOT / "data",
)


def _is_relative_to(child: pathlib.Path, parent: pathlib.Path) -> bool:
    """Return True if child is inside parent (safe replacement for startswith)."""
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def _safe_file_response(path: "str | pathlib.Path", filename: str) -> FileResponse:
    """Return FileResponse only if path is inside an allowed export directory.

    Raises HTTPException 400 on path traversal attempts.
    Raises HTTPException 404 if file does not exist.
    """
    resolved = pathlib.Path(path).resolve()
    in_allowed = any(
        _is_relative_to(resolved, allowed)
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

    from pipeline.orchestrator_checkpoint import find_checkpoint_path
    safe_name = pathlib.Path(filename).name
    if ".." in filename or safe_name != filename:
        logger.warning(f"Path traversal attempt in checkpoint load: {filename}")
        return None
    resolved = find_checkpoint_path(safe_name)
    if not resolved:
        logger.warning(f"Checkpoint file not found: {filename}")
        return None
    checkpoint_path = pathlib.Path(resolved)

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


@router.post("/files/{session_id}", dependencies=[_READ_STORIES])
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
        if any(_is_relative_to(resolved, d) for d in _ALLOWED_EXPORT_DIRS):
            safe_files.append(str(resolved))
        else:
            logger.warning(f"Skipping disallowed export path: {resolved}")
    return {"files": safe_files}


@router.post("/zip/{session_id}", dependencies=[_READ_STORIES])
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


@router.post("/pdf/{session_id}", dependencies=[_READ_STORIES])
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


@router.post("/epub/{session_id}", dependencies=[_READ_STORIES])
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


# ---------------------------------------------------------------------------
# Library export — accepts a Story payload from the frontend library store
# (localStorage), converts it to a StoryDraft, and serves the rendered file.
# ---------------------------------------------------------------------------

# Library exports now land in the per-story exports folder
# (``output/<story-slug>/exports``) instead of a shared ``output/library``.
# The served-file guard validates against the whole output root so any
# per-story exports dir is acceptable while still blocking path traversal.
from services.output_paths import OUTPUT_ROOT as _OUTPUT_ROOT, exports_dir as _exports_dir
_OUTPUT_ROOT_ABS = (_PROJECT_ROOT / _OUTPUT_ROOT).resolve()
_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9_\-]+")


class _LibraryChapterPayload(BaseModel):
    title: str = ""
    content: str = ""
    summary: str = ""


class _LibraryCharacterPayload(BaseModel):
    name: str = ""
    role: str = ""
    description: str = ""
    backstory: str = ""


class _LibraryStoryPayload(BaseModel):
    id: str = ""
    title: str = "Untitled"
    genre: str = ""
    setting: str = ""
    tone: str = ""
    description: str = ""
    characters: list[_LibraryCharacterPayload] = Field(default_factory=list)
    chapters: list[_LibraryChapterPayload] = Field(default_factory=list)


def _slug(text: str, fallback: str = "story") -> str:
    cleaned = _SAFE_NAME_RE.sub("-", (text or "").strip())
    cleaned = cleaned.strip("-")[:60]
    return cleaned or fallback


def _payload_to_story_draft(payload: _LibraryStoryPayload):
    """Convert frontend Story shape -> backend StoryDraft for reuse of exporters."""
    from models.schemas import Chapter, Character, StoryDraft

    chars = [
        Character(
            name=c.name or "Vô danh",
            role=c.role or "supporting",
            personality=c.description or "Chưa xác định",
            background=c.backstory or "",
        )
        for c in payload.characters
    ]
    chapters = [
        Chapter(
            chapter_number=i + 1,
            title=ch.title or f"Chương {i + 1}",
            content=ch.content or "",
            word_count=len((ch.content or "").split()),
            summary=ch.summary or "",
        )
        for i, ch in enumerate(payload.chapters)
    ]
    return StoryDraft(
        title=payload.title or "Untitled",
        genre=payload.genre or "",
        synopsis=payload.description or "",
        characters=chars,
        chapters=chapters,
    )


def _serve_library_file(path: str, download_name: str):
    resolved = pathlib.Path(path).resolve()
    try:
        resolved.relative_to(_OUTPUT_ROOT_ABS)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid export path")
    if not resolved.exists():
        raise HTTPException(status_code=404, detail="Export file not found")
    return FileResponse(str(resolved), filename=pathlib.Path(download_name).name)


@router.post("/library/{fmt}", dependencies=[_READ_STORIES])
async def export_library_story(fmt: str, story: _LibraryStoryPayload = Body(...)):
    """Export a frontend-library story (localStorage shape) as docx | pdf | epub.

    The story payload travels in the request body; nothing is persisted server-side
    beyond the generated file in `output/<story-slug>/exports/`.
    """
    fmt_lower = fmt.lower()
    if fmt_lower not in {"docx", "pdf", "epub"}:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {fmt}")

    draft = _payload_to_story_draft(story)
    if not draft.chapters:
        return JSONResponse({"error": "Truyện chưa có chương để xuất"}, status_code=400)

    # Prefer the localStorage story id as the scope key (stable across exports
    # of the same story); fall back to the title.
    out_dir = pathlib.Path(_exports_dir(draft.title, story_id=story.id or None))
    out_dir.mkdir(parents=True, exist_ok=True)
    base = f"{_slug(draft.title)}-{uuid.uuid4().hex[:8]}"
    out_path = str(out_dir / f"{base}.{fmt_lower}")
    download_name = f"{_slug(draft.title)}.{fmt_lower}"

    try:
        if fmt_lower == "docx":
            from services.export.docx_exporter import DOCXExporter
            path = DOCXExporter.export(draft, out_path, characters=draft.characters)
        elif fmt_lower == "pdf":
            from services.export.pdf_exporter import PDFExporter
            path = PDFExporter.export(draft, out_path, characters=draft.characters)
        else:  # epub
            from services.export.epub_exporter import EPUBExporter
            path = EPUBExporter.export(draft, out_path, characters=draft.characters)
    except Exception as e:  # pragma: no cover — exporter-specific failures surface as 500
        logger.exception(f"Library export ({fmt_lower}) failed")
        return JSONResponse({"error": f"Xuất {fmt_lower.upper()} thất bại: {e}"}, status_code=500)

    if not path:
        return JSONResponse({"error": f"Xuất {fmt_lower.upper()} thất bại"}, status_code=500)
    return _serve_library_file(path, download_name)
