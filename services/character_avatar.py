"""Auto-generate a character portrait via FlowKit after extraction.

Called from `POST /api/characters/extract-story`. Failures are swallowed so a
flaky image provider can never break the LLM-extracted character payload.
"""

from __future__ import annotations

import hashlib
import logging
import os
from typing import Optional

from config import ConfigManager
from models.schemas import ForgeCharacter
from services.safe_name import safe_character_name

logger = logging.getLogger(__name__)

_AVATAR_SUBDIR = "avatars"
_AVATAR_ASPECT = (
    "1:1"  # square frame composes cleanly into both portrait & landscape scenes
)
_SEED_MOD = 2_147_483_647

# Genre-specific style anchors. Layered on top of the anime baseline so the
# avatar fits the story's visual world without re-describing the character.
# Vietnamese genre labels (as written in CreateStoryModal.tsx) map to short
# English descriptors the image model understands well. Anything not in this
# map falls back to the generic anime baseline.
_GENRE_STYLE_ANCHORS = {
    "Tiên Hiệp": "xianxia / Chinese cultivation aesthetic, flowing hanfu robes, classical jade accessories, anime art",
    "Huyền Huyễn": "high-fantasy mystical aesthetic, ornate robes with arcane motifs, anime art",
    "Đô Thị": "modern urban aesthetic, contemporary casual or business clothing, anime art",
    "Khoa Huyễn": "near-future sci-fi aesthetic, tech-wear, subtle neon trim, anime art",
    "Lịch Sử": "historical period aesthetic, era-appropriate traditional clothing, anime art",
    "Hiện Đại": "contemporary modern aesthetic, everyday clothing, anime art",
}
_DEFAULT_STYLE_ANCHOR = "anime illustration style"

# Case/whitespace-insensitive view of the anchor dict. The frontend sends
# the genre label exactly as written in CreateStoryModal.tsx but older
# library entries occasionally carry "tiên hiệp" lowercase or with stray
# whitespace; without a normalized lookup those silently fell through to
# the generic anchor and a xianxia character came back in jeans.
_GENRE_STYLE_ANCHORS_CF = {k.casefold(): v for k, v in _GENRE_STYLE_ANCHORS.items()}


def _safe_name(name: str) -> str:
    """Filesystem-safe filename — delegates to the shared utility.

    Kept as a thin wrapper so existing import sites (find_existing_avatar
    callers in other modules) don't need to change. New code should prefer
    importing ``safe_character_name`` directly.
    """
    return safe_character_name(name)


