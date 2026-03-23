"""HTML story exporter — generates beautiful standalone reader pages.

Self-contained HTML with inline CSS/JS: Vietnamese typography, chapter navigation,
dark/light mode toggle, character cards, responsive mobile layout.
"""

import html
import logging
import os
import re
from typing import Optional, Union

from models.schemas import StoryDraft, EnhancedStory, Character

logger = logging.getLogger(__name__)


def _md_to_html(text: str) -> str:
    """Convert basic markdown-like formatting to HTML.

    Handles: **bold**, *italic*, --- (hr), line breaks.
    All text is pre-escaped before conversion.
    """
    escaped = html.escape(text)
    # Bold
    escaped = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', escaped)
    # Italic
    escaped = re.sub(r'\*(.+?)\*', r'<em>\1</em>', escaped)
    # Horizontal rule
    escaped = re.sub(r'^---+$', '<hr>', escaped, flags=re.MULTILINE)
    # Paragraphs (double newline)
    paragraphs = re.split(r'\n\n+', escaped)
    result = []
    for p in paragraphs:
        p = p.strip()
        if p and p != '<hr>':
            result.append(f'<p>{p.replace(chr(10), "<br>")}</p>')
        elif p == '<hr>':
            result.append('<hr>')
    return '\n'.join(result)


def _build_chapter_nav(chapters: list) -> str:
    """Generate chapter navigation HTML."""
    items = []
    for ch in chapters:
        title = html.escape(ch.title)
        items.append(
            f'<a href="#ch-{ch.chapter_number}" class="nav-item">'
            f'Ch.{ch.chapter_number}: {title}</a>'
        )
    return '\n'.join(items)


def _build_character_cards(characters: list[Character]) -> str:
    """Generate character info cards HTML."""
    if not characters:
        return ''
    cards = []
    for c in characters:
        name = html.escape(c.name)
        role = html.escape(c.role) if c.role else ''
        personality = html.escape(c.personality) if c.personality else ''
        motivation = html.escape(c.motivation) if c.motivation else ''

        card = f'''<div class="char-card">
<h4>{name}</h4>
{f'<p class="char-role">{role}</p>' if role else ''}
{f'<p><strong>Tinh cach:</strong> {personality}</p>' if personality else ''}
{f'<p><strong>Dong luc:</strong> {motivation}</p>' if motivation else ''}
</div>'''
        cards.append(card)
    return f'''<section class="characters" id="characters">
<h2>Nhan vat</h2>
<div class="char-grid">{"".join(cards)}</div>
</section>'''


def _build_chapters_html(chapters: list) -> str:
    """Generate chapter content HTML."""
    sections = []
    for ch in chapters:
        title = html.escape(ch.title)
        content = _md_to_html(ch.content) if ch.content else '<p><em>Chua co noi dung.</em></p>'
        sections.append(
            f'<article id="ch-{ch.chapter_number}" class="chapter">\n'
            f'<h2>Chuong {ch.chapter_number}: {title}</h2>\n'
            f'{content}\n'
            f'</article>'
        )
    return '\n'.join(sections)


