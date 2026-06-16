"""Export pipeline output to various formats: TXT, JSON, Markdown, HTML, ZIP, video assets."""

import json
import logging
import os
import zipfile
from datetime import datetime
from typing import Optional

from models.schemas import PipelineOutput
from plugins import plugin_manager

logger = logging.getLogger(__name__)


class PipelineExporter:
    """Handles exporting PipelineOutput to files in various formats."""

    def __init__(self, output: PipelineOutput):
        self.output = output

    def _default_output_dir(self) -> str:
        """Per-story exports dir derived from the output's title (centralised).

        Replaces the old bare ``output/`` default, which dumped exports at the
        root. Falls back to the resolver's ``_unsorted`` bucket when there is no
        title to scope by.
        """
        from services.output_paths import exports_dir

        story = self.output.enhanced_story or self.output.story_draft
        title = getattr(story, "title", None)
        return exports_dir(title)

    def export_output(
        self, output_dir: str | None = None, formats: list[str] | None = None
    ) -> list[str]:
        """Export results to files. Returns list of generated file paths.

        ``output_dir=None`` resolves to the per-story exports dir (see
        :meth:`_default_output_dir`); explicit callers (CLI, tests) override it.
        """
        if output_dir is None:
            output_dir = self._default_output_dir()
        if formats is None:
            formats = ["TXT", "Markdown", "JSON", "HTML", "EPUB"]
        os.makedirs(output_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        files = []

        if "TXT" in formats:
            if self.output.story_draft:
                path = os.path.join(output_dir, f"{timestamp}_draft.txt")
                try:
                    draft_data = plugin_manager.apply_export(
                        "txt", self.output.story_draft
                    )
                except Exception as _e:
                    logger.warning(f"Plugin apply_export txt failed: {_e}")
                    draft_data = self.output.story_draft
                with open(path, "w", encoding="utf-8") as f:
                    f.write(f"# {draft_data.title}\n\n")
                    for ch in draft_data.chapters:
                        f.write(f"\n## Chương {ch.chapter_number}: {ch.title}\n\n")
                        f.write(ch.content + "\n")
                files.append(path)

            if self.output.enhanced_story:
                path = os.path.join(output_dir, f"{timestamp}_enhanced.txt")
                try:
                    enhanced_data = plugin_manager.apply_export(
                        "txt", self.output.enhanced_story
                    )
                except Exception as _e:
                    logger.warning(f"Plugin apply_export txt (enhanced) failed: {_e}")
                    enhanced_data = self.output.enhanced_story
                with open(path, "w", encoding="utf-8") as f:
                    f.write(f"# {enhanced_data.title} (Phiên bản kịch tính)\n\n")
                    for ch in enhanced_data.chapters:
                        f.write(f"\n## Chương {ch.chapter_number}: {ch.title}\n\n")
                        f.write(ch.content + "\n")
                files.append(path)

        if "JSON" in formats:
            # Structured JSON of the story itself — the format users reach for to
            # round-trip a story programmatically. Mirrors the TXT branch: the
            # draft and (when present) the enhanced version are written as
            # separate files. Previously JSON export only emitted a simulation
            # result, so "Export JSON" produced nothing unless a simulation had
            # been run.
            if self.output.story_draft:
                path = os.path.join(output_dir, f"{timestamp}_draft.json")
                try:
                    draft_data = plugin_manager.apply_export(
                        "json", self.output.story_draft.model_dump()
                    )
                except Exception as _e:
                    logger.warning(f"Plugin apply_export json (draft) failed: {_e}")
                    draft_data = self.output.story_draft.model_dump()
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(draft_data, f, ensure_ascii=False, indent=2)
                files.append(path)

            if self.output.enhanced_story:
                path = os.path.join(output_dir, f"{timestamp}_enhanced.json")
                try:
                    enhanced_data = plugin_manager.apply_export(
                        "json", self.output.enhanced_story.model_dump()
                    )
                except Exception as _e:
                    logger.warning(f"Plugin apply_export json (enhanced) failed: {_e}")
                    enhanced_data = self.output.enhanced_story.model_dump()
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(enhanced_data, f, ensure_ascii=False, indent=2)
                files.append(path)

            if self.output.simulation_result:
                path = os.path.join(output_dir, f"{timestamp}_simulation.json")
                try:
                    sim_data = plugin_manager.apply_export(
                        "json", self.output.simulation_result.model_dump()
                    )
                except Exception as _e:
                    logger.warning(
                        f"Plugin apply_export json (simulation) failed: {_e}"
                    )
                    sim_data = self.output.simulation_result.model_dump()
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(sim_data, f, ensure_ascii=False, indent=2)
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

    def export_zip(
        self, output_dir: str | None = None, formats: list[str] | None = None
    ) -> str:
        """Export all files and bundle into a single ZIP. Returns ZIP path or empty string."""
        if output_dir is None:
            output_dir = self._default_output_dir()
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
        try:
            story = plugin_manager.apply_export("html", story) or story
        except Exception as _e:
            logger.warning(f"Plugin apply_export html failed: {_e}")
        from services.html_exporter import HTMLExporter

        path = os.path.join(output_dir, f"{timestamp}_story.html")
        chars = self.output.story_draft.characters if self.output.story_draft else []
        return HTMLExporter.export(story, path, characters=chars)

    def _export_epub(self, output_dir: str, timestamp: str) -> Optional[str]:
        """Export story as EPUB. Returns file path or None."""
        story = self.output.enhanced_story or self.output.story_draft
        if not story:
            return None
        try:
            story = plugin_manager.apply_export("epub", story) or story
        except Exception as _e:
            logger.warning(f"Plugin apply_export epub failed: {_e}")
        from services.epub_exporter import EPUBExporter

        path = os.path.join(output_dir, f"{timestamp}_story.epub")
        chars = self.output.story_draft.characters if self.output.story_draft else []
        return EPUBExporter.export(story, path, characters=chars)

    def _export_markdown(self, output_dir: str, timestamp: str) -> Optional[str]:
        """Export story as formatted Markdown. Returns file path or None."""
        story = self.output.enhanced_story or self.output.story_draft
        if not story:
            return None
        try:
            story = plugin_manager.apply_export("markdown", story) or story
        except Exception as _e:
            logger.warning(f"Plugin apply_export markdown failed: {_e}")
        path = os.path.join(output_dir, f"{timestamp}_story.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"# {story.title}\n\n")
            if hasattr(story, "genre"):
                f.write(f"**Thể loại:** {story.genre}\n")
            if hasattr(story, "drama_score"):
                f.write(f"**Điểm kịch tính:** {story.drama_score:.2f}\n")
            f.write("\n---\n\n")
            for ch in story.chapters:
                f.write(f"## Chương {ch.chapter_number}: {ch.title}\n\n")
                f.write(ch.content + "\n\n")
        return path
