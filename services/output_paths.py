"""Single source of truth for StoryForge's per-story output layout.

Historically ``output/`` was grouped *by file type* (``output/characters/``,
``output/images/``, ``output/checkpoints/``, ``output/library/``) with two
different story-scoping schemes layered on top inconsistently (image panels
keyed by ``slug(title)_session_id``, avatars keyed by ``safe_name(story_id)``,
checkpoints keyed by ``slug(title)_hash``). That made it impossible to find
"everything for one story" and let two stories collide.

This module flips the grouping to *by story*::

    output/
      <story-slug>/
        characters/<CharName>/profile.json
        images/                 # chapter / scene panels
        images/avatars/         # character portraits
        checkpoints/            # layerN.json + per_chapter/
        exports/                # pdf / epub / docx (was output/library/)

Every writer and reader in the codebase MUST build paths through the helpers
here rather than concatenating ``"output"`` themselves, so the layout has one
owner. The ``/media`` static mount serves ``OUTPUT_ROOT`` directly, so the
public URL for any media asset is simply ``/media/<path-relative-to-OUTPUT_ROOT>``
— see :func:`media_url`.

Story identity
--------------
Different layers know the story by different handles:
  - the L1/L2 pipeline knows ``story_title`` (+ a ``session_id``),
  - the extract / avatar path knows a frontend ``story_id`` (localStorage id),
  - run recovery only has a checkpoint filename.

:func:`story_slug` collapses all of these onto ONE deterministic slug so the
same story always lands in the same folder regardless of which handle the
caller holds. The slug reuses the existing :func:`slug_session_dir` /
:func:`safe_character_name` helpers — we do NOT invent a parallel scheme.
"""

from __future__ import annotations

import hashlib
import os
import re
from typing import Optional

from services.media._util import slug_session_dir
from services.safe_name import safe_character_name

__all__ = [
    "OUTPUT_ROOT",
    "UNSORTED_SLUG",
    "story_slug",
    "story_root",
    "characters_dir",
    "images_dir",
    "avatars_dir",
    "checkpoints_dir",
    "chapter_checkpoints_dir",
    "exports_dir",
    "media_url",
    "rel_to_output_root",
]

# Root of all generated output. Overridable for tests / alternate deployments
# via STORYFORGE_OUTPUT_ROOT; defaults to the legacy ``output`` directory so
# nothing changes for existing installs.
OUTPUT_ROOT = os.environ.get("STORYFORGE_OUTPUT_ROOT", "output")

# Bucket for assets that exist on disk but can't be attributed to a story
# (used by the migration script and as a defensive fallback).
UNSORTED_SLUG = "_unsorted"

_MAX_SLUG_LEN = 60
_SLUG_CLEAN_RE = re.compile(r"[^a-z0-9_-]+")


