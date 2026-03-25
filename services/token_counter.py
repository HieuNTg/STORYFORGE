"""Token estimation utility for long-context mode."""


def estimate_tokens(text: str) -> int:
    """Rough estimate: 1 token ~ 3.5 chars for Vietnamese text."""
    if not text:
        return 0
    return int(len(text) / 3.5)


def fits_in_context(texts: list[str], max_tokens: int, reserve: int = 8192) -> bool:
    """Check if concatenated texts fit within max_tokens minus reserve for output."""
    total = sum(estimate_tokens(t) for t in texts)
    return total < (max_tokens - reserve)
