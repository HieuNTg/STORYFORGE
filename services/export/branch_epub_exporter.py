"""Export branch tree as EPUB with all paths as chapters."""

import html as _html
import logging

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
            content=BranchEPUBExporter._get_css().encode("utf-8"),
        )
        book.add_item(style)

        # Generate all paths from root
        all_paths = BranchEPUBExporter._enumerate_paths(root_id, nodes)
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
        cover_page = epub.EpubHtml(title="Cover", file_name="cover.xhtml", lang=language)
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
                        f'<em>Choice: {_html_escape(choice_made)}</em></div>'
                    )
                content_parts.append(
                    f'<div class="story-section">{_html_escape(text)}</div>'
                )

                # Show available choices at end of path
                if j == len(path) - 1:
                    choices = node.get("choices", [])
                    if choices:
                        content_parts.append('<div class="choices"><p><strong>Available choices:</strong></p><ul>')
                        for choice in choices:
                            content_parts.append(f'<li>{_html_escape(choice)}</li>')
                        content_parts.append('</ul></div>')

            chapter_html = f"""<html><body>
<h1 class="chapter-title">{_html_escape(path_title)}</h1>
<p class="path-info">Depth: {len(path)} nodes</p>
{''.join(content_parts)}
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

    @staticmethod
    def _enumerate_paths(root_id: str, nodes: dict) -> list[list[dict]]:
        """Enumerate all unique paths from root to leaves."""
        paths = []

        def dfs(node_id: str, current_path: list[dict], choice_made: str = ""):
            node = nodes.get(node_id)
            if not node:
                return

            current_path.append({
                "node_id": node_id,
                "choice_made": choice_made,
            })

            children = node.get("children", {})
            if not children:
                # Leaf node - save this path
                paths.append(list(current_path))
            else:
                # Continue to children
                choices = node.get("choices", [])
                for child_key, child_id in children.items():
                    try:
                        choice_idx = int(child_key)
                        choice_text = choices[choice_idx] if choice_idx < len(choices) else ""
                    except (ValueError, IndexError):
                        choice_text = child_key
                    dfs(child_id, current_path, choice_text)

            current_path.pop()

        dfs(root_id, [])
        return paths

    @staticmethod
    def _get_css() -> str:
        return """
body {
    font-family: Georgia, serif;
    line-height: 1.8;
    margin: 1em;
    color: #333;
}
h1.chapter-title {
    font-size: 1.8em;
    color: #222;
    border-bottom: 2px solid #ccc;
    padding-bottom: 0.3em;
    margin-bottom: 1em;
}
.path-info {
    color: #666;
    font-style: italic;
    margin-bottom: 1.5em;
}
.story-section {
    margin: 1em 0;
    text-align: justify;
}
.choice-made {
    background: #f5f5f5;
    padding: 0.5em 1em;
    border-left: 3px solid #4a90d9;
    margin: 1em 0;
    color: #555;
}
.choices {
    background: #fffaed;
    padding: 1em;
    border: 1px solid #e0d5c0;
    margin-top: 2em;
}
.choices ul {
    margin: 0.5em 0;
    padding-left: 1.5em;
}
.choices li {
    margin: 0.3em 0;
}
"""
