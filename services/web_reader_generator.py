"""Web story reader — enhanced HTML reader with progress tracking and bookmarks."""
import html as _html
import logging
import re
from typing import Union, Optional
from models.schemas import StoryDraft, EnhancedStory

logger = logging.getLogger(__name__)

READER_WPM = 200  # Vietnamese reading speed
MAX_WORDS = 200_000  # ~200K words safety limit for browser rendering


class WebReaderGenerator:
    """Generate enhanced web reader HTML with progress tracking and bookmarks."""

    @staticmethod
    def generate(
        story: Union[StoryDraft, EnhancedStory],
        characters: Optional[list] = None,
    ) -> str:
        """Generate full HTML reader string with all features."""
        title = _html.escape(story.title)
        genre = _html.escape(story.genre) if hasattr(story, "genre") and story.genre else ""
        chapters = story.chapters
        if not chapters:
            return f"<html><body><h1>{title}</h1><p>Chưa có nội dung.</p></body></html>"

        # Truncate chapters if story exceeds word limit (prevents browser crash)
        total_words = sum(len(ch.content.split()) for ch in chapters)
        truncation_info = None  # (total_words, original_count, kept_count)
        if total_words > MAX_WORDS:
            logger.warning(f"Story too large for web reader ({total_words} words), truncating to {MAX_WORDS} words")
            original_count = len(chapters)
            running_total = 0
            truncated_chapters = []
            for ch in chapters:
                ch_words = len(ch.content.split())
                if running_total + ch_words > MAX_WORDS:
                    break
                truncated_chapters.append(ch)
                running_total += ch_words
            chapters = truncated_chapters
            truncation_info = (total_words, original_count, len(chapters))

        # Build chapter data for JS
        chapter_data = []
        for ch in chapters:
            words = len(ch.content.split())
            reading_min = max(1, words // READER_WPM)
            content_html = WebReaderGenerator._content_to_html(ch.content)
            chapter_data.append({
                "number": ch.chapter_number,
                "title": _html.escape(ch.title),
                "words": words,
                "reading_min": reading_min,
                "content": content_html,
            })

        # Character cards
        char_html = ""
        if characters:
            cards = []
            for c in characters:
                cards.append(
                    f'<div class="char-card">'
                    f'<strong>{_html.escape(c.name)}</strong> '
                    f'<span class="role">({_html.escape(c.role)})</span>'
                    f'<p>{_html.escape(c.personality)}</p>'
                    f'</div>'
                )
            char_html = f'<div class="char-grid">{"".join(cards)}</div>'

        return WebReaderGenerator._render_template(title, genre, chapter_data, char_html, truncation_info)

    @staticmethod
    def _content_to_html(content: str) -> str:
        """Convert chapter content to HTML paragraphs."""
        escaped = _html.escape(content)
        escaped = escaped.replace("</", "&lt;/")  # prevent script injection
        # Bold/italic
        escaped = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', escaped)
        escaped = re.sub(r'\*(.+?)\*', r'<em>\1</em>', escaped)
        paragraphs = [f"<p>{p.strip()}</p>" for p in escaped.split("\n") if p.strip()]
        return "\n".join(paragraphs)

    @staticmethod
    def _render_template(
        title: str,
        genre: str,
        chapters: list,
        char_html: str,
        truncation_info: Optional[tuple] = None,
    ) -> str:
        """Render the full reader HTML with embedded JS."""
        # Build chapter list for sidebar
        ch_nav_items = "\n".join(
            f'<div class="ch-nav-item" data-ch="{ch["number"]}">'
            f'<span class="ch-num">Ch.{ch["number"]}</span> {ch["title"]}'
            f'<span class="ch-time">{ch["reading_min"]} phút</span>'
            f'<div class="ch-progress-bar"><div class="ch-progress-fill" id="progress-{ch["number"]}"></div></div>'
            f'</div>'
            for ch in chapters
        )

        # Build chapter content divs
        ch_content_divs = "\n".join(
            f'<div class="chapter-content" id="chapter-{ch["number"]}" style="display:none">'
            f'<h2>Chương {ch["number"]}: {ch["title"]}</h2>'
            f'<div class="reading-meta">{ch["words"]:,} từ · ~{ch["reading_min"]} phút đọc</div>'
            f'{ch["content"]}'
            f'</div>'
            for ch in chapters
        )

        total_words = sum(ch["words"] for ch in chapters)
        total_time = max(1, total_words // READER_WPM)
        n_chapters = len(chapters)

        # Truncation warning banner (shown when story was silently cut)
        if truncation_info:
            tw, orig, kept = truncation_info
            truncation_banner = (
                f'<div style="background:#f59e0b;color:#000;padding:12px 20px;'
                f'border-radius:8px;margin:15px 0;text-align:center;font-weight:600">'
                f'&#9888;&#65039; Truy&#7879;n qu&aacute; d&agrave;i ({tw:,} t&#7915;). '
                f'Ch&#7881; hi&#7875;n th&#7883; {kept} / {orig} ch&#432;&#417;ng '
                f'({MAX_WORDS:,} t&#7915; t&#7889;i &#273;a).'
                f'</div>'
            )
        else:
            truncation_banner = ""

        # Escape title for JS (avoid breaking JS string literals and script injection)
        title_js = title.replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"').replace("</", "<\\/")

        return f'''<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
:root {{ --bg:#faf8f5; --text:#2d2d2d; --accent:#6366f1; --card:#fff; --border:#e5e0d8; --sidebar:#f8f7f4; }}
[data-theme="dark"] {{ --bg:#0f172a; --text:#e2e8f0; --accent:#818cf8; --card:#1e293b; --border:#334155; --sidebar:#1e293b; }}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family:'Segoe UI',system-ui,sans-serif; background:var(--bg); color:var(--text); line-height:1.9; font-size:18px; }}

/* Layout */
.reader-container {{ display:flex; min-height:100vh; }}
.sidebar {{ width:280px; background:var(--sidebar); border-right:1px solid var(--border); position:fixed; height:100vh; overflow-y:auto; transition:transform .3s; z-index:100; }}
.main-content {{ margin-left:280px; flex:1; max-width:750px; padding:40px 30px; margin-right:auto; }}

/* Header */
.reader-header {{ text-align:center; padding:30px 0; border-bottom:2px solid var(--border); margin-bottom:30px; }}
.reader-header h1 {{ font-size:1.8em; color:var(--accent); }}
.reader-header .meta {{ font-size:14px; opacity:.7; margin-top:8px; }}
.badge {{ background:var(--accent); color:#fff; padding:2px 12px; border-radius:12px; font-size:12px; font-weight:600; }}

/* Sidebar */
.sidebar-header {{ padding:20px; border-bottom:1px solid var(--border); }}
.sidebar-header h3 {{ color:var(--accent); font-size:14px; }}
.ch-nav-item {{ padding:10px 20px; cursor:pointer; border-bottom:1px solid var(--border); font-size:14px; position:relative; }}
.ch-nav-item:hover {{ background:var(--accent); color:#fff; }}
.ch-nav-item.active {{ background:var(--accent); color:#fff; font-weight:600; }}
.ch-num {{ font-weight:600; margin-right:4px; }}
.ch-time {{ display:block; font-size:11px; opacity:.6; margin-top:2px; }}
.ch-progress-bar {{ height:3px; background:var(--border); border-radius:2px; margin-top:4px; }}
.ch-progress-fill {{ height:100%; background:#22c55e; border-radius:2px; width:0%; transition:width .3s; }}

/* Content */
.chapter-content h2 {{ color:var(--accent); margin-bottom:10px; font-size:1.4em; }}
.reading-meta {{ font-size:13px; opacity:.6; margin-bottom:20px; padding-bottom:10px; border-bottom:1px solid var(--border); }}
.chapter-content p {{ margin-bottom:1em; text-align:justify; }}

/* Characters */
.char-grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(200px,1fr)); gap:10px; margin:20px 0; }}
.char-card {{ background:var(--card); border:1px solid var(--border); border-radius:8px; padding:12px; }}
.char-card .role {{ color:var(--accent); font-size:13px; }}

/* Controls */
.controls {{ position:fixed; bottom:20px; right:20px; display:flex; gap:8px; z-index:50; }}
.controls button {{ background:var(--card); border:1px solid var(--border); border-radius:8px; padding:8px 14px; cursor:pointer; font-size:14px; color:var(--text); }}
.controls button:hover {{ background:var(--accent); color:#fff; }}
.reading-progress {{ position:fixed; top:0; left:0; width:100%; height:3px; z-index:200; background:var(--border); }}
.reading-progress-fill {{ height:100%; background:var(--accent); width:0%; transition:width .1s; }}

/* Bookmark indicator */
.bookmark-icon {{ cursor:pointer; font-size:18px; }}
.bookmark-icon.saved {{ color:#f59e0b; }}

/* Mobile */
.menu-toggle {{ display:none; position:fixed; left:10px; top:10px; z-index:150; background:var(--card); border:1px solid var(--border); border-radius:8px; padding:8px 12px; cursor:pointer; }}
@media (max-width:768px) {{
  .sidebar {{ transform:translateX(-100%); }}
  .sidebar.open {{ transform:translateX(0); }}
  .main-content {{ margin-left:0; padding:20px 15px; }}
  .menu-toggle {{ display:block; }}
  body {{ font-size:16px; }}
}}
</style>
</head>
<body>
<div class="reading-progress"><div class="reading-progress-fill" id="readingProgress"></div></div>
<button class="menu-toggle" onclick="document.querySelector('.sidebar').classList.toggle('open')">&#9776;</button>

<div class="reader-container">
  <div class="sidebar">
    <div class="sidebar-header">
      <h3>{title}</h3>
      <span class="badge">{genre}</span>
      <div style="font-size:12px;margin-top:8px;opacity:.6">{total_words:,} từ · ~{total_time} phút</div>
    </div>
    {ch_nav_items}
    <div class="sidebar-header" style="border-top:1px solid var(--border)">
      <h3>&#128209; Bookmarks</h3>
    </div>
    <div id="bookmarkList" style="padding:10px 20px;font-size:13px;opacity:.7">
      Ch&#432;a c&oacute; bookmark
    </div>
  </div>

  <div class="main-content">
    <div class="reader-header">
      <h1>{title}</h1>
      <div class="meta"><span class="badge">{genre}</span> · {n_chapters} chương · {total_words:,} từ</div>
    </div>
    {truncation_banner}
    {char_html}

    <div id="chapterContainer">
      {ch_content_divs}
    </div>

    <div style="display:flex;justify-content:space-between;margin-top:30px;padding-top:20px;border-top:1px solid var(--border)">
      <button onclick="prevChapter()" id="prevBtn" style="padding:8px 20px;border-radius:8px;border:1px solid var(--border);cursor:pointer;background:var(--card);color:var(--text)">&#8592; Chương trước</button>
      <span class="bookmark-icon" id="bookmarkBtn" onclick="toggleBookmark()" title="Đánh dấu">&#9734;</span>
      <button onclick="nextChapter()" id="nextBtn" style="padding:8px 20px;border-radius:8px;border:1px solid var(--border);cursor:pointer;background:var(--card);color:var(--text)">Chương sau &#8594;</button>
    </div>
  </div>
</div>

<div class="controls">
  <button onclick="toggleTheme()" title="Đổi theme">&#127763;</button>
  <button onclick="changeFontSize(1)" title="Tăng cỡ chữ">A+</button>
  <button onclick="changeFontSize(-1)" title="Giảm cỡ chữ">A-</button>
</div>

<script>
const STORY_KEY = 'sf-reader-' + btoa(unescape(encodeURIComponent('{title_js}'.substring(0,20))));
let currentChapter = 1;
const totalChapters = {n_chapters};
let fontSize = 18;

function showChapter(n) {{
  document.querySelectorAll('.chapter-content').forEach(el => el.style.display = 'none');
  const el = document.getElementById('chapter-' + n);
  if (el) {{ el.style.display = 'block'; currentChapter = n; }}
  document.querySelectorAll('.ch-nav-item').forEach(item => {{
    item.classList.toggle('active', parseInt(item.dataset.ch) === n);
  }});
  document.getElementById('prevBtn').disabled = (n <= 1);
  document.getElementById('nextBtn').disabled = (n >= totalChapters);
  window.scrollTo({{top: 0, behavior: 'smooth'}});
  saveProgress();
  updateBookmarkIcon();
  document.querySelector('.sidebar').classList.remove('open');
}}

function prevChapter() {{ if (currentChapter > 1) showChapter(currentChapter - 1); }}
function nextChapter() {{ if (currentChapter < totalChapters) showChapter(currentChapter + 1); }}

// Keyboard navigation
document.addEventListener('keydown', function(e) {{
  if (e.key === 'ArrowLeft') prevChapter();
  if (e.key === 'ArrowRight') nextChapter();
}});

// Reading progress (scroll-based)
window.addEventListener('scroll', function() {{
  const scrollTop = window.scrollY;
  const docHeight = document.documentElement.scrollHeight - window.innerHeight;
  const progress = docHeight > 0 ? (scrollTop / docHeight) * 100 : 0;
  document.getElementById('readingProgress').style.width = progress + '%';
  const fill = document.getElementById('progress-' + currentChapter);
  if (fill) fill.style.width = Math.min(100, progress) + '%';
}});

// Nav click handlers
document.querySelectorAll('.ch-nav-item').forEach(item => {{
  item.addEventListener('click', function() {{ showChapter(parseInt(this.dataset.ch)); }});
}});

// Theme toggle
function toggleTheme() {{
  const d = document.documentElement;
  const newTheme = d.getAttribute('data-theme') === 'dark' ? '' : 'dark';
  d.setAttribute('data-theme', newTheme);
  try {{ localStorage.setItem(STORY_KEY + '-theme', newTheme); }} catch(e) {{}}
}}

// Font size
function changeFontSize(delta) {{
  fontSize = Math.max(14, Math.min(24, fontSize + delta));
  document.querySelector('.main-content').style.fontSize = fontSize + 'px';
}}

// Bookmark
function toggleBookmark() {{
  try {{
    const bookmarks = JSON.parse(localStorage.getItem(STORY_KEY + '-bookmarks') || '[]');
    const idx = bookmarks.indexOf(currentChapter);
    if (idx >= 0) bookmarks.splice(idx, 1);
    else bookmarks.push(currentChapter);
    localStorage.setItem(STORY_KEY + '-bookmarks', JSON.stringify(bookmarks));
    updateBookmarkIcon();
    renderBookmarkList();
  }} catch(e) {{}}
}}

function updateBookmarkIcon() {{
  try {{
    const bookmarks = JSON.parse(localStorage.getItem(STORY_KEY + '-bookmarks') || '[]');
    const btn = document.getElementById('bookmarkBtn');
    btn.textContent = bookmarks.includes(currentChapter) ? '\u2605' : '\u2606';
    btn.classList.toggle('saved', bookmarks.includes(currentChapter));
  }} catch(e) {{}}
}}

function renderBookmarkList() {{
  try {{
    const bookmarks = JSON.parse(localStorage.getItem(STORY_KEY + '-bookmarks') || '[]');
    const container = document.getElementById('bookmarkList');
    if (!bookmarks.length) {{ container.innerHTML = 'Ch\u01b0a c\u00f3 bookmark'; return; }}
    container.innerHTML = bookmarks.sort((a,b) => a-b).map(n =>
      '<div class="ch-nav-item" onclick="showChapter(' + n + ')" style="padding:6px 0;cursor:pointer">' +
      '\u2605 Ch\u01b0\u01a1ng ' + n +
      '</div>'
    ).join('');
  }} catch(e) {{}}
}}

// Save/restore progress
function saveProgress() {{
  try {{ localStorage.setItem(STORY_KEY + '-chapter', currentChapter); }} catch(e) {{}}
}}

function restoreProgress() {{
  try {{
    const theme = localStorage.getItem(STORY_KEY + '-theme');
    if (theme) document.documentElement.setAttribute('data-theme', theme);
    const saved = localStorage.getItem(STORY_KEY + '-chapter');
    if (saved) return parseInt(saved);
  }} catch(e) {{}}
  return 1;
}}

// Init
showChapter(restoreProgress());
renderBookmarkList();
</script>
</body>
</html>'''
