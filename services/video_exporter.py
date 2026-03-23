"""Video asset exporter — converts VideoScript to creator-friendly formats.

Exports: SRT subtitles, voiceover scripts, image prompt lists,
timeline JSON (CapCut-compatible), and bundled ZIP packages.
"""

import csv
import io
import json
import logging
import os
import zipfile
from typing import Optional

from models.schemas import VideoScript, StoryboardPanel

logger = logging.getLogger(__name__)

# Max panels to export (prevent huge files for 50-chapter stories)
MAX_PANELS = 200


def _format_srt_time(seconds: float) -> str:
    """Convert seconds to SRT timestamp format HH:MM:SS,mmm."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _format_time_short(seconds: float) -> str:
    """Convert seconds to MM:SS format for voiceover script."""
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes:02d}:{secs:02d}"


class VideoExporter:
    """Exports VideoScript data to multiple creator-friendly formats."""

    def __init__(self, video_script: VideoScript):
        self._vs = video_script
        if len(video_script.panels) > MAX_PANELS:
            logger.warning(
                f"VideoScript has {len(video_script.panels)} panels, "
                f"exporting first {MAX_PANELS} only"
            )
        # Build voice_line lookup by panel_number
        self._voice_by_panel: dict[int, list] = {}
        for vl in self._vs.voice_lines:
            self._voice_by_panel.setdefault(vl.panel_number, []).append(vl)

    def export_srt(self) -> str:
        """Generate SRT subtitle file content with cumulative timing."""
        lines = []
        entry_num = 0
        current_time = 0.0

        for panel in self._vs.panels[:MAX_PANELS]:
            end_time = current_time + panel.duration_seconds

            # Narration entry
            if panel.narration:
                entry_num += 1
                lines.append(str(entry_num))
                lines.append(
                    f"{_format_srt_time(current_time)} --> "
                    f"{_format_srt_time(current_time + panel.duration_seconds / 2)}"
                )
                lines.append(f"[Narrator] {panel.narration}")
                lines.append("")

            # Dialogue entry
            if panel.dialogue:
                entry_num += 1
                # Use voice_line character name if available
                voice_lines = self._voice_by_panel.get(panel.panel_number, [])
                if voice_lines:
                    char_name = voice_lines[0].character
                else:
                    # Extract from characters_in_frame
                    char_name = panel.characters_in_frame[0] if panel.characters_in_frame else "Character"

                start = current_time + panel.duration_seconds / 2 if panel.narration else current_time
                lines.append(str(entry_num))
                lines.append(
                    f"{_format_srt_time(start)} --> {_format_srt_time(end_time)}"
                )
                lines.append(f"{char_name}: {panel.dialogue}")
                lines.append("")

            # Panel with no text — add description as subtitle
            if not panel.narration and not panel.dialogue:
                entry_num += 1
                lines.append(str(entry_num))
                lines.append(
                    f"{_format_srt_time(current_time)} --> {_format_srt_time(end_time)}"
                )
                lines.append(f"[{panel.description[:80].replace('-->', '- -')}]")
                lines.append("")

            current_time = end_time

        return "\n".join(lines)

    def export_voiceover(self) -> str:
        """Generate voiceover script with emotion markers and timing."""
        lines = []
        current_time = 0.0
        current_chapter = -1

        for panel in self._vs.panels[:MAX_PANELS]:
            # Chapter header
            if panel.chapter_number != current_chapter:
                current_chapter = panel.chapter_number
                if lines:
                    lines.append("")
                lines.append(f"{'=' * 50}")
                lines.append(f"CHUONG {current_chapter}")
                lines.append(f"{'=' * 50}")
                lines.append("")

            end_time = current_time + panel.duration_seconds
            time_range = f"{_format_time_short(current_time)} - {_format_time_short(end_time)}"

            lines.append(f"--- SCENE {panel.panel_number} (Ch.{panel.chapter_number}) | {time_range} ---")

            # Narration
            if panel.narration:
                lines.append(f"[Narrator] (neutral) {panel.narration}")

            # Dialogue from voice_lines (has emotion) or panel
            voice_lines = self._voice_by_panel.get(panel.panel_number, [])
            if voice_lines:
                for vl in voice_lines:
                    emotion = vl.emotion or "neutral"
                    lines.append(f'[{vl.character}] ({emotion}) "{vl.text}"')
            elif panel.dialogue:
                char_name = panel.characters_in_frame[0] if panel.characters_in_frame else "Character"
                lines.append(f'[{char_name}] (neutral) "{panel.dialogue}"')

            # Sound effects
            if panel.sound_effect:
                lines.append(f"[SFX: {panel.sound_effect}]")

            lines.append(f"--- Timing: {panel.duration_seconds:.1f}s ---")
            lines.append("")
            current_time = end_time

        return "\n".join(lines)

    def export_image_prompts(self) -> str:
        """Generate numbered image prompt list for batch AI generation."""
        lines = [
            f"# Image Prompts — {self._vs.title}",
            f"# Total: {min(len(self._vs.panels), MAX_PANELS)} panels",
            "",
        ]

        for panel in self._vs.panels[:MAX_PANELS]:
            shot_label = panel.shot_type.value
            lines.append(f"Panel {panel.panel_number} (Ch.{panel.chapter_number} - {shot_label}):")

            if panel.image_prompt:
                lines.append(panel.image_prompt)
            else:
                lines.append(panel.description)

            if panel.characters_in_frame:
                lines.append(f"Characters: {', '.join(panel.characters_in_frame)}")
            if panel.mood:
                lines.append(f"Mood: {panel.mood}")
            lines.append("")

        # Append character descriptions for reference
        if self._vs.character_descriptions:
            lines.append("=" * 50)
            lines.append("CHARACTER REFERENCE")
            lines.append("=" * 50)
            for name, desc in self._vs.character_descriptions.items():
                lines.append(f"\n{name}:")
                lines.append(desc)

        return "\n".join(lines)

    def export_capcut_draft(self) -> dict:
        """Generate CapCut-compatible timeline JSON.

        Structure follows CapCut's draft.json format (simplified):
        - tracks: video track with segments, text track with subtitles
        - Each segment has start/end time in microseconds
        """
        # CapCut uses microseconds for timing
        US_PER_SEC = 1_000_000
        current_time_us = 0

        video_segments = []
        text_segments = []

        for panel in self._vs.panels[:MAX_PANELS]:
            duration_us = int(panel.duration_seconds * US_PER_SEC)
            end_time_us = current_time_us + duration_us

            # Video segment (scene placeholder)
            video_segments.append({
                "id": f"segment_{panel.panel_number}",
                "type": "video",
                "target_timerange": {
                    "start": current_time_us,
                    "duration": duration_us,
                },
                "extra_info": {
                    "panel_number": panel.panel_number,
                    "chapter": panel.chapter_number,
                    "shot_type": panel.shot_type.value,
                    "description": panel.description,
                    "image_prompt": panel.image_prompt,
                },
            })

            # Text overlay segment (dialogue/narration)
            text_content = panel.dialogue or panel.narration
            if text_content:
                text_segments.append({
                    "id": f"text_{panel.panel_number}",
                    "type": "text",
                    "target_timerange": {
                        "start": current_time_us,
                        "duration": duration_us,
                    },
                    "content": text_content,
                    "font_size": 8.0,
                })

            current_time_us = end_time_us

        total_duration_us = current_time_us

        return {
            "type": "draft",
            "version": "5.0.0",
            "name": self._vs.title,
            "duration": total_duration_us,
            "canvas_config": {"width": 1080, "height": 1920, "ratio": "9:16"},
            "tracks": [
                {
                    "type": "video",
                    "segments": video_segments,
                },
                {
                    "type": "text",
                    "segments": text_segments,
                },
            ],
            "metadata": {
                "generator": "StoryForge",
                "total_panels": len(video_segments),
                "total_duration_seconds": self._vs.total_duration_seconds,
            },
        }

    def export_timeline_csv(self) -> str:
        """Export as CSV timeline — universal fallback format."""
        output = io.StringIO()
        writer = csv.writer(output, quoting=csv.QUOTE_ALL)
        writer.writerow(["start_time", "end_time", "type", "text", "character", "shot_type", "chapter"])
        current_time = 0.0

        for panel in self._vs.panels[:MAX_PANELS]:
            end_time = current_time + panel.duration_seconds
            start_str = f"{current_time:.3f}"
            end_str = f"{end_time:.3f}"
            shot = panel.shot_type.value

            if panel.narration:
                writer.writerow([start_str, end_str, "narration", panel.narration, "Narrator", shot, panel.chapter_number])

            if panel.dialogue:
                char = panel.characters_in_frame[0] if panel.characters_in_frame else "Character"
                writer.writerow([start_str, end_str, "dialogue", panel.dialogue, char, shot, panel.chapter_number])

            current_time = end_time

        return output.getvalue()

    def export_all(self, output_dir: str = "output") -> Optional[str]:
        """Export all formats and bundle into ZIP. Returns ZIP path."""
        import tempfile as _tempfile
        os.makedirs(output_dir, exist_ok=True)

        try:
            # Write intermediates to temp dir, only ZIP goes to output_dir
            with _tempfile.TemporaryDirectory() as tmpdir:
                file_map = {
                    "subtitles.srt": self.export_srt(),
                    "voiceover_script.txt": self.export_voiceover(),
                    "image_prompts.txt": self.export_image_prompts(),
                    "timeline.csv": self.export_timeline_csv(),
                }
                capcut_data = self.export_capcut_draft()

                zip_path = os.path.join(output_dir, "video_assets.zip")
                with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                    for filename, content in file_map.items():
                        tmp_path = os.path.join(tmpdir, filename)
                        with open(tmp_path, "w", encoding="utf-8") as f:
                            f.write(content)
                        zf.write(tmp_path, filename)

                    # CapCut JSON
                    cc_path = os.path.join(tmpdir, "capcut_draft.json")
                    with open(cc_path, "w", encoding="utf-8") as f:
                        json.dump(capcut_data, f, ensure_ascii=False, indent=2)
                    zf.write(cc_path, "capcut_draft.json")

            logger.info(f"Video assets exported to {zip_path} (5 files)")
            return zip_path

        except Exception as e:
            logger.error(f"Video export error: {e}")
            return None
