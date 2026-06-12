"""HTML fragment builders for the HTML exporter.

Internal module — import these names via services.export.html_exporter,
which re-exports them as the stable import surface.
"""

import html
import re

from models.schemas import Character


def _md_to_html(text: str) -> str:
    """Convert basic markdown-like formatting to HTML.

    Handles: **bold**, *italic*, --- (hr), line breaks.
    All text is pre-escaped before conversion.
    """
    escaped = html.escape(text)
    # Bold
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    # Italic
    escaped = re.sub(r"\*(.+?)\*", r"<em>\1</em>", escaped)
    # Horizontal rule
    escaped = re.sub(r"^---+$", "<hr>", escaped, flags=re.MULTILINE)
    # Paragraphs (double newline)
    paragraphs = re.split(r"\n\n+", escaped)
    result = []
    for p in paragraphs:
        p = p.strip()
        if p and p != "<hr>":
            result.append(f"<p>{p.replace(chr(10), '<br>')}</p>")
        elif p == "<hr>":
            result.append("<hr>")
    return "\n".join(result)


def _build_chapter_nav(chapters: list) -> str:
    """Generate chapter navigation HTML."""
    items = []
    for ch in chapters:
        title = html.escape(ch.title)
        items.append(
            f'<a href="#ch-{ch.chapter_number}" class="nav-item">'
            f"Ch.{ch.chapter_number}: {title}</a>"
        )
    return "\n".join(items)


def _build_character_cards(characters: list[Character]) -> str:
    """Generate character info cards HTML."""
    if not characters:
        return ""
    cards = []
    for c in characters:
        name = html.escape(c.name)
        role = html.escape(c.role) if c.role else ""
        personality = html.escape(c.personality) if c.personality else ""
        motivation = html.escape(c.motivation) if c.motivation else ""

        card = f"""<div class="char-card">
<h4>{name}</h4>
{f'<p class="char-role">{role}</p>' if role else ""}
{f"<p><strong>Tính cách:</strong> {personality}</p>" if personality else ""}
{f"<p><strong>Động lực:</strong> {motivation}</p>" if motivation else ""}
</div>"""
        cards.append(card)
    return f"""<section class="characters" id="characters">
<h2>Nhân vật</h2>
<div class="char-grid">{"".join(cards)}</div>
</section>"""


def _safe_media_urls(images: list) -> list[str]:
    """Keep only same-origin /media/ URLs (no traversal, no external hosts)."""
    safe = []
    for url in images or []:
        if not isinstance(url, str):
            continue
        url = url.strip()
        if url.startswith("/media/") and ".." not in url:
            safe.append(url)
    return safe


def _build_comic_pages_html(images: list) -> str:
    """Stacked comic pages/panels (webtoon reading order) for one chapter."""
    safe = _safe_media_urls(images)
    if not safe:
        return ""
    imgs = "\n".join(
        f'<img src="{html.escape(url)}" alt="Trang truyện tranh" loading="lazy">'
        for url in safe
    )
    return f'<div class="comic-pages">\n{imgs}\n</div>'


def _build_chapters_html(chapters: list) -> str:
    """Generate chapter content HTML.

    Chapters that carry generated comic pages (`chapter.images`) render them
    stacked in reading order; the prose then collapses into a <details> block
    so the comic IS the chapter and the text stays available as a fallback.
    """
    sections = []
    for ch in chapters:
        title = html.escape(ch.title)
        content = (
            _md_to_html(ch.content)
            if ch.content
            else "<p><em>Chưa có nội dung.</em></p>"
        )
        comic = _build_comic_pages_html(getattr(ch, "images", None))
        if comic:
            body = (
                f"{comic}\n"
                f'<details class="prose-fallback"><summary>Đọc bản chữ</summary>\n'
                f"{content}\n</details>"
            )
        else:
            body = content
        sections.append(
            f'<article id="ch-{ch.chapter_number}" class="chapter">\n'
            f"<h2>Chương {ch.chapter_number}: {title}</h2>\n"
            f"{body}\n"
            f"</article>"
        )
    return "\n".join(sections)
