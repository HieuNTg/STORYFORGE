"""Tests for VideoComposer service."""
from unittest.mock import MagicMock, patch


from services.video_composer import VideoComposer


def _make_panel(image_path: str, duration: float = 5.0):
    """Create a minimal panel-like object."""
    panel = MagicMock()
    panel.image_path = image_path
    panel.duration_seconds = duration
    return panel


# ── compose — no valid panels ─────────────────────────────────────────────────

def test_compose_no_panels_returns_none(tmp_path):
    composer = VideoComposer()
    composer.output_dir = str(tmp_path)
    result = composer.compose(panels=[])
    assert result is None


def test_compose_panels_without_existing_images_returns_none(tmp_path):
    composer = VideoComposer()
    composer.output_dir = str(tmp_path)
    panels = [_make_panel("/nonexistent/image.png")]
    result = composer.compose(panels=panels)
    assert result is None


# ── compose — concat file generation ─────────────────────────────────────────

def test_compose_writes_concat_file(tmp_path):
    # Create fake image files
    img1 = tmp_path / "img1.png"
    img2 = tmp_path / "img2.png"
    img1.write_bytes(b"img1")
    img2.write_bytes(b"img2")

    panels = [
        _make_panel(str(img1), duration=3.0),
        _make_panel(str(img2), duration=7.0),
    ]

    mock_result = MagicMock()
    mock_result.returncode = 0

    composer = VideoComposer()
    composer.output_dir = str(tmp_path)

    # Capture concat content before cleanup removes it
    captured_content = {}
    orig_write = composer._write_concat_file

    def _capture_write(p):
        path = orig_write(p)
        captured_content["text"] = open(path, encoding="utf-8").read()
        return path

    with patch.object(composer, '_write_concat_file', side_effect=_capture_write), \
         patch("services.video_composer.subprocess.run", return_value=mock_result):
        composer.compose(panels=panels, output_filename="test.mp4")

    content = captured_content["text"]
    assert "duration 3.0" in content
    assert "duration 7.0" in content
    # Last entry repeated without duration (FFmpeg requirement)
    lines = [line for line in content.splitlines() if line.startswith("file")]
    assert len(lines) == 3  # 2 panels + repeat of last


def test_compose_calls_ffmpeg_with_correct_args(tmp_path):
    img = tmp_path / "panel.png"
    img.write_bytes(b"png")
    panels = [_make_panel(str(img))]

    mock_result = MagicMock()
    mock_result.returncode = 0

    composer = VideoComposer()
    composer.output_dir = str(tmp_path)

    with patch("services.video_composer.subprocess.run", return_value=mock_result) as mock_run:
        composer.compose(panels=panels, output_filename="out.mp4")

    cmd = mock_run.call_args[0][0]
    assert cmd[0] == "ffmpeg"
    assert "-f" in cmd
    assert "concat" in cmd
    assert str(tmp_path / "out.mp4") in cmd


def test_compose_ffmpeg_not_found_returns_none(tmp_path):
    img = tmp_path / "panel.png"
    img.write_bytes(b"png")
    panels = [_make_panel(str(img))]

    composer = VideoComposer()
    composer.output_dir = str(tmp_path)

    with patch("services.video_composer.subprocess.run", side_effect=FileNotFoundError):
        result = composer.compose(panels=panels)

    assert result is None


# ── merge_chapter_audios ──────────────────────────────────────────────────────

def test_merge_chapter_audios_empty_returns_none(tmp_path):
    composer = VideoComposer()
    composer.output_dir = str(tmp_path)
    result = composer.merge_chapter_audios([])
    assert result is None


def test_merge_chapter_audios_calls_ffmpeg(tmp_path):
    audio1 = tmp_path / "ch1.mp3"
    audio2 = tmp_path / "ch2.mp3"
    audio1.write_bytes(b"audio1")
    audio2.write_bytes(b"audio2")

    mock_result = MagicMock()
    mock_result.returncode = 0

    composer = VideoComposer()
    composer.output_dir = str(tmp_path)
    out = str(tmp_path / "merged.mp3")

    with patch("services.video_composer.subprocess.run", return_value=mock_result) as mock_run:
        result = composer.merge_chapter_audios([str(audio1), str(audio2)], output_path=out)

    assert result == out
    cmd = mock_run.call_args[0][0]
    assert "ffmpeg" in cmd
    assert "concat" in cmd


def test_merge_chapter_audios_failure_returns_none(tmp_path):
    audio = tmp_path / "ch1.mp3"
    audio.write_bytes(b"audio")

    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stderr = "error"

    composer = VideoComposer()
    composer.output_dir = str(tmp_path)

    with patch("services.video_composer.subprocess.run", return_value=mock_result):
        result = composer.merge_chapter_audios([str(audio)])

    assert result is None
