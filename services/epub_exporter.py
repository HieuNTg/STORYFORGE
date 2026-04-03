"""Export story as EPUB with table of contents, character page, and metadata."""
import html as _html
import logging
import os
from typing import Union
from models.schemas import StoryDraft, EnhancedStory, Character

logger = logging.getLogger(__name__)


def _html_escape(text) -> str:
    """Safely escape text for HTML insertion."""
    return _html.escape(str(text)) if text else ""


class EPUBExporter:
    """Export story as EPUB 3.0 with chapter navigation and metadata."""

    @staticmethod
    def export(
        story: Union[StoryDraft, EnhancedStory],
        output_path: str,
        characters: list[Character] = None,
        language: str = "vi",
        author: str = "StoryForge AI",
    ) -> str:
        """Export story to EPUB. Returns path to generated file."""
        try:
            from ebooklib import epub
        except ImportError:
            logger.error("ebooklib not installed. Run: pip install ebooklib")
            return ""

        book = epub.EpubBook()

        # Metadata
        book.set_identifier(f"storyforge-{story.title[:30]}")
        book.set_title(story.title)
        book.set_language(language)
        book.add_author(author)
        if hasattr(story, "genre"):
            book.add_metadata("DC", "subject", story.genre)

        # CSS for Vietnamese typography
        style = epub.EpubItem(
            uid="style",
            file_name="style/default.css",
            media_type="text/css",
            content=EPUBExporter._get_css().encode("utf-8"),
        )
        book.add_item(style)

        chapters_epub = []

        # Cover page (styled HTML, no image dependency)
        cover_html = (
            "<html><body>"
            '<div style="text-align:center;margin-top:40%;font-family:serif;">'
            f'<h1 style="font-size:2.5em;color:#333;">{_html_escape(story.title)}</h1>'
            f'<p style="font-size:1.2em;color:#666;margin-top:1em;">'
            f'{_html_escape(story.genre) if hasattr(story, "genre") else ""}</p>'
            '<hr style="width:30%;margin:2em auto;border-color:#999;">'
            f'<p style="color:#888;">{_html_escape(author)}</p>'
            '<p style="color:#aaa;font-size:0.9em;">Powered by StoryForge</p>'
            "</div></body></html>"
        )
        cover_page = epub.EpubHtml(title="Cover", file_name="cover.xhtml", lang=language)
        cover_page.content = cover_html.encode("utf-8")
        cover_page.add_item(style)
        book.add_item(cover_page)

        spine = ["nav", cover_page]

        # Title page
        title_page = epub.EpubHtml(title="Trang bìa", file_name="title.xhtml", lang=language)
        title_html = f"""<html><body>
<div class="title-page">
<h1>{story.title}</h1>
<p class="genre">Thể loại: {story.genre if hasattr(story, 'genre') else 'N/A'}</p>
<p class="author">Tác giả: {author}</p>
{f'<p class="synopsis">{story.synopsis[:500]}</p>' if hasattr(story, 'synopsis') and story.synopsis else ''}
</div></body></html>"""
        title_page.content = title_html.encode("utf-8")
        title_page.add_item(style)
        book.add_item(title_page)
        spine.append(title_page)

        # Character page (if characters provided)
        if characters:
            char_page = epub.EpubHtml(title="Nhân vật", file_name="characters.xhtml", lang=language)
            char_lines = []
            for c in characters:
                char_lines.append(
                    f'<div class="character">'
                    f'<h3>{c.name} <span class="role">({c.role})</span></h3>'
                    f'<p><strong>Tính cách:</strong> {c.personality}</p>'
                    f'<p><strong>Động lực:</strong> {c.motivation}</p>'
                    f'{"<p><strong>Ngoại hình:</strong> " + c.appearance + "</p>" if c.appearance else ""}'
                    f'</div>'
                )
            char_page.content = f'<html><body><h2>Nhân vật</h2>{"".join(char_lines)}</body></html>'.encode("utf-8")
            char_page.add_item(style)
            book.add_item(char_page)
            chapters_epub.append(char_page)
            spine.append(char_page)

        # Chapters
        for ch in story.chapters:
            epub_ch = epub.EpubHtml(
                title=f"Chương {ch.chapter_number}: {ch.title}",
                file_name=f"chapter_{ch.chapter_number:03d}.xhtml",
                lang=language,
            )
            # Convert content paragraphs to HTML
            paragraphs = [f"<p>{p.strip()}</p>" for p in ch.content.split("\n") if p.strip()]
            content_html = f"""<html><body>
<h2>Chương {ch.chapter_number}: {ch.title}</h2>
{''.join(paragraphs)}
</body></html>"""
            epub_ch.content = content_html.encode("utf-8")
            epub_ch.add_item(style)
            book.add_item(epub_ch)
            chapters_epub.append(epub_ch)
            spine.append(epub_ch)

        # Table of contents
        book.toc = [epub.Link(c.file_name, c.title, c.file_name) for c in chapters_epub]

        # Navigation
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())

        # Spine (reading order)
        book.spine = spine

        # Write file
        out_dir = os.path.dirname(output_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        epub.write_epub(output_path, book)
        logger.info(f"EPUB exported: {output_path}")
        return output_path

    @staticmethod
    def _get_css() -> str:
        """CSS optimized for Vietnamese text readability on e-readers."""
        return """
body { font-family: serif; line-height: 1.8; margin: 1em; }
h1, h2, h3 { font-family: sans-serif; }
h1 { text-align: center; margin-top: 2em; }
h2 { margin-top: 1.5em; border-bottom: 1px solid #ccc; padding-bottom: 0.3em; }
p { text-indent: 1.5em; margin: 0.5em 0; text-align: justify; }
.title-page { text-align: center; margin-top: 30%; }
.title-page h1 { font-size: 2em; }
.genre { color: #666; font-style: italic; }
.author { margin-top: 1em; }
.synopsis { margin-top: 2em; font-style: italic; text-align: justify; max-width: 80%; margin-left: auto; margin-right: auto; }
.character { margin-bottom: 1em; padding: 0.5em; border-left: 3px solid #4a9; }
.role { color: #888; font-size: 0.9em; }
"""
