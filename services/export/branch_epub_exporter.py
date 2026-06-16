"""Export branch tree as EPUB with all paths as chapters."""

import html as _html
import logging

from services.export._branch_epub_assets import enumerate_paths, get_css

logger = logging.getLogger(__name__)


def _html_escape(text) -> str:
    """Safely escape text for HTML insertion."""
    return _html.escape(str(text)) if text else ""


class BranchEPUBExporter:
    """Export branch tree as EPUB 3.0 with all paths navigable."""

    @staticmethod
    def export(
        tree_data: dict,
        output_path: str,
        title: str = "Interactive Story",
        author: str = "StoryForge AI",
        language: str = "en",
    ) -> str:
        """Export branch tree to EPUB with all paths.

        Args:
            tree_data: Tree structure from BranchManager.get_tree()
            output_path: Path to save EPUB file
            title: Book title
            author: Author name
            language: Language code

        Returns:
            Path to generated file, or empty string on failure
        """
        try:
            from ebooklib import epub
        except ImportError:
            logger.error("ebooklib not installed. Run: pip install ebooklib")
            return ""

        nodes = tree_data.get("nodes", {})
        root_id = tree_data.get("root")
        if not root_id or not nodes:
            logger.error("Invalid tree data: missing root or nodes")
            return ""

        book = epub.EpubBook()

        # Metadata
        book.set_identifier(f"storyforge-branch-{title[:30]}")
        book.set_title(title)
        book.set_language(language)
        book.add_author(author)
        book.add_metadata("DC", "subject", "Interactive Fiction")

        # CSS
        style = epub.EpubItem(
            uid="style",
            file_name="style/default.css",
            media_type="text/css",
            content=get_css().encode("utf-8"),
        )
        book.add_item(style)

        # Generate all paths from root
        all_paths = enumerate_paths(root_id, nodes)
        chapters_epub = []
        spine = ["nav"]

        # Cover page
        cover_html = f"""<html><body>
<div style="text-align:center;margin-top:40%;font-family:serif;">
<h1 style="font-size:2.5em;color:#333;">{_html_escape(title)}</h1>
<p style="font-size:1.2em;color:#666;margin-top:1em;">Interactive Branch Story</p>
<hr style="width:30%;margin:2em auto;border-color:#999;">
<p style="color:#888;">{_html_escape(author)}</p>
<p style="color:#aaa;font-size:0.9em;">{len(all_paths)} unique paths</p>
</div></body></html>"""
        cover_page = epub.EpubHtml(
            title="Cover", file_name="cover.xhtml", lang=language
        )
        cover_page.content = cover_html.encode("utf-8")
        cover_page.add_item(style)
        book.add_item(cover_page)
        spine.append(cover_page)

        # Table of contents for paths
        toc_entries = []

        # Generate chapter for each path
        for i, path in enumerate(all_paths):
            path_title = f"Path {i + 1}"
            if path:
                # Use first choice as path name
                first_choice = path[0].get("choice_made", "")
                if first_choice:
                    path_title = f"Path: {first_choice[:40]}"

            # Build chapter content
            content_parts = []
            for j, node_info in enumerate(path):
                node = nodes.get(node_info["node_id"])
                if not node:
                    continue

                text = node.get("text", "")
                choice_made = node_info.get("choice_made", "")

                if choice_made:
                    content_parts.append(
                        f'<div class="choice-made">'
                        f"<em>Choice: {_html_escape(choice_made)}</em></div>"
                    )
                content_parts.append(
                    f'<div class="story-section">{_html_escape(text)}</div>'
                )

                # Show available choices at end of path
                if j == len(path) - 1:
                    choices = node.get("choices", [])
                    if choices:
                        content_parts.append(
                            '<div class="choices"><p><strong>Available choices:</strong></p><ul>'
                        )
                        for choice in choices:
                            content_parts.append(f"<li>{_html_escape(choice)}</li>")
                        content_parts.append("</ul></div>")

            chapter_html = f"""<html><body>
<h1 class="chapter-title">{_html_escape(path_title)}</h1>
<p class="path-info">Depth: {len(path)} nodes</p>
{"".join(content_parts)}
</body></html>"""

            chapter = epub.EpubHtml(
                title=path_title,
                file_name=f"path_{i + 1}.xhtml",
                lang=language,
            )
            chapter.content = chapter_html.encode("utf-8")
            chapter.add_item(style)
            book.add_item(chapter)
            chapters_epub.append(chapter)
            spine.append(chapter)
            toc_entries.append(chapter)

        # Navigation
        book.toc = toc_entries
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())
        book.spine = spine

        # Write file
        try:
            epub.write_epub(output_path, book)
            logger.info(f"Branch EPUB exported: {output_path}")
            return output_path
        except Exception as e:
            logger.error(f"Failed to write EPUB: {e}")
            return ""
