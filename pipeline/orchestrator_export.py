"""Export pipeline output to various formats: TXT, JSON, Markdown, HTML, ZIP, video assets."""

import json
import logging
import os
import zipfile
from datetime import datetime
from typing import Optional

from models.schemas import PipelineOutput

logger = logging.getLogger(__name__)


class PipelineExporter:
    """Handles exporting PipelineOutput to files in various formats."""

    def __init__(self, output: PipelineOutput):
        self.output = output

    def export_output(self, output_dir: str = "output", formats: list[str] | None = None) -> list[str]:
        """Export results to files. Returns list of generated file paths."""
        if formats is None:
            formats = ["TXT", "Markdown", "JSON", "HTML", "EPUB"]
        os.makedirs(output_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        files = []

        if "TXT" in formats:
            if self.output.story_draft:
                path = os.path.join(output_dir, f"{timestamp}_draft.txt")
                with open(path, "w", encoding="utf-8") as f:
                    f.write(f"# {self.output.story_draft.title}\n\n")
                    for ch in self.output.story_draft.chapters:
                        f.write(f"\n## Chuong {ch.chapter_number}: {ch.title}\n\n")
                        f.write(ch.content + "\n")
                files.append(path)

            if self.output.enhanced_story:
                path = os.path.join(output_dir, f"{timestamp}_enhanced.txt")
                with open(path, "w", encoding="utf-8") as f:
                    f.write(f"# {self.output.enhanced_story.title} (Phien ban kich tinh)\n\n")
                    for ch in self.output.enhanced_story.chapters:
                        f.write(f"\n## Chuong {ch.chapter_number}: {ch.title}\n\n")
                        f.write(ch.content + "\n")
                files.append(path)

        if "JSON" in formats:
            if self.output.video_script:
                path = os.path.join(output_dir, f"{timestamp}_video_script.json")
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(
                        self.output.video_script.model_dump(),
                        f, ensure_ascii=False, indent=2,
                    )
                files.append(path)

            if self.output.simulation_result:
                path = os.path.join(output_dir, f"{timestamp}_simulation.json")
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(
                        self.output.simulation_result.model_dump(),
                        f, ensure_ascii=False, indent=2,
                    )
                files.append(path)

        if "Markdown" in formats:
            md_path = self._export_markdown(output_dir, timestamp)
            if md_path:
                files.append(md_path)

        if "HTML" in formats:
            html_path = self._export_html(output_dir, timestamp)
            if html_path:
                files.append(html_path)

        if "EPUB" in formats:
            epub_path = self._export_epub(output_dir, timestamp)
            if epub_path:
                files.append(epub_path)

        return files

    def export_zip(self, output_dir: str = "output", formats: list[str] | None = None) -> str:
        """Export all files and bundle into a single ZIP. Returns ZIP path or empty string."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        files = self.export_output(output_dir, formats)
        if not files:
            return ""
        zip_path = os.path.join(output_dir, f"{timestamp}_storyforge.zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in files:
                zf.write(f, os.path.basename(f))
        return zip_path

    def _export_html(self, output_dir: str, timestamp: str) -> Optional[str]:
        """Export story as standalone HTML reader page."""
        story = self.output.enhanced_story or self.output.story_draft
        if not story:
            return None
        from services.html_exporter import HTMLExporter
        path = os.path.join(output_dir, f"{timestamp}_story.html")
        chars = self.output.story_draft.characters if self.output.story_draft else []
        return HTMLExporter.export(story, path, characters=chars)

    def _export_epub(self, output_dir: str, timestamp: str) -> Optional[str]:
        """Export story as EPUB. Returns file path or None."""
        story = self.output.enhanced_story or self.output.story_draft
        if not story:
            return None
        from services.epub_exporter import EPUBExporter
        path = os.path.join(output_dir, f"{timestamp}_story.epub")
        chars = self.output.story_draft.characters if self.output.story_draft else []
        return EPUBExporter.export(story, path, characters=chars)

    def export_video_assets(self, output_dir: str = "output") -> Optional[str]:
        """Export video script as creator-friendly asset package (ZIP).

        Returns ZIP path or None if no video script available.
        """
        if not self.output.video_script:
            return None
        from services.video_exporter import VideoExporter
        exporter = VideoExporter(self.output.video_script)
        return exporter.export_all(output_dir)

    def _export_markdown(self, output_dir: str, timestamp: str) -> Optional[str]:
        """Export story as formatted Markdown. Returns file path or None."""
        story = self.output.enhanced_story or self.output.story_draft
        if not story:
            return None
        path = os.path.join(output_dir, f"{timestamp}_story.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"# {story.title}\n\n")
            if hasattr(story, "genre"):
                f.write(f"**The loai:** {story.genre}\n")
            if hasattr(story, "drama_score"):
                f.write(f"**Diem kich tinh:** {story.drama_score:.2f}\n")
            f.write("\n---\n\n")
            for ch in story.chapters:
                f.write(f"## Chuong {ch.chapter_number}: {ch.title}\n\n")
                f.write(ch.content + "\n\n")
        return path
