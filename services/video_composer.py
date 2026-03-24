"""Video composer — assemble images + audio into MP4 using FFmpeg."""

import os
import subprocess
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class VideoComposer:
    """Compose video from storyboard images and audio narration."""

    def __init__(self, fps: int = 25, resolution: str = "1024x1024"):
        self.fps = fps  # Base fps for zoompan duration calculation
        self.resolution = resolution
        self.output_dir = "output/video"
        os.makedirs(self.output_dir, exist_ok=True)

    def compose(
        self,
        panels: list,
        audio_path: str = "",
        output_filename: str = "story_video.mp4",
    ) -> Optional[str]:
        """Compose video from panels with images + optional audio.

        panels: list of StoryboardPanel objects with image_path set.
        audio_path: optional path to full audiobook MP3.
        Returns: path to output MP4 or None.
        """
        valid_panels = [
            p
            for p in panels
            if getattr(p, "image_path", "") and os.path.exists(getattr(p, "image_path", ""))
        ]

        if not valid_panels:
            logger.warning("No panels with images found")
            return None

        output_path = os.path.join(self.output_dir, output_filename)

        try:
            concat_path = self._write_concat_file(valid_panels)

            # Use average panel duration for zoompan d (per-panel timing handled by concat demuxer)
            total_duration = sum(getattr(p, "duration_seconds", 5.0) for p in valid_panels)
            avg_duration = total_duration / len(valid_panels)
            zoompan_d = int(self.fps * avg_duration)

            # Dynamic timeout: total video duration * 2 + 120s buffer
            ffmpeg_timeout = int(total_duration * 2 + 120)

            cmd = [
                "ffmpeg", "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", concat_path,
                "-vf",
                (
                    f"scale={self.resolution}:force_original_aspect_ratio=decrease,"
                    f"pad={self.resolution}:(ow-iw)/2:(oh-ih)/2:black,"
                    f"zoompan=z='min(zoom+0.001,1.3)':d={zoompan_d}:s={self.resolution}"
                ),
                "-pix_fmt", "yuv420p",
            ]

            if audio_path and os.path.exists(audio_path):
                cmd.extend(["-i", audio_path, "-c:a", "aac", "-shortest"])

            cmd.extend(["-c:v", "libx264", "-preset", "medium", "-crf", "23", output_path])

            logger.info(f"Running FFmpeg: {' '.join(cmd[:10])}... (timeout={ffmpeg_timeout}s)")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=ffmpeg_timeout)

            if result.returncode != 0:
                logger.error(f"FFmpeg failed: {result.stderr[:500]}")
                return self._compose_simple(valid_panels, audio_path, output_path)

            logger.info(f"Video created: {output_path}")
            return output_path

        except FileNotFoundError:
            logger.error("FFmpeg not found. Install ffmpeg to enable video composition.")
            return None
        except subprocess.TimeoutExpired:
            logger.error(f"FFmpeg timed out (>{ffmpeg_timeout}s)")
            return None
        except Exception as e:
            logger.error(f"Video composition failed: {e}")
            return None

    def merge_chapter_audios(
        self, audio_paths: list, output_path: str = ""
    ) -> Optional[str]:
        """Merge multiple chapter audio files into one."""
        if not audio_paths:
            return None

        output = output_path or os.path.join(self.output_dir, "full_audio.mp3")

        try:
            list_path = os.path.join(self.output_dir, "audio_list.txt")
            with open(list_path, "w", encoding="utf-8") as f:
                for ap in audio_paths:
                    if os.path.exists(ap):
                        f.write(f"file '{ap.replace(chr(92), '/')}'\n")

            cmd = [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0",
                "-i", list_path,
                "-c", "copy",
                output,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

            if result.returncode == 0:
                return output
            logger.error(f"Audio merge failed: {result.stderr[:300]}")
            return None
        except Exception as e:
            logger.error(f"Audio merge failed: {e}")
            return None

    # ── Private ────────────────────────────────────────────────────────────────

    @staticmethod
    def _escape_concat_path(path: str) -> str:
        """Escape path for FFmpeg concat demuxer (forward slashes, escape single quotes)."""
        return path.replace("\\", "/").replace("'", "\\'")

    def _write_concat_file(self, panels: list) -> str:
        """Write FFmpeg concat demuxer file. Returns path."""
        concat_path = os.path.join(self.output_dir, "concat.txt")
        with open(concat_path, "w", encoding="utf-8") as f:
            for panel in panels:
                img = self._escape_concat_path(panel.image_path)
                duration = getattr(panel, "duration_seconds", 5.0)
                f.write(f"file '{img}'\n")
                f.write(f"duration {duration}\n")
            # FFmpeg requires repeating last entry without duration
            f.write(f"file '{self._escape_concat_path(panels[-1].image_path)}'\n")
        return concat_path

    def _compose_simple(
        self, panels: list, audio_path: str, output_path: str
    ) -> Optional[str]:
        """Simpler composition without Ken Burns effect (fallback)."""
        try:
            concat_path = os.path.join(self.output_dir, "concat.txt")

            cmd = [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0",
                "-i", concat_path,
                "-vf",
                (
                    f"scale={self.resolution}:force_original_aspect_ratio=decrease,"
                    f"pad={self.resolution}:(ow-iw)/2:(oh-ih)/2:black"
                ),
                "-pix_fmt", "yuv420p",
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "28",
            ]

            if audio_path and os.path.exists(audio_path):
                cmd.extend(["-i", audio_path, "-c:a", "aac", "-shortest"])

            cmd.append(output_path)

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

            if result.returncode == 0:
                logger.info(f"Simple video created: {output_path}")
                return output_path

            logger.error(f"Simple FFmpeg also failed: {result.stderr[:300]}")
            return None
        except Exception as e:
            logger.error(f"Simple composition failed: {e}")
            return None
