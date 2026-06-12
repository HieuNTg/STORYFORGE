"""Persistent character visual profile store for consistent image generation."""

import os
import logging
import shutil
from typing import Optional
from datetime import datetime

from services._visual_profile_io import (
    build_visual_description as _build_visual_description,
    list_profile_jsons,
    read_profile_json,
    resolve_profile_base_dir,
    store_reference_image,
    write_profile_json,
)
from services.safe_name import safe_character_name

logger = logging.getLogger(__name__)


class CharacterVisualProfileStore:
    """Store and retrieve character visual profiles (descriptions + reference images)."""

    def __init__(
        self,
        base_dir: Optional[str] = None,
        *,
        story_title: Optional[str] = None,
        story_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ):
        """Visual-profile store rooted at a per-story characters dir.

        Pass a story handle (``story_title`` / ``story_id`` / ``session_id``) to
        scope profiles under ``output/<story-slug>/characters`` via the central
        resolver. An explicit ``base_dir`` overrides the handle (used by tests).
        When nothing is given we fall back to the legacy global
        ``output/characters`` so pre-migration data and unscoped callers keep
        working.
        """
        self.base_dir = resolve_profile_base_dir(
            base_dir,
            story_title=story_title,
            story_id=story_id,
            session_id=session_id,
        )
        os.makedirs(self.base_dir, exist_ok=True)

    def _safe_name(self, name: str) -> str:
        """Filesystem-safe directory name — delegates to the shared utility.

        Previously had its own implementation that diverged from
        ``services.character_avatar._safe_name`` for names with punctuation or
        names longer than 60 chars. Centralizing avoids the bug where the
        extract endpoint writes an avatar under one slug while the consistency
        pipeline looks for the profile under a different slug.
        """
        return safe_character_name(name)

    def _profile_dir(self, name: str) -> str:
        return os.path.join(self.base_dir, self._safe_name(name))

    def _profile_path(self, name: str) -> str:
        return os.path.join(self._profile_dir(name), "profile.json")

    def has_profile(self, name: str) -> bool:
        return os.path.exists(self._profile_path(name))

    def save_profile(
        self, name: str, appearance_desc: str, reference_image_path: str = ""
    ) -> None:
        """Save character visual profile."""
        pdir = self._profile_dir(name)
        os.makedirs(pdir, exist_ok=True)

        profile = {
            "name": name,
            "description": appearance_desc,
            "reference_image": store_reference_image(pdir, reference_image_path),
            "created_at": datetime.now().isoformat(),
        }
        write_profile_json(self._profile_path(name), profile)
        logger.info("Saved visual profile for: %s", name)

    def save_enhanced_profile(
        self,
        name: str,
        appearance_desc: str,
        structured_attributes: dict,
        frozen_prompt: str,
        reference_image_path: str = "",
    ) -> None:
        """Save character visual profile with structured attributes and frozen prompt."""
        pdir = self._profile_dir(name)
        os.makedirs(pdir, exist_ok=True)

        ref_stored = store_reference_image(pdir, reference_image_path)

        # Preserve existing prompt_version if profile already exists
        existing = self.load_profile(name)
        prompt_version = 1
        if (
            existing
            and existing.get("frozen_prompt")
            and existing.get("frozen_prompt") != frozen_prompt
        ):
            prompt_version = existing.get("prompt_version", 1) + 1
        elif existing and existing.get("prompt_version"):
            prompt_version = existing["prompt_version"]

        profile = {
            "name": name,
            "description": appearance_desc,
            "reference_image": ref_stored,
            "structured_attributes": structured_attributes,
            "frozen_prompt": frozen_prompt,
            "prompt_version": prompt_version,
            "created_at": existing.get("created_at", datetime.now().isoformat())
            if existing
            else datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
        write_profile_json(self._profile_path(name), profile)
        logger.info(
            "Saved enhanced visual profile for: %s (prompt_version=%d)",
            name,
            prompt_version,
        )

    def load_profile(self, name: str) -> Optional[dict]:
        """Load character visual profile. Returns None if not found."""
        return read_profile_json(self._profile_path(name), name)

    def set_reference_image(self, name: str, image_path: str) -> bool:
        """Update only the reference_image field on an existing profile.

        Avoids re-running the LLM extractor when the user has just uploaded a
        reference image. Returns False if no profile exists yet (caller should
        create one via save_enhanced_profile first).
        """
        profile = self.load_profile(name)
        if not profile:
            return False
        profile["reference_image"] = image_path
        profile["updated_at"] = datetime.now().isoformat()
        write_profile_json(self._profile_path(name), profile)
        return True

    def get_reference_image(self, name: str) -> Optional[str]:
        """Get path to character reference image."""
        profile = self.load_profile(name)
        if profile and profile.get("reference_image"):
            ref = profile["reference_image"]
            if os.path.exists(ref):
                return ref
        return None

    def get_visual_description(self, name: str) -> str:
        """Get frozen visual description for prompt injection."""
        profile = self.load_profile(name)
        if profile and profile.get("description"):
            return profile["description"]
        return ""

    def get_frozen_prompt(self, name: str) -> str:
        """Return the frozen image generation prompt for a character.

        Falls back to the plain description if no frozen_prompt is saved.
        Returns empty string if profile does not exist.
        """
        profile = self.load_profile(name)
        if not profile:
            return ""
        if profile.get("frozen_prompt"):
            return profile["frozen_prompt"]
        return profile.get("description", "")

    def build_visual_description(self, character) -> str:
        """Build a visual description from Character object attributes.

        Uses character.appearance if available, otherwise constructs from
        name + personality. This is a simple text-based description, not LLM-generated.
        """
        return _build_visual_description(character)

    def list_profiles(self) -> list:
        """List all saved character profiles."""
        return list_profile_jsons(self.base_dir)

    def delete_profile(self, name: str) -> bool:
        """Delete a character profile and its reference image."""
        pdir = self._profile_dir(name)
        if os.path.exists(pdir):
            shutil.rmtree(pdir)
            return True
        return False
