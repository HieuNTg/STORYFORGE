# Shim: re-exports from new location for backward compatibility
from services.export.html_exporter import (
    HTMLExporter,
    _md_to_html,
    _build_chapter_nav,
    _build_character_cards,
    _build_chapters_html,
)

__all__ = [
    "HTMLExporter",
    "_md_to_html",
    "_build_chapter_nav",
    "_build_character_cards",
    "_build_chapters_html",
]
