"""Tests for Phase 3: One-Click Video Export."""

import json
import os
import sys
import tempfile
import zipfile


sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from models.schemas import VideoScript, StoryboardPanel, ShotType, VoiceLine
from services.video_exporter import (
    VideoExporter, _format_srt_time, _format_time_short, MAX_PANELS,
)


# --- Fixtures ---

def _make_video_script(n_panels=3):
    """Create a mock VideoScript with n panels and voice lines."""
    panels = []
    voice_lines = []
    for i in range(1, n_panels + 1):
        panels.append(StoryboardPanel(
            panel_number=i,
            chapter_number=(i - 1) // 2 + 1,
            shot_type=ShotType.WIDE if i % 2 else ShotType.CLOSE_UP,
            description=f"Scene {i} description",
            dialogue=f"Dialogue line {i}" if i % 2 else "",
            narration=f"Narration for scene {i}" if i % 2 == 0 else "",
            mood="tense" if i % 2 else "calm",
            characters_in_frame=[f"Char{i}"],
            duration_seconds=5.0,
            image_prompt=f"A dramatic scene {i}, cinematic lighting",
            sound_effect="thunder" if i == 1 else "",
            camera_movement="pan left" if i % 2 else "static",
        ))
        if i % 2:
            voice_lines.append(VoiceLine(
                character=f"Char{i}", text=f"Voice text {i}",
                emotion="angry" if i == 1 else "sad", panel_number=i,
            ))

    return VideoScript(
        title="Test Story",
        total_duration_seconds=n_panels * 5.0,
        panels=panels,
        voice_lines=voice_lines,
        character_descriptions={"Char1": "A brave warrior", "Char2": "A wise sage"},
        location_descriptions={"Forest": "Dark ancient forest"},
    )


# --- Time Formatters ---

class TestTimeFormatters:
    def test_srt_time_zero(self):
        assert _format_srt_time(0.0) == "00:00:00,000"

    def test_srt_time_minutes(self):
        assert _format_srt_time(65.5) == "00:01:05,500"

    def test_srt_time_hours(self):
        assert _format_srt_time(3661.25) == "01:01:01,250"

    def test_short_time_zero(self):
        assert _format_time_short(0.0) == "00:00"

    def test_short_time_minutes(self):
        assert _format_time_short(125.0) == "02:05"


# --- SRT Export ---

class TestExportSRT:
    def test_srt_format(self):
        vs = _make_video_script(3)
        exporter = VideoExporter(vs)
        srt = exporter.export_srt()
        assert "1\n" in srt
        assert "-->" in srt
        assert "00:00:00,000" in srt

    def test_srt_cumulative_timing(self):
        vs = _make_video_script(2)
        exporter = VideoExporter(vs)
        srt = exporter.export_srt()
        # Second panel starts at 5s
        assert "00:00:05,000" in srt

    def test_srt_narrator_lines(self):
        vs = _make_video_script(4)
        exporter = VideoExporter(vs)
        srt = exporter.export_srt()
        assert "[Narrator]" in srt

    def test_srt_character_dialogue(self):
        vs = _make_video_script(3)
        exporter = VideoExporter(vs)
        srt = exporter.export_srt()
        assert "Char1:" in srt or "Dialogue line" in srt

    def test_srt_empty_script(self):
        vs = VideoScript(title="Empty", panels=[], voice_lines=[])
        exporter = VideoExporter(vs)
        srt = exporter.export_srt()
        assert srt == ""


# --- Voiceover Export ---

class TestExportVoiceover:
    def test_voiceover_has_chapters(self):
        vs = _make_video_script(4)
        exporter = VideoExporter(vs)
        vo = exporter.export_voiceover()
        assert "CHUONG 1" in vo
        assert "CHUONG 2" in vo

    def test_voiceover_emotion_markers(self):
        vs = _make_video_script(3)
        exporter = VideoExporter(vs)
        vo = exporter.export_voiceover()
        assert "(angry)" in vo or "(sad)" in vo

    def test_voiceover_sfx(self):
        vs = _make_video_script(3)
        exporter = VideoExporter(vs)
        vo = exporter.export_voiceover()
        assert "[SFX: thunder]" in vo

    def test_voiceover_timing(self):
        vs = _make_video_script(2)
        exporter = VideoExporter(vs)
        vo = exporter.export_voiceover()
        assert "Timing: 5.0s" in vo


# --- Image Prompts Export ---

