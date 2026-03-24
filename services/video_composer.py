"""Video composer — assemble images + audio into MP4 using FFmpeg."""

import asyncio
import os
import re
import shlex
import subprocess
import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# Directories that media inputs are expected to live under
_ALLOWED_MEDIA_DIRS = [
    os.path.abspath("output"),
    os.path.abspath("data"),
    os.path.abspath("assets"),
]


def _validate_media_path(path: str, allowed_dirs: list = None) -> bool:
    """Validate media file path to prevent injection and path traversal.

    Checks:
    - File must exist
    - No shell metacharacters (belt-and-suspenders; subprocess list-form is safe, but
      the path is also written into concat .txt files read by FFmpeg)
    - Resolved absolute path must be inside one of the allowed directories
    """
    if not path or not os.path.isfile(path):
        return False
    # Block shell metacharacters
    if re.search(r'[;&|`$\n\r]', path):
        logger.warning(f"Rejected suspicious path (metacharacters): {shlex.quote(path)}")
        return False
    # Directory containment check — prevents path traversal
    resolved = os.path.realpath(os.path.abspath(path))
    dirs = allowed_dirs or _ALLOWED_MEDIA_DIRS
    if not any(resolved.startswith(os.path.realpath(d) + os.sep) or
               resolved == os.path.realpath(d)
               for d in dirs):
        logger.warning(f"Rejected path outside allowed directories: {shlex.quote(path)}")
        return False
    return True


