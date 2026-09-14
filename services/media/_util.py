"""Shared media helpers."""

from __future__ import annotations

import re
import unicodedata

_SLUG_RE = re.compile(r"[^a-zA-Z0-9_-]+")


def slug_session_dir(title: str, session_id: str, max_len: int = 60) -> str:
    """Build a filesystem-safe per-session subdirectory name.

    Format: ``{slug(title)}_{session_id}`` — title is NFKD-normalized (so
    "Tiên Hiệp" → "Tien Hiep"), non-alphanumeric is collapsed to ``_``,
    lowercased, and truncated to ``max_len``. Trailing ``_`` from the title
    slug is preserved so callers always see a clear delimiter before the sid.
    """
    raw = (title or "").strip()
    if raw:
        decomposed = unicodedata.normalize("NFKD", raw)
        ascii_only = "".join(c for c in decomposed if not unicodedata.combining(c))
        base = _SLUG_RE.sub("_", ascii_only).lower()
        if not base or set(base) == {"_"}:
            base = "story"
        else:
            base = base[:max_len]
    else:
        base = "story"
    sid = _SLUG_RE.sub("_", (session_id or "").strip()).strip("_") or "session"
    return f"{base}_{sid}"


# ── Colour steering ──────────────────────────────────────────────────────────
# Comic-panel prompts ("cel shading", "bold ink lines", "manga") sit right on
# top of the monochrome slice of every image model's training data, so a panel
# prompt that never says "colour" comes back as black-and-white lineart often
# enough to be a bug. Every prompt builder states it positively AND negates the
# monochrome failure mode — models weight the two differently, and DALL-E-style
# endpoints drop negative prompts entirely, so the positive clause carries alone
# there.
COLOR_CLAUSE = "full color, rich vibrant color palette, colored artwork"
MONOCHROME_NEGATIVES = (
    "monochrome, grayscale, black and white, desaturated, sepia, "
    "uncolored lineart, sketch"
)
