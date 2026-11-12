"""Auto-generate ONE cover image for a Library story with the configured provider.

Called from `POST /api/images/library/generate-cover` right after the frontend
saves a story into the localStorage Library, so the bookshelf card shows art
instead of the gradient placeholder. Mirrors `services.character_avatar`:
failures are swallowed (return None) so a flaky image provider can never block
or fail the save itself.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

from config import ConfigManager
from services.media._util import COLOR_CLAUSE
from services.character_avatar import _style_anchor_for

logger = logging.getLogger(__name__)

_COVER_SIZE = "768x1024"  # 3:4, matches StoryCard's aspect-[3/4] bookshelf frame
_COVER_FILENAME = "cover.png"

_MAX_SYNOPSIS_CHARS = 400


def _build_cover_prompt(
    title: str, genre: Optional[str], synopsis: Optional[str]
) -> str:
    """Build a single-scene book-cover prompt.

    Reuses the avatar prompt's genre style anchors and its defenses against
    Flow's failure modes — especially text bake-in, which is WORSE for covers:
    "book cover" is a strong tag for title typography in the training data, so
    the model loves to render garbled pseudo-Vietnamese lettering unless
    explicitly negated. The title is still included as content guidance (it
    tells the model what the story is about), bracketed by the no-text cues.
    """
    style_anchor = _style_anchor_for(genre)
    syn = (synopsis or "").strip()[:_MAX_SYNOPSIS_CHARS]
    parts = [
        (
            f"Book cover key-art illustration, one dramatic cohesive scene, "
            f"portrait orientation, {style_anchor}, {COLOR_CLAUSE}, "
            f"rich cinematic lighting, strong silhouette and atmosphere"
        ),
        f"Story title (for theme only, do NOT render it): {title}",
        f"Premise: {syn}" if syn else "",
        (
            "Composition: ONE scene with a single focal character or landmark "
            "moment, clear depth, no collage, no split frames, no panels. "
            "Strictly NO text, NO letters, NO title typography, NO calligraphy, "
            "NO Chinese characters, NO Han characters, NO captions, "
            "NO watermark, NO logo, NO borders, NO frames. "
            "The artwork is in colour: NOT monochrome, NOT grayscale, "
            "NOT black-and-white, NOT uncolored lineart."
        ),
    ]
    return ". ".join(p for p in parts if p)


async def generate_story_cover(
    title: str,
    *,
    genre: Optional[str] = None,
    synopsis: Optional[str] = None,
    story_id: Optional[str] = None,
) -> Optional[str]:
    """Generate one cover. Returns `/media/...` URL or None.

    Silently returns None when the feature flag is off, no image provider is
    configured, or the provider call fails — the bookshelf card then keeps its
    gradient placeholder. Covers are an automatic side feature, so a missing
    provider is logged rather than raised. ``story_id`` (the localStorage id)
    scopes the output folder so two stories with the same title don't share a
    cover.
    """
    if not (title and title.strip()):
        logger.info("cover skip: empty story title")
        return None

    cfg = ConfigManager().pipeline
    if not getattr(cfg, "cover_image_enabled", True):
        logger.info("cover skip: cover_image_enabled=false (title=%s)", title)
        return None
    provider = (cfg.image_provider or "none").strip()
    if provider == "none":
        logger.info("cover skip: no image provider configured (title=%s)", title)
        return None

    from services import output_paths
    from services.media.image_generator import ImageGenerator

    base_dir = output_paths.images_dir(title, story_id=story_id)
    os.makedirs(base_dir, exist_ok=True)

    prompt = _build_cover_prompt(title, genre, synopsis)
    gen = ImageGenerator(provider=provider)
    gen.output_dir = base_dir
    try:
        # ImageGenerator is synchronous (requests); keep it off the event loop.
        path = await asyncio.to_thread(
            gen.generate, prompt, _COVER_FILENAME, _COVER_SIZE
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("cover generation failed for %s: %s", title, exc)
        return None
    if not path:
        logger.warning(
            "cover generation returned no image for %s (provider=%s)", title, provider
        )
        return None
    url = output_paths.media_url(path)
    # Cache-buster so a regenerated cover reloads in the browser while an
    # unchanged one keeps a stable URL (mirrors avatar_url_for).
    try:
        url = f"{url}?v={int(os.path.getmtime(path))}"
    except OSError:
        pass
    return url


__all__ = ["generate_story_cover"]