class VideoComposer:
    """Compose video from storyboard images and audio narration."""

    def __init__(self, fps: int = 25, resolution: str = "1024x1024"):
        self.fps = fps  # Base fps for zoompan duration calculation
        self.resolution = resolution
        self.output_dir = "output/video"
        os.makedirs(self.output_dir, exist_ok=True)

    def _calc_timeout(self, total_duration: float) -> int:
        """Calculate FFmpeg timeout based on duration and resolution."""
        base = total_duration * 2 + 120
        # Scale by resolution (1024x1024 = 1.0x, 1920x1080 ~ 2x, 3840x2160 ~ 4x)
        try:
            width = int(self.resolution.split("x")[0])
            scale = max(1.0, (width / 1024) ** 1.5)
        except (ValueError, IndexError):
            scale = 1.0
        return int(base * scale)

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
        concat_path = None

        try:
            concat_path = self._write_concat_file(valid_panels)

            # Use average panel duration for zoompan d (per-panel timing handled by concat demuxer)
            total_duration = sum(getattr(p, "duration_seconds", 5.0) for p in valid_panels)
            avg_duration = total_duration / len(valid_panels)
            zoompan_d = int(self.fps * avg_duration)

            # Dynamic timeout: scales with resolution
            ffmpeg_timeout = self._calc_timeout(total_duration)

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

            if audio_path and _validate_media_path(audio_path):
                cmd.extend(["-i", audio_path, "-c:a", "aac", "-shortest"])

            cmd.extend(["-c:v", "libx264", "-preset", "medium", "-crf", "23", output_path])

            logger.info(f"Running FFmpeg: {' '.join(cmd[:10])}... (timeout={ffmpeg_timeout}s)")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=ffmpeg_timeout)

            if result.returncode != 0:
                logger.error(f"FFmpeg failed: {result.stderr[-2000:]}")
                logger.debug(f"FFmpeg full stderr: {result.stderr}")
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
        finally:
            if concat_path and os.path.exists(concat_path):
                try:
                    os.remove(concat_path)
                except OSError:
                    pass

    async def compose_async(
        self,
        panels: list,
        audio_path: str = "",
        output_filename: str = "story_video.mp4",
        progress_callback: Callable[[str], None] = None,
    ) -> Optional[str]:
        """Async video composition with progress reporting."""
        valid_panels = [
            p for p in panels
            if getattr(p, "image_path", "") and os.path.exists(getattr(p, "image_path", ""))
        ]
        if not valid_panels:
            logger.warning("No panels with images found")
            return None

        output_path = os.path.join(self.output_dir, output_filename)
        concat_path = None
        process = None

        try:
            concat_path = self._write_concat_file(valid_panels)
            total_duration = sum(getattr(p, "duration_seconds", 5.0) for p in valid_panels)
            avg_duration = total_duration / len(valid_panels)
            zoompan_d = int(self.fps * avg_duration)
            ffmpeg_timeout = self._calc_timeout(total_duration)

            cmd = [
                "ffmpeg", "-y", "-progress", "pipe:1",
                "-f", "concat", "-safe", "0", "-i", concat_path,
                "-vf",
                (
                    f"scale={self.resolution}:force_original_aspect_ratio=decrease,"
                    f"pad={self.resolution}:(ow-iw)/2:(oh-ih)/2:black,"
                    f"zoompan=z='min(zoom+0.001,1.3)':d={zoompan_d}:s={self.resolution}"
                ),
                "-pix_fmt", "yuv420p",
            ]

            if audio_path and _validate_media_path(audio_path):
                cmd.extend(["-i", audio_path, "-c:a", "aac", "-shortest"])

            cmd.extend(["-c:v", "libx264", "-preset", "medium", "-crf", "23", output_path])

            if progress_callback:
                progress_callback(f"Starting FFmpeg encode ({len(valid_panels)} panels)...")

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            # Parse FFmpeg progress output (H2 fix: wall-clock total timeout)
            deadline = asyncio.get_event_loop().time() + ffmpeg_timeout
            while True:
                remaining = deadline - asyncio.get_event_loop().time()
                if remaining <= 0:
                    raise asyncio.TimeoutError()
                line = await asyncio.wait_for(process.stdout.readline(), timeout=remaining)
                if not line:
                    break
                decoded = line.decode("utf-8", errors="replace").strip()
                if decoded.startswith("out_time_ms=") and progress_callback:
                    try:
                        elapsed_ms = int(decoded.split("=")[1])
                        elapsed_s = elapsed_ms / 1_000_000
                        pct = min(100, int(elapsed_s / total_duration * 100))
                        progress_callback(f"Encoding video... {pct}%")
                    except (ValueError, ZeroDivisionError):
                        pass

            await process.wait()

            if process.returncode != 0:
                stderr = await process.stderr.read()
                stderr_text = stderr.decode()
                logger.error(f"FFmpeg async failed: {stderr_text[-2000:]}")
                logger.debug(f"FFmpeg full stderr: {stderr_text}")
                return self._compose_simple(valid_panels, audio_path, output_path)

            if progress_callback:
                progress_callback("Video encoding complete!")
            logger.info(f"Video created: {output_path}")
            return output_path

        except FileNotFoundError:
            logger.error("FFmpeg not found.")
            return None
        except asyncio.TimeoutError:
            logger.error(f"FFmpeg timed out (>{ffmpeg_timeout}s)")
            if process and process.returncode is None:
                process.kill()
                await process.wait()
            return None
        except Exception as e:
            logger.error(f"Async video composition failed: {e}")
            if process and process.returncode is None:
                process.kill()
                await process.wait()
            return None
        finally:
            if concat_path and os.path.exists(concat_path):
                try:
                    os.remove(concat_path)
                except OSError:
                    pass

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
        fallback_concat = os.path.join(self.output_dir, "concat_simple.txt")
        try:
            # Write fresh concat file — do not reuse potentially corrupt concat.txt
            with open(fallback_concat, "w", encoding="utf-8") as f:
                for panel in panels:
                    img = self._escape_concat_path(panel.image_path)
                    duration = getattr(panel, "duration_seconds", 5.0)
                    f.write(f"file '{img}'\n")
                    f.write(f"duration {duration}\n")
                f.write(f"file '{self._escape_concat_path(panels[-1].image_path)}'\n")

            cmd = [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0",
                "-i", fallback_concat,
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

            if audio_path and _validate_media_path(audio_path):
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
        finally:
            if os.path.exists(fallback_concat):
                try:
                    os.remove(fallback_concat)
                except OSError:
                    pass
