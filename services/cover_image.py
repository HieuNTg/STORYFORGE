"""Auto-generate ONE cover image for a Library story via FlowKit.

Called from `POST /api/images/library/generate-cover` right after the frontend
saves a story into the localStorage Library, so the bookshelf card shows art
instead of the gradient placeholder. Mirrors `services.character_avatar`:
failures are swallowed (return None) so a flaky image provider can never block
or fail the save itself.
"""

from __future__ import annotations

import hashlib
import logging
import os
from typing import Optional

from config import ConfigManager
from services.character_avatar import _style_anchor_for

logger = logging.getLogger(__name__)

_COVER_ASPECT = "3:4"  # matches StoryCard's aspect-[3/4] bookshelf frame
_COVER_FILENAME = "cover.png"
_SEED_MOD = 2_147_483_647

_MAX_SYNOPSIS_CHARS = 400


def _seed_for(key: str) -> int:
    """Deterministic seed derived from the story identity.

    Re-requesting the cover for the same story should produce the same art —
    a random seed would drift the cover on every retry, which reads as the
    bookshelf "changing its mind" about a book's face.
    """
    digest = hashlib.sha1((key or "untitled").encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % _SEED_MOD


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
            f"portrait orientation, {style_anchor}, rich cinematic lighting, "
            f"strong silhouette and atmosphere"
        ),
        f"Story title (for theme only, do NOT render it): {title}",
        f"Premise: {syn}" if syn else "",
        (
            "Composition: ONE scene with a single focal character or landmark "
            "moment, clear depth, no collage, no split frames, no panels. "
            "Strictly NO text, NO letters, NO title typography, NO calligraphy, "
            "NO Chinese characters, NO Han characters, NO captions, "
            "NO watermark, NO logo, NO borders, NO frames."
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
    """Generate one cover via FlowKit. Returns `/media/...` URL or None.

    Silently returns None when the feature flag is off, FlowKit is disabled,
    project_id is unset, or the upstream call fails — the bookshelf card then
    keeps its gradient placeholder. ``story_id`` (the localStorage id) scopes
    the output folder so two stories with the same title don't share a cover;
    it also seeds generation so retries are idempotent.
    """
    if not (title and title.strip()):
        logger.info("cover skip: empty story title")
        return None

    cfg = ConfigManager().pipeline
    if not getattr(cfg, "cover_image_enabled", True):
        logger.info("cover skip: cover_image_enabled=false (title=%s)", title)
        return None
    if not getattr(cfg, "flowkit_enabled", False):
        logger.info("cover skip: flowkit_enabled=false (title=%s)", title)
        return None
    if not (getattr(cfg, "flowkit_project_id", "") or "").strip():
        logger.info("cover skip: flowkit_project_id empty (title=%s)", title)
        return None

    from services.output_paths import images_dir, media_url

    base_dir = images_dir(title, story_id=story_id)
    os.makedirs(base_dir, exist_ok=True)

    from services.media.flow_service import FlowService

    prompt = _build_cover_prompt(title, genre, synopsis)
    seed = _seed_for(story_id or title)
    # One retry — same rationale as avatars: FlowKit occasionally drops the
    # connection mid-handshake under parallel load and the second attempt
    # almost always succeeds once a worker slot frees up.
    last_exc: Optional[Exception] = None
    for attempt in (1, 2):
        try:
            path = await FlowService().request_image(
                prompt=prompt,
                char_refs=None,
                style_ref=None,
                output_dir=base_dir,
                filename=_COVER_FILENAME,
                aspect_override=_COVER_ASPECT,
                seed_override=seed,
            )
            if not path:
                logger.warning(
                    "cover attempt %d returned empty path for %s", attempt, title
                )
                if attempt == 2:
                    return None
                continue
            url = media_url(path)
            # Cache-buster so a regenerated cover reloads in the browser while
            # an unchanged one keeps a stable URL (mirrors avatar_url_for).
            try:
                url = f"{url}?v={int(os.path.getmtime(path))}"
            except OSError:
                pass
            return url
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            logger.warning("cover attempt %d failed for %s: %s", attempt, title, exc)
    logger.warning("cover generation gave up for %s: %s", title, last_exc)
    return None


__all__ = ["generate_story_cover"]
