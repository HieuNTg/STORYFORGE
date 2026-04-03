"""Multi-platform story export — Wattpad, NovelHD, Royal Road ready formats."""

import html
import json
import logging
import os
import re
import zipfile
from typing import Union
from models.schemas import StoryDraft, EnhancedStory

logger = logging.getLogger(__name__)

MAX_WATTPAD_CHAPTER_WORDS = 5000  # Wattpad recommended chapter length
MAX_TAGS = 25  # Wattpad tag limit


class PlatformExporter:
    """Export stories in platform-specific formats for manual publishing."""

    @staticmethod
    def export_wattpad(
        story: Union[StoryDraft, EnhancedStory],
        output_dir: str = "output/wattpad",
    ) -> dict:
        """Export Wattpad-ready package: per-chapter HTML + metadata JSON + full_story.txt + ZIP."""
        os.makedirs(output_dir, exist_ok=True)
        files = []

        # Build chapter details with reading_time_min
        chapter_details = []
        for ch in story.chapters:
            words = len(ch.content.split())
            chapter_details.append({
                "chapter_number": ch.chapter_number,
                "title": ch.title,
                "content": ch.content,
                "word_count": words,
                "reading_time_min": max(1, words // 200),
                "author_notes": "",
            })

        # Metadata
        meta = {
            "title": story.title,
            "description": getattr(story, "synopsis", "")[:2000],
            "genre": story.genre if hasattr(story, "genre") else "",
            "tags": PlatformExporter._generate_tags(story),
            "language": "vi",
            "chapters": len(story.chapters),
            "total_words": sum(cd["word_count"] for cd in chapter_details),
            "platform_notes": "Copy-paste mỗi chương vào Wattpad editor",
            "chapter_details": [
                {k: v for k, v in cd.items() if k != "content"}
                for cd in chapter_details
            ],
        }
        meta_path = os.path.join(output_dir, "metadata.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        files.append(meta_path)

        # Per-chapter HTML files (for rich text paste)
        for ch in story.chapters:
            ch_html = PlatformExporter._chapter_to_wattpad_html(ch)
            ch_path = os.path.join(output_dir, f"chapter_{ch.chapter_number:03d}.html")
            with open(ch_path, "w", encoding="utf-8") as f:
                f.write(ch_html)
            files.append(ch_path)

        # Plain text version (alternative paste)
        txt_path = os.path.join(output_dir, "full_story.txt")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(f"{story.title}\n{'=' * 40}\n\n")
            for ch in story.chapters:
                f.write(f"Chuong {ch.chapter_number}: {ch.title}\n")
                f.write(f"{'-' * 30}\n{ch.content}\n\n")
        files.append(txt_path)

        # Character appendix
        if hasattr(story, "characters") and story.characters:
            char_text = "\n".join(
                f"- {c.name}: {c.personality}" for c in story.characters
            )
            char_path = os.path.join(output_dir, "characters.txt")
            with open(char_path, "w", encoding="utf-8") as f:
                f.write(f"Nhan vat chinh:\n{char_text}")
            files.append(char_path)

        # ZIP bundle
        safe_title = re.sub(r'[^\w\s-]', '', story.title)[:30].strip() or "story"
        zip_path = os.path.join(output_dir, f"{safe_title}_wattpad.zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for fp in files:
                zf.write(fp, os.path.basename(fp))

        logger.info(f"Wattpad export: {len(files)} files + ZIP -> {output_dir}")
        return {"files": files, "zip_path": zip_path, "metadata": meta, "output_dir": output_dir}

    @staticmethod
    def _chapter_to_wattpad_html(chapter) -> str:
        """Convert chapter to Wattpad-friendly HTML."""
        title = html.escape(chapter.title)
        paragraphs = []
        for p in chapter.content.split("\n"):
            p = p.strip()
            if p:
                escaped = html.escape(p)
                escaped = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', escaped)
                escaped = re.sub(r'\*(.+?)\*', r'<i>\1</i>', escaped)
                paragraphs.append(f"<p>{escaped}</p>")
        body = "\n".join(paragraphs)
        return f"<h2>Chuong {chapter.chapter_number}: {title}</h2>\n{body}"

    @staticmethod
    def _generate_tags(story) -> list:
        """Generate platform tags from story metadata."""
        tags = []
        if hasattr(story, "genre") and story.genre:
            tags.append(story.genre.lower().replace(" ", ""))
        tags.extend(["vietnamese", "storyforge", "aiwriting"])
        if hasattr(story, "sub_genres"):
            for sg in story.sub_genres[:5]:
                tags.append(sg.lower().replace(" ", ""))
        return tags[:MAX_TAGS]