# Self-contained HTML template — all CSS/JS inlined
HTML_TEMPLATE = '''<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
:root {{
  --bg: #faf8f5; --text: #2d2d2d; --accent: #8b5e3c;
  --card-bg: #fff; --border: #e5e0d8; --nav-bg: #f5f0ea;
  --shadow: rgba(0,0,0,0.08);
}}
[data-theme="dark"] {{
  --bg: #1a1a2e; --text: #e0e0e0; --accent: #c9a96e;
  --card-bg: #222240; --border: #333355; --nav-bg: #16162a;
  --shadow: rgba(0,0,0,0.3);
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
  font-family: 'Segoe UI', 'SF Pro Text', -apple-system, BlinkMacSystemFont, sans-serif;
  background: var(--bg); color: var(--text);
  line-height: 1.8; font-size: 18px;
  transition: background 0.3s, color 0.3s;
}}
.container {{ max-width: 720px; margin: 0 auto; padding: 20px; }}
header {{ text-align: center; padding: 40px 20px; border-bottom: 2px solid var(--border); margin-bottom: 30px; }}
header h1 {{ font-size: 2em; color: var(--accent); margin-bottom: 10px; }}
header .meta {{ font-size: 14px; opacity: 0.7; }}
header .meta span {{ margin: 0 8px; }}
.badge {{ display: inline-block; padding: 2px 10px; border-radius: 12px;
  font-size: 13px; font-weight: 600; background: var(--accent); color: #fff; }}
.synopsis {{ font-style: italic; margin-top: 15px; max-width: 600px; margin-left: auto; margin-right: auto; }}

/* Nav */
.nav-sidebar {{ position: fixed; left: 0; top: 0; width: 260px; height: 100vh;
  background: var(--nav-bg); border-right: 1px solid var(--border);
  overflow-y: auto; padding: 20px 0; transform: translateX(-100%);
  transition: transform 0.3s; z-index: 100; }}
.nav-sidebar.open {{ transform: translateX(0); }}
.nav-item {{ display: block; padding: 8px 20px; color: var(--text); text-decoration: none;
  font-size: 14px; border-bottom: 1px solid var(--border); }}
.nav-item:hover {{ background: var(--accent); color: #fff; }}
.nav-toggle {{ position: fixed; left: 15px; top: 15px; z-index: 101;
  background: var(--card-bg); border: 1px solid var(--border); border-radius: 8px;
  padding: 8px 12px; cursor: pointer; font-size: 16px; }}
.theme-toggle {{ position: fixed; right: 15px; top: 15px; z-index: 101;
  background: var(--card-bg); border: 1px solid var(--border); border-radius: 8px;
  padding: 8px 12px; cursor: pointer; font-size: 16px; }}

/* Characters */
.characters {{ margin-bottom: 30px; }}
.characters h2 {{ color: var(--accent); margin-bottom: 15px; }}
.char-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 15px; }}
.char-card {{ background: var(--card-bg); border: 1px solid var(--border);
  border-radius: 8px; padding: 15px; box-shadow: 0 2px 8px var(--shadow); }}
.char-card h4 {{ color: var(--accent); margin-bottom: 5px; }}
.char-role {{ font-size: 13px; opacity: 0.7; margin-bottom: 5px; }}
.char-card p {{ font-size: 14px; margin-bottom: 5px; }}

/* Chapters */
.chapter {{ margin-bottom: 50px; padding-bottom: 30px; border-bottom: 1px solid var(--border); }}
.chapter h2 {{ color: var(--accent); margin-bottom: 20px; font-size: 1.4em; }}
.chapter p {{ margin-bottom: 1em; text-align: justify; }}
.chapter hr {{ border: none; border-top: 1px solid var(--border); margin: 20px 0; }}

/* Back to top */
.back-top {{ position: fixed; right: 15px; bottom: 15px; background: var(--accent);
  color: #fff; border: none; border-radius: 50%; width: 40px; height: 40px;
  cursor: pointer; font-size: 18px; display: none; z-index: 50; }}

footer {{ text-align: center; padding: 30px; font-size: 13px; opacity: 0.5; }}

@media (max-width: 768px) {{
  body {{ font-size: 16px; }}
  .container {{ padding: 15px; }}
  header h1 {{ font-size: 1.5em; }}
  .char-grid {{ grid-template-columns: 1fr; }}
}}
</style>
</head>
<body>
<button class="nav-toggle" onclick="toggleNav()">&#9776;</button>
<button class="theme-toggle" onclick="toggleTheme()">&#9790;</button>
<nav class="nav-sidebar" id="navSidebar">
<div style="padding:15px 20px;font-weight:bold;color:var(--accent)">{title_escaped}</div>
{chapter_nav}
</nav>
<div class="container">
<header>
<h1>{title_escaped}</h1>
<div class="meta">
<span class="badge">{genre_escaped}</span>
{drama_badge}
</div>
{synopsis_html}
</header>
{characters_html}
{chapters_html}
</div>
<button class="back-top" id="backTop" onclick="window.scrollTo({{top:0,behavior:'smooth'}})">&uarr;</button>
<footer>Tao boi StoryForge</footer>
<script>
function toggleNav(){{var n=document.getElementById('navSidebar');n.classList.toggle('open')}}
function toggleTheme(){{var d=document.documentElement;
d.setAttribute('data-theme',d.getAttribute('data-theme')==='dark'?'':'dark');
try{{localStorage.setItem('sf-theme',d.getAttribute('data-theme')||'')}}catch(e){{}}}}
try{{var t=localStorage.getItem('sf-theme');if(t)document.documentElement.setAttribute('data-theme',t)}}catch(e){{}}
document.querySelectorAll('.nav-item').forEach(function(a){{a.addEventListener('click',function(){{
document.getElementById('navSidebar').classList.remove('open')}});}});
window.addEventListener('scroll',function(){{
document.getElementById('backTop').style.display=window.scrollY>300?'block':'none'}});
</script>
</body>
</html>'''


class HTMLExporter:
    """Generates self-contained HTML story reader pages."""

    @staticmethod
    def export(
        story: Union[StoryDraft, EnhancedStory],
        output_path: str,
        characters: Optional[list[Character]] = None,
    ) -> str:
        """Export story as beautiful standalone HTML file.

        Args:
            story: StoryDraft or EnhancedStory to render
            output_path: Where to save the HTML file
            characters: Optional character list for cards section

        Returns:
            Path to generated HTML file
        """
        title = story.title
        genre = story.genre if story.genre else ''
        synopsis = story.synopsis if hasattr(story, 'synopsis') and story.synopsis else ''

        # Drama badge for enhanced stories
        drama_badge = ''
        if isinstance(story, EnhancedStory) and story.drama_score > 0:
            score_str = html.escape(f"{story.drama_score:.1f}")
            drama_badge = f'<span class="badge">Kich tinh: {score_str}/1.0</span>'

        # Synopsis
        synopsis_html = ''
        if synopsis:
            synopsis_html = f'<p class="synopsis">{html.escape(synopsis)}</p>'

        # Characters
        chars = characters or []
        if not chars and hasattr(story, 'characters'):
            chars = story.characters

        # All template variables MUST be pre-escaped before interpolation.
        # HTML_TEMPLATE uses f-string-style {var} placeholders with no auto-escaping.
        title_escaped = html.escape(title)
        rendered = HTML_TEMPLATE.format(
            title=title_escaped,
            title_escaped=title_escaped,
            genre_escaped=html.escape(genre),
            drama_badge=drama_badge,
            synopsis_html=synopsis_html,
            characters_html=_build_character_cards(chars),
            chapter_nav=_build_chapter_nav(story.chapters),
            chapters_html=_build_chapters_html(story.chapters),
        )

        os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(rendered)

        logger.info(f"HTML exported to {output_path}")
        return output_path
