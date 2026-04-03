"""Shared text utility functions."""


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
