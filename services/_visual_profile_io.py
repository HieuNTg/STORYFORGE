"""I/O and description helpers for the character visual profile store.

Internal module for services/character_visual_profile.py: base-dir
resolution, reference-image storage, profile JSON read/write, and the plain
text description builder live here so the store class stays focused on
profile semantics.
"""

import json
import logging
import os
import shutil
from typing import Optional

logger = logging.getLogger(__name__)


def resolve_profile_base_dir(
    base_dir: Optional[str],
    *,
    story_title: Optional[str] = None,
    story_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> str:
    """Resolve the characters directory for a visual-profile store.

    An explicit ``base_dir`` wins (used by tests). A story handle
    (``story_title`` / ``story_id`` / ``session_id``) scopes profiles under
    ``output/<story-slug>/characters`` via the central resolver. With nothing
    given we fall back to the legacy global ``output/characters`` so
    pre-migration data and unscoped callers keep working.
    """
    if base_dir is not None:
        return base_dir
    if story_title or story_id or session_id:
        from services.output_paths import characters_dir

        return characters_dir(story_title, story_id=story_id, session_id=session_id)
    from services.output_paths import OUTPUT_ROOT

    return os.path.join(OUTPUT_ROOT, "characters")


def store_reference_image(profile_dir: str, reference_image_path: str) -> str:
    """Copy a reference image into ``profile_dir`` as ``reference.<ext>``.

    Returns the stored path, or "" when no usable source image was given.
    A copy is skipped when source and destination are already the same file.
    """
    if not (reference_image_path and os.path.exists(reference_image_path)):
        return ""
    ext = os.path.splitext(reference_image_path)[1]
    ref_stored = os.path.join(profile_dir, f"reference{ext}")
    if os.path.abspath(reference_image_path) != os.path.abspath(ref_stored):
        shutil.copy2(reference_image_path, ref_stored)
    return ref_stored


def write_profile_json(path: str, profile: dict) -> None:
    """Write a profile dict as UTF-8 JSON (ensure_ascii=False, indent=2)."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)


def list_profile_jsons(base_dir: str) -> list:
    """Load every ``<base_dir>/*/profile.json``; corrupt files are skipped."""
    profiles = []
    if not os.path.exists(base_dir):
        return profiles
    for dirname in os.listdir(base_dir):
        ppath = os.path.join(base_dir, dirname, "profile.json")
        if os.path.exists(ppath):
            try:
                with open(ppath, "r", encoding="utf-8") as f:
                    profiles.append(json.load(f))
            except Exception:
                pass
    return profiles


def build_visual_description(character) -> str:
    """Build a visual description from Character object attributes.

    Uses character.appearance if available, otherwise constructs from
    name + personality. This is a simple text-based description, not
    LLM-generated.
    """
    parts = []
    if hasattr(character, "appearance") and character.appearance:
        parts.append(character.appearance)
    if hasattr(character, "personality") and character.personality:
        parts.append(character.personality)
    if not parts:
        parts.append(character.name if hasattr(character, "name") else str(character))
    return ". ".join(parts)


def read_profile_json(path: str, name: str) -> Optional[dict]:
    """Read a profile JSON file; returns None if missing or unreadable.

    ``name`` is only used for the warning log on a corrupt file.
    """
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning("Failed to load profile for %s: %s", name, e)
        return None