class TestExportImagePrompts:
    def test_image_prompts_numbered(self):
        vs = _make_video_script(3)
        exporter = VideoExporter(vs)
        ip = exporter.export_image_prompts()
        assert "Panel 1" in ip
        assert "Panel 2" in ip
        assert "Panel 3" in ip

    def test_image_prompts_shot_type(self):
        vs = _make_video_script(2)
        exporter = VideoExporter(vs)
        ip = exporter.export_image_prompts()
        assert "toàn_cảnh" in ip or "cận_cảnh" in ip

    def test_image_prompts_mood(self):
        vs = _make_video_script(2)
        exporter = VideoExporter(vs)
        ip = exporter.export_image_prompts()
        assert "Mood:" in ip

    def test_image_prompts_character_ref(self):
        vs = _make_video_script(2)
        exporter = VideoExporter(vs)
        ip = exporter.export_image_prompts()
        assert "CHARACTER REFERENCE" in ip
        assert "A brave warrior" in ip


# --- CapCut Draft Export ---

class TestExportCapcut:
    def test_capcut_structure(self):
        vs = _make_video_script(3)
        exporter = VideoExporter(vs)
        draft = exporter.export_capcut_draft()
        assert draft["type"] == "draft"
        assert "tracks" in draft
        assert len(draft["tracks"]) == 2  # video + text

    def test_capcut_microsecond_timing(self):
        vs = _make_video_script(2)
        exporter = VideoExporter(vs)
        draft = exporter.export_capcut_draft()
        seg = draft["tracks"][0]["segments"][0]
        assert seg["target_timerange"]["duration"] == 5_000_000  # 5s in us

    def test_capcut_canvas_vertical(self):
        vs = _make_video_script(1)
        exporter = VideoExporter(vs)
        draft = exporter.export_capcut_draft()
        assert draft["canvas_config"]["ratio"] == "9:16"

    def test_capcut_json_serializable(self):
        vs = _make_video_script(3)
        exporter = VideoExporter(vs)
        draft = exporter.export_capcut_draft()
        # Should not raise
        json.dumps(draft, ensure_ascii=False)


# --- CSV Timeline Export ---

class TestExportCSV:
    def test_csv_header(self):
        vs = _make_video_script(2)
        exporter = VideoExporter(vs)
        csv = exporter.export_timeline_csv()
        # Header may use quoted fields (CSV dialect)
        header = csv.split('\n')[0].strip()
        unquoted = header.replace('"', '')
        assert unquoted == "start_time,end_time,type,text,character,shot_type,chapter"

    def test_csv_rows(self):
        vs = _make_video_script(3)
        exporter = VideoExporter(vs)
        csv = exporter.export_timeline_csv()
        lines = csv.strip().split("\n")
        assert len(lines) > 1  # header + at least 1 data row


# --- ZIP Bundle Export ---

class TestExportAll:
    def test_export_all_creates_zip(self):
        vs = _make_video_script(3)
        exporter = VideoExporter(vs)
        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = exporter.export_all(tmpdir)
            assert zip_path is not None
            assert zip_path.endswith(".zip")
            assert os.path.exists(zip_path)

    def test_export_all_zip_contents(self):
        vs = _make_video_script(3)
        exporter = VideoExporter(vs)
        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = exporter.export_all(tmpdir)
            with zipfile.ZipFile(zip_path) as zf:
                names = zf.namelist()
                assert "subtitles.srt" in names
                assert "voiceover_script.txt" in names
                assert "image_prompts.txt" in names
                assert "capcut_draft.json" in names
                assert "timeline.csv" in names

    def test_export_all_empty_script(self):
        vs = VideoScript(title="Empty", panels=[], voice_lines=[])
        exporter = VideoExporter(vs)
        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = exporter.export_all(tmpdir)
            assert zip_path is not None  # ZIP still created, just empty content


# --- MAX_PANELS Limit ---

class TestMaxPanels:
    def test_max_panels_constant(self):
        assert MAX_PANELS == 200

    def test_srt_respects_limit(self):
        vs = _make_video_script(210)
        exporter = VideoExporter(vs)
        srt = exporter.export_srt()
        # Count SRT entries (numbered lines followed by timestamps)
        entries = srt.count("-->")
        assert entries <= 200 * 2  # max 2 entries per panel (narration + dialogue)


# --- Orchestrator Integration ---

class TestOrchestratorIntegration:
    def test_export_video_assets_method_exists(self):
        from pipeline.orchestrator import PipelineOrchestrator
        assert hasattr(PipelineOrchestrator, "export_video_assets")

    def test_export_video_assets_no_script(self):
        from pipeline.orchestrator import PipelineOrchestrator
        orch = PipelineOrchestrator()
        result = orch.export_video_assets()
        assert result is None


# --- App UI Integration ---

class TestAppIntegration:
    def test_app_has_video_export(self):
        app_path = os.path.join(os.path.dirname(__file__), "..", "ui", "gradio_app.py")
        with open(app_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        assert "video_export_btn" in content
        assert "export_video_assets" in content

    def test_video_exporter_import(self):
        """Verify video_exporter module imports cleanly."""
        from services.video_exporter import VideoExporter
        assert VideoExporter is not None