def story_slug(
    title: Optional[str] = None,
    *,
    story_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> str:
    """Return the deterministic per-story folder name.

    Resolution order — the first handle that yields a non-empty slug wins, so a
    caller can pass whichever identity it holds:

      1. ``story_id`` — the stable frontend/localStorage id. Preferred because
         it is constant across pipeline runs of the same story; sanitized via
         the shared :func:`safe_character_name` (also used for avatar scoping).
      2. ``title`` (optionally disambiguated by ``session_id``) — slugified via
         the shared :func:`slug_session_dir`. When a ``session_id`` is given the
         slug is ``slug(title)_session_id`` (matches the legacy image-panel
         convention); without one it is ``slug(title)``.

    Always returns a non-empty, filesystem-safe token (falls back to
    ``UNSORTED_SLUG``) so callers can build a valid path unconditionally.
    """
    if story_id and story_id.strip():
        slug = safe_character_name(story_id).lower()
        slug = _SLUG_CLEAN_RE.sub("_", slug).strip("_")
        if slug:
            return slug[:_MAX_SLUG_LEN]

    if title and title.strip():
        if session_id and session_id.strip():
            return slug_session_dir(title, session_id, max_len=_MAX_SLUG_LEN)
        # No session: slug the title alone. slug_session_dir always appends a
        # session token, so build the title slug directly via the same rules.
        base = slug_session_dir(title, "", max_len=_MAX_SLUG_LEN)
        # slug_session_dir(title, "") -> "{slug}_session"; strip the placeholder
        # and any trailing delimiter left by the title slug.
        if base.endswith("_session"):
            base = base[: -len("_session")]
        base = base.strip("_")
        return base or UNSORTED_SLUG

    return UNSORTED_SLUG


def title_hash(title: Optional[str]) -> str:
    """Stable 16-char hash of a story title.

    Preserves the legacy checkpoint hash so resume/recovery keeps matching
    pre-migration checkpoints by content rather than only by slug.
    """
    return hashlib.sha256((title or "untitled").encode()).hexdigest()[:16]


def story_root(
    title: Optional[str] = None,
    *,
    story_id: Optional[str] = None,
    session_id: Optional[str] = None,
    slug: Optional[str] = None,
) -> str:
    """Absolute-relative root folder for one story: ``output/<story-slug>``.

    Pass an explicit ``slug`` to bypass derivation (used by run recovery, which
    already holds the folder name).
    """
    s = slug or story_slug(title, story_id=story_id, session_id=session_id)
    return os.path.join(OUTPUT_ROOT, s)


def characters_dir(title=None, *, story_id=None, session_id=None, slug=None) -> str:
    """``output/<story>/characters`` — character visual-profile folders."""
    return os.path.join(
        story_root(title, story_id=story_id, session_id=session_id, slug=slug),
        "characters",
    )


def images_dir(title=None, *, story_id=None, session_id=None, slug=None) -> str:
    """``output/<story>/images`` — chapter / scene panels."""
    return os.path.join(
        story_root(title, story_id=story_id, session_id=session_id, slug=slug),
        "images",
    )


def avatars_dir(title=None, *, story_id=None, session_id=None, slug=None) -> str:
    """``output/<story>/images/avatars`` — character portraits."""
    return os.path.join(
        images_dir(title, story_id=story_id, session_id=session_id, slug=slug),
        "avatars",
    )


def checkpoints_dir(title=None, *, story_id=None, session_id=None, slug=None) -> str:
    """``output/<story>/checkpoints`` — layerN + sidecar checkpoints."""
    return os.path.join(
        story_root(title, story_id=story_id, session_id=session_id, slug=slug),
        "checkpoints",
    )


def chapter_checkpoints_dir(
    title=None, *, story_id=None, session_id=None, slug=None
) -> str:
    """``output/<story>/checkpoints/per_chapter`` — per-chapter resume files."""
    return os.path.join(
        checkpoints_dir(title, story_id=story_id, session_id=session_id, slug=slug),
        "per_chapter",
    )


def exports_dir(title=None, *, story_id=None, session_id=None, slug=None) -> str:
    """``output/<story>/exports`` — pdf / epub / docx (was ``output/library``)."""
    return os.path.join(
        story_root(title, story_id=story_id, session_id=session_id, slug=slug),
        "exports",
    )


def rel_to_output_root(path: str) -> str:
    """Path relative to OUTPUT_ROOT with forward slashes (for URL building)."""
    rel = os.path.relpath(os.path.abspath(path), os.path.abspath(OUTPUT_ROOT))
    return rel.replace(os.sep, "/")


def media_url(path: str) -> str:
    """Public ``/media`` URL for a file living under OUTPUT_ROOT.

    The ``/media`` static mount serves OUTPUT_ROOT, so the URL is just the
    file's path relative to that root. Returns the path unchanged-ish if it is
    already outside OUTPUT_ROOT (caller's responsibility to keep it inside).
    """
    return "/media/" + rel_to_output_root(path)
