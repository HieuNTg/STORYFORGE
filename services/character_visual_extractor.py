"""Extract structured visual attributes from character descriptions for consistent image generation."""

import logging

from services._visual_extractor_prompts import (
    _DEFAULT_ATTRIBUTES,
    _SYSTEM_PROMPT,
    _USER_PROMPT_TEMPLATE,
    build_frozen_prompt,
)

__all__ = ["CharacterVisualExtractor", "_DEFAULT_ATTRIBUTES"]

logger = logging.getLogger(__name__)


class CharacterVisualExtractor:
    """Extract structured visual attributes and generate frozen image generation prompts."""

    def __init__(self):
        from services.llm_client import LLMClient

        self.llm = LLMClient()

    def extract_attributes(self, character) -> dict:
        """Extract structured visual attributes from a Character object.

        Returns a dict with keys: hair, eyes, face, build, skin, outfit,
        age_appearance, distinguishing_features.
        Falls back to empty-value structure on LLM failure.
        """
        # Field-name compatibility: `Character` (from StoryDraft) uses
        # appearance/background; `ForgeCharacter` (from /extract-story) uses
        # description/backstory. Or-fallback so this extractor stays correct
        # if a caller ever feeds a Forge character in without re-mapping —
        # without it the LLM gets empty inputs and starts hallucinating
        # attributes, defeating the strict-extraction prompt.
        user_prompt = _USER_PROMPT_TEMPLATE.format(
            name=getattr(character, "name", ""),
            role=getattr(character, "role", ""),
            personality=getattr(character, "personality", ""),
            appearance=(
                getattr(character, "appearance", "")
                or getattr(character, "description", "")
                or ""
            ),
            background=(
                getattr(character, "background", "")
                or getattr(character, "backstory", "")
                or ""
            ),
        )
        try:
            result = self.llm.generate_json(
                system_prompt=_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                temperature=0.3,
                expect="dict",
            )
            # Merge with defaults to ensure all keys exist
            attributes = dict(_DEFAULT_ATTRIBUTES)
            for key in _DEFAULT_ATTRIBUTES:
                if key in result:
                    attributes[key] = result[key]
            return attributes
        except Exception as e:
            logger.warning(
                "LLM attribute extraction failed for %s: %s — using fallback",
                getattr(character, "name", "unknown"),
                e,
            )
            return self._fallback_attributes(character)

    def generate_frozen_prompt(self, name: str, attributes: dict) -> str:
        """Convert structured attributes to a stable English prompt for image generation."""
        return build_frozen_prompt(attributes)

    def extract_and_generate(self, character) -> tuple:
        """Convenience method: extract attributes then generate frozen prompt.

        Returns (attributes: dict, frozen_prompt: str).
        """
        attributes = self.extract_attributes(character)
        frozen_prompt = self.generate_frozen_prompt(
            name=getattr(character, "name", ""),
            attributes=attributes,
        )
        return attributes, frozen_prompt

    def _fallback_attributes(self, character) -> dict:
        """Build minimal attributes from character fields without LLM."""
        attributes = {
            k: (
                dict(v)
                if isinstance(v, dict)
                else list(v)
                if isinstance(v, list)
                else v
            )
            for k, v in _DEFAULT_ATTRIBUTES.items()
        }
        appearance = (
            getattr(character, "appearance", "")
            or getattr(character, "description", "")
            or ""
        )
        if appearance:
            attributes["outfit"]["default"] = appearance[:200]
        return attributes
