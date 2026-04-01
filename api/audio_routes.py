"""Audio API routes — TTS generation and streaming."""

import logging
from pathlib import Path

import edge_tts
from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/audio", tags=["audio"])

AUDIO_DIR = Path("data/audio")
DEFAULT_VOICE = "vi-VN-HoaiMyNeural"


def _audio_path(chapter_index: int) -> Path:
    return AUDIO_DIR / f"chapter_{chapter_index:03d}.mp3"


async def _generate_audio(text: str, voice: str, output_path: Path) -> None:
    """Generate TTS audio using edge-tts and save to output_path."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(str(output_path))


@router.post("/generate/{chapter_index}")
async def generate_audio(chapter_index: int, body: dict):
    """Generate TTS audio for a chapter. Body: {text: str, voice?: str}."""
    text = (body.get("text") or "").strip()
    if not text:
        return JSONResponse({"error": "text is required"}, status_code=400)

    voice = body.get("voice") or DEFAULT_VOICE
    output_path = _audio_path(chapter_index)

    try:
        await _generate_audio(text, voice, output_path)
        filename = output_path.name
        return {"status": "ok", "audio_url": f"/api/audio/stream/{filename}"}
    except Exception as e:
        logger.error("TTS generation failed for chapter %d: %s", chapter_index, e)
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/stream/{filename}")
async def stream_audio(filename: str):
    """Serve audio file with audio/mpeg content type."""
    # Sanitize: only allow simple filenames (no path traversal)
    if "/" in filename or "\\" in filename or ".." in filename:
        return JSONResponse({"error": "invalid filename"}, status_code=400)

    path = AUDIO_DIR / filename
    if not path.exists():
        return JSONResponse({"error": "audio not found"}, status_code=404)

    return FileResponse(str(path), media_type="audio/mpeg", filename=filename)


@router.get("/status/{chapter_index}")
async def audio_status(chapter_index: int):
    """Check if audio exists for a chapter."""
    path = _audio_path(chapter_index)
    exists = path.exists()
    return {
        "chapter_index": chapter_index,
        "exists": exists,
        "audio_url": f"/api/audio/stream/{path.name}" if exists else None,
    }
