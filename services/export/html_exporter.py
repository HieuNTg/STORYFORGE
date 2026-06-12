"""HTML story exporter — generates beautiful standalone reader pages.

Self-contained HTML with inline CSS/JS: Vietnamese typography, chapter navigation,
dark/light mode toggle, character cards, responsive mobile layout.
"""

import html
import logging
import os
from typing import Optional, Union

from models.schemas import StoryDraft, EnhancedStory, Character

# Stable import surface: consumers (tests, the services.html_exporter alias)
# import these names from this module, not from the internal modules.
from services.export._html_render import (  # noqa: F401
    _build_chapter_nav,
    _build_character_cards,
    _build_chapters_html,
    _build_comic_pages_html,
    _md_to_html,
    _safe_media_urls,
)
from services.export._html_template import HTML_TEMPLATE  # noqa: F401

logger = logging.getLogger(__name__)


class HTMLExporter:
    """Generates self-contained HTML story reader pages."""

    @staticmethod
    def export(
        story: Union[StoryDraft, EnhancedStory],
        output_path: str,
        characters: Optional[list[Character]] = None,
        share_id: Optional[str] = None,
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
        genre = story.genre if story.genre else ""
        synopsis = (
            story.synopsis if hasattr(story, "synopsis") and story.synopsis else ""
        )

        # Drama badge for enhanced stories
        drama_badge = ""
        if isinstance(story, EnhancedStory) and story.drama_score > 0:
            score_str = html.escape(f"{story.drama_score:.1f}")
            drama_badge = f'<span class="badge">Kịch tính: {score_str}/1.0</span>'

        # Synopsis
        synopsis_html = ""
        if synopsis:
            synopsis_html = f'<p class="synopsis">{html.escape(synopsis)}</p>'

        # Characters
        chars = characters or []
        if not chars and hasattr(story, "characters"):
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

        # Inject share metadata if share_id provided
        if share_id:
            from datetime import datetime

            share_meta = (
                f'\n<meta name="storyforge-share" content="{html.escape(share_id)}">'
                f'\n<meta name="storyforge-created" content="{datetime.now().isoformat()}">'
            )
            rendered = rendered.replace("</head>", f"{share_meta}\n</head>", 1)

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(rendered)

        logger.info(f"HTML exported to {output_path}")
        return output_path
