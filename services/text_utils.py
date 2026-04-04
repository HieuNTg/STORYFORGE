"""Shared text utility functions."""

try:
    import nh3 as _nh3
    _HAS_NH3 = True
except ImportError:
    _nh3 = None  # type: ignore[assignment]
    _HAS_NH3 = False

_ALLOWED_TAGS = {"strong", "em", "br", "p", "h1", "h2", "h3", "h4",
                 "ul", "ol", "li", "a", "code", "pre", "blockquote"}
_ALLOWED_ATTRS = {"a": {"href", "target", "rel"}}


def sanitize_story_html(content: str) -> str:
    """Sanitize HTML content to prevent XSS. Strips all non-allowlisted tags."""
    if not content:
        return ""
    if not _HAS_NH3:
        return content
    return _nh3.clean(content, tags=_ALLOWED_TAGS, attributes=_ALLOWED_ATTRS, link_rel=None)


def excerpt_text(text: str, max_chars: int = 4000, head_ratio: float = 0.67) -> str:
    """Return a head+tail excerpt of text for use in prompts.

    If text fits within max_chars, return it unchanged.
    Otherwise take head_ratio of max_chars from the start and the rest from the end,
    joined by an ellipsis marker so the model knows content was trimmed.

    Args:
        text: Input text to excerpt.
        max_chars: Maximum total characters in the result (default 4000).
        head_ratio: Fraction of max_chars taken from the head (default 0.67 → 67%).
    """
    if len(text) <= max_chars:
        return text
    head = int(max_chars * head_ratio)
    tail = max_chars - head
    return text[:head] + "\n...\n" + text[-tail:]