def _seed_for(name: str) -> int:
    """Deterministic seed derived from the character name.

    Re-extracting the same story should produce the same face. A random seed
    per call would mean every re-extract drifts the portrait, breaking visual
    continuity for the user. Hash → int gives a stable 31-bit positive seed.
    """
    digest = hashlib.sha1((name or "unnamed").encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % _SEED_MOD


def _style_anchor_for(genre: Optional[str]) -> str:
    """Map a Vietnamese genre label to a short English style descriptor.

    Falls back to the generic anime baseline for unknown or empty genres
    so the prompt always has some style guidance.
    """
    if not genre or not genre.strip():
        return _DEFAULT_STYLE_ANCHOR
    return _GENRE_STYLE_ANCHORS_CF.get(genre.strip().casefold(), _DEFAULT_STYLE_ANCHOR)


def _build_avatar_prompt(char: ForgeCharacter, genre: Optional[str] = None) -> str:
    """Build a single-portrait prompt that resists Flow's failure modes.

    Two failure modes the prompt explicitly defends against:
      1) Text/calligraphy bake-in — Imagen / Nano Banana renders character
         names, poetry, or environmental signage especially for wuxia/xianxia
         subjects where the training set is saturated with calligraphy
         backgrounds. Negative cues bracket the prompt.
      2) Multi-view "reference sheet" misinterpretation — the literal phrase
         "reference sheet" or even "character reference" is a strong tag in
         the anime/concept-art slice of the training data and the model
         collapses to a 4-view turnaround instead of a single portrait. We
         avoid the word "reference" entirely and explicitly negate the
         turnaround failure mode.

    Genre is injected as a style anchor so a sci-fi character doesn't come
    back wearing hanfu and a xianxia character doesn't come back in jeans.
    The character's literal description still takes precedence — the anchor
    is a soft prior, not a hard override.
    """
    desc = (char.description or "").strip()[:240]
    back = (char.backstory or "").strip()[:160]
    style_anchor = _style_anchor_for(genre)
    parts = [
        (
            f"Single-figure character portrait, one person only, centered, "
            f"eye-level shot, head and upper torso visible, {style_anchor}, "
            f"soft studio lighting on a plain neutral gray background"
        ),
        f"Character: {char.name} ({char.role})",
        desc,
        back,
        (
            "Composition: ONE figure, single composition, single pose. "
            "NOT a turnaround, NOT a model sheet, NOT a character sheet, "
            "NOT multiple views, NOT multi-panel, no separate object inserts, "
            "no split frames. "
            "Strictly NO text, NO letters, NO calligraphy, NO Chinese characters, "
            "NO Han characters, NO captions, NO watermark, NO logo, NO signs. "
            "Background must be empty plain gray studio, no scenery, no buildings."
        ),
    ]
    return ". ".join(p for p in parts if p)


def _avatar_dirs(story_id: Optional[str]) -> tuple[str, str]:
    """Return (scoped_dir, scoped_url_prefix) for a given story_id.

    Scoping prevents collisions when two stories share a character name
    (e.g. two unrelated wuxia stories both have a "Tiểu Vũ"). Under the
    per-story output layout the avatar dir is
    ``output/<story-slug>/images/avatars`` (one slug for everything a story
    owns). When no story_id is provided (legacy callers, ad-hoc Forge UI use
    before a story is saved) we fall back to a global ``avatars`` dir so
    unscoped data keeps working.

    Returns a 2-tuple of:
      - filesystem directory (created on demand)
      - URL path prefix under ``/media/`` (no leading slash), relative to the
        output root that the ``/media`` static mount serves.
    """
    from services.output_paths import OUTPUT_ROOT, avatars_dir, rel_to_output_root

    if story_id:
        fs_dir = avatars_dir(story_id=story_id)
    else:
        fs_dir = os.path.join(OUTPUT_ROOT, _AVATAR_SUBDIR)
    url_prefix = rel_to_output_root(fs_dir)
    return fs_dir, url_prefix


async def generate_character_avatar(
    char: ForgeCharacter,
    story_id: Optional[str] = None,
    genre: Optional[str] = None,
) -> Optional[str]:
    """Generate one portrait via FlowKit. Returns `/media/...` URL or None.

    Silently returns None when FlowKit is disabled, project_id is unset, or
    the upstream call fails. Avatar generation is a nice-to-have layered on
    top of text extraction and must never raise.

    ``story_id`` scopes the output path so two stories with characters of
    the same name don't collide. Defaults to the legacy unscoped location
    when not provided. ``genre`` shapes the prompt's style anchor.
    """
    # Whitespace guard — an all-whitespace name slugs to an empty string and
    # writes ".png" or "_.png" into the avatar dir, then every later character
    # with a blank name collides on it. Bail early instead.
    if not (char.name and char.name.strip()):
        logger.info("avatar skip: empty character name")
        return None

    cfg = ConfigManager().pipeline
    if not getattr(cfg, "flowkit_enabled", False):
        # Surface why no avatars ever appear in dev — silent return was making
        # it look like the upstream call was failing when in fact the feature
        # flag was off.
        logger.info(
            "avatar skip: flowkit_enabled=false (char=%s, story_id=%s)",
            char.name,
            story_id,
        )
        return None
    if not (getattr(cfg, "flowkit_project_id", "") or "").strip():
        logger.info(
            "avatar skip: flowkit_project_id empty (char=%s, story_id=%s)",
            char.name,
            story_id,
        )
        return None

    base_dir, url_prefix = _avatar_dirs(story_id)
    os.makedirs(base_dir, exist_ok=True)
    safe = _safe_name(char.name)
    filename = f"{safe}.png"

    from services.media.flow_service import FlowService

    prompt = _build_avatar_prompt(char, genre=genre)
    seed = _seed_for(safe)
    # One retry — FlowKit occasionally drops the connection mid-handshake under
    # parallel load (5 concurrent extracts vs workers_max=4). The second
    # attempt almost always succeeds because by then the worker slot freed up.
    last_exc: Optional[Exception] = None
    for attempt in (1, 2):
        try:
            path = await FlowService().request_image(
                prompt=prompt,
                char_refs=None,
                style_ref=None,
                output_dir=base_dir,
                filename=filename,
                aspect_override=_AVATAR_ASPECT,
                seed_override=seed,
            )
            if not path:
                # Distinguish "FlowService returned empty path" from "exception
                # was raised" — the empty-path branch is the silent failure
                # mode that historically left no trace in the logs.
                logger.warning(
                    "avatar attempt %d returned empty path for %s",
                    attempt,
                    char.name,
                )
                if attempt == 2:
                    return None
                continue
            return f"/media/{url_prefix}/{filename}"
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            logger.warning(
                "avatar attempt %d failed for %s: %s", attempt, char.name, exc
            )
    logger.warning("avatar generation gave up for %s: %s", char.name, last_exc)
    return None


def find_existing_avatar(name: str, story_id: Optional[str] = None) -> Optional[str]:
    """Return absolute path to a previously generated avatar, or None.

    The comic / chapter-illustration pipeline calls this BEFORE asking Seedream
    or FlowKit to generate a fresh reference image — if the extract endpoint
    already produced an avatar for this character, that avatar is the source
    of truth and downstream panels should be conditioned on it for consistency.
    A zero-byte file (FlowService crashed mid-write) is treated as missing so
    downstream callers get a chance to regenerate instead of feeding the
    image model a corrupt reference.

    Lookup order when ``story_id`` is provided:
      1) ``output/<story-slug>/images/avatars/<safe_name>.png`` (current layout)
      2) ``output/images/avatars/<safe_story_id>/<safe_name>.png`` (legacy scoped)
      3) ``output/images/avatars/<safe_name>.png`` (legacy unscoped)
    The legacy paths are kept so pre-migration stories with avatars already on
    disk keep rendering without needing a forced migration.
    """
    if not (name and name.strip()):
        return None
    from services.output_paths import OUTPUT_ROOT, avatars_dir

    safe = _safe_name(name)
    candidates: list[str] = []
    if story_id:
        candidates.append(os.path.join(avatars_dir(story_id=story_id), f"{safe}.png"))
        safe_story = safe_character_name(story_id)
        candidates.append(
            os.path.join(
                OUTPUT_ROOT, "images", _AVATAR_SUBDIR, safe_story, f"{safe}.png"
            )
        )
    candidates.append(
        os.path.join(OUTPUT_ROOT, "images", _AVATAR_SUBDIR, f"{safe}.png")
    )
    for path in candidates:
        try:
            if os.path.getsize(path) > 1024:
                return path
        except OSError:
            continue
    return None


def avatar_url_for(name: str, story_id: Optional[str] = None) -> Optional[str]:
    """Return the public ``/media`` URL for an existing avatar, or None.

    Bridges the on-disk, story-scoped avatar (written by extract-story's
    background task) to any UI that only knows the character name + story_id —
    notably the Characters page for localStorage-only library stories, which
    never live in the backend orchestrator store and so 404 on the
    profile/rebuild endpoints. Unlike those endpoints this needs no store: it
    is a pure filesystem lookup.

    The URL is derived from the file's actual location (so it handles both the
    new per-story path and the legacy paths returned by
    ``find_existing_avatar``) relative to the output root that ``/media`` serves,
    and carries a ``?v=<mtime>`` cache-buster so a regenerated portrait reloads
    in the browser while an unchanged one keeps a stable URL (avoids needless
    <img> churn).
    """
    path = find_existing_avatar(name, story_id)
    if not path:
        return None
    from services.output_paths import media_url

    url = media_url(path)
    try:
        url = f"{url}?v={int(os.path.getmtime(path))}"
    except OSError:
        pass
    return url


__all__ = ["generate_character_avatar", "find_existing_avatar"]
