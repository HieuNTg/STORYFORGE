"""Persistent character visual profile store for consistent image generation."""
import os
import json
import logging
import shutil
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class CharacterVisualProfileStore:
    """Store and retrieve character visual profiles (descriptions + reference images)."""

    def __init__(self, base_dir: str = "output/characters"):
        self.base_dir = base_dir
        os.makedirs(base_dir, exist_ok=True)

    def _safe_name(self, name: str) -> str:
        """Convert character name to filesystem-safe directory name."""
        return "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in name).strip("_")

    def _profile_dir(self, name: str) -> str:
        return os.path.join(self.base_dir, self._safe_name(name))

    def _profile_path(self, name: str) -> str:
        return os.path.join(self._profile_dir(name), "profile.json")

    def has_profile(self, name: str) -> bool:
        return os.path.exists(self._profile_path(name))

    def save_profile(self, name: str, appearance_desc: str, reference_image_path: str = "") -> None:
        """Save character visual profile."""
        pdir = self._profile_dir(name)
        os.makedirs(pdir, exist_ok=True)

        ref_stored = ""
        if reference_image_path and os.path.exists(reference_image_path):
            ext = os.path.splitext(reference_image_path)[1]
            ref_stored = os.path.join(pdir, f"reference{ext}")
            if os.path.abspath(reference_image_path) != os.path.abspath(ref_stored):
                shutil.copy2(reference_image_path, ref_stored)

        profile = {
            "name": name,
            "description": appearance_desc,
            "reference_image": ref_stored,
            "created_at": datetime.now().isoformat(),
        }
        with open(self._profile_path(name), "w", encoding="utf-8") as f:
            json.dump(profile, f, ensure_ascii=False, indent=2)
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

        ref_stored = ""
        if reference_image_path and os.path.exists(reference_image_path):
            ext = os.path.splitext(reference_image_path)[1]
            ref_stored = os.path.join(pdir, f"reference{ext}")
            if os.path.abspath(reference_image_path) != os.path.abspath(ref_stored):
                shutil.copy2(reference_image_path, ref_stored)

        # Preserve existing prompt_version if profile already exists
        existing = self.load_profile(name)
        prompt_version = 1
        if existing and existing.get("frozen_prompt") and existing.get("frozen_prompt") != frozen_prompt:
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
            "created_at": existing.get("created_at", datetime.now().isoformat()) if existing else datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
        with open(self._profile_path(name), "w", encoding="utf-8") as f:
            json.dump(profile, f, ensure_ascii=False, indent=2)
        logger.info("Saved enhanced visual profile for: %s (prompt_version=%d)", name, prompt_version)

    def load_profile(self, name: str) -> Optional[dict]:
        """Load character visual profile. Returns None if not found."""
        path = self._profile_path(name)
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning("Failed to load profile for %s: %s", name, e)
            return None

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
        with open(self._profile_path(name), "w", encoding="utf-8") as f:
            json.dump(profile, f, ensure_ascii=False, indent=2)
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
        parts = []
        if hasattr(character, "appearance") and character.appearance:
            parts.append(character.appearance)
        if hasattr(character, "personality") and character.personality:
            parts.append(character.personality)
        if not parts:
            parts.append(character.name if hasattr(character, "name") else str(character))
        return ". ".join(parts)

    def list_profiles(self) -> list:
        """List all saved character profiles."""
        profiles = []
        if not os.path.exists(self.base_dir):
            return profiles
        for dirname in os.listdir(self.base_dir):
            ppath = os.path.join(self.base_dir, dirname, "profile.json")
            if os.path.exists(ppath):
                try:
                    with open(ppath, "r", encoding="utf-8") as f:
                        profiles.append(json.load(f))
                except Exception:
                    pass
        return profiles

    def delete_profile(self, name: str) -> bool:
        """Delete a character profile and its reference image."""
        pdir = self._profile_dir(name)
        if os.path.exists(pdir):
            shutil.rmtree(pdir)
            return True
        return False
