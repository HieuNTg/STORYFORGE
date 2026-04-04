"""Extract structured visual attributes from character descriptions for consistent image generation."""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

_DEFAULT_ATTRIBUTES = {
    "hair": {"color": "", "style": "", "details": ""},
    "eyes": {"color": "", "shape": ""},
    "face": {"shape": "", "features": ""},
    "build": {"height": "", "type": ""},
    "skin": {"tone": "", "details": ""},
    "outfit": {"default": "", "accessories": ""},
    "age_appearance": "",
    "distinguishing_features": [],
}

_SYSTEM_PROMPT = (
    "You are a character visual analyst. Extract physical appearance attributes from the given "
    "character description. Always respond in JSON format."
)

_USER_PROMPT_TEMPLATE = """Extract the visual/physical appearance attributes of the following character and return structured JSON.

Character name: {name}
Role: {role}
Personality: {personality}
Appearance description: {appearance}
Background: {background}

Return a JSON object with these exact keys:
{{
  "hair": {{"color": "...", "style": "...", "details": "..."}},
  "eyes": {{"color": "...", "shape": "..."}},
  "face": {{"shape": "...", "features": "..."}},
  "build": {{"height": "...", "type": "..."}},
  "skin": {{"tone": "...", "details": "..."}},
  "outfit": {{"default": "...", "accessories": "..."}},
  "age_appearance": "...",
  "distinguishing_features": ["...", "..."]
}}

Rules:
- All values must be in English
- Use empty string "" if information is not available
- distinguishing_features should list 0-5 notable items
- Keep descriptions concise but specific"""


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
        user_prompt = _USER_PROMPT_TEMPLATE.format(
            name=getattr(character, "name", ""),
            role=getattr(character, "role", ""),
            personality=getattr(character, "personality", ""),
            appearance=getattr(character, "appearance", ""),
            background=getattr(character, "background", ""),
        )
        try:
            result = self.llm.generate_json(
                system_prompt=_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                temperature=0.3,
            )
            # Merge with defaults to ensure all keys exist
            attributes = dict(_DEFAULT_ATTRIBUTES)
            for key in _DEFAULT_ATTRIBUTES:
                if key in result:
                    attributes[key] = result[key]
            return attributes
        except Exception as e:
            logger.warning("LLM attribute extraction failed for %s: %s — using fallback",
                           getattr(character, "name", "unknown"), e)
            return self._fallback_attributes(character)

    def generate_frozen_prompt(self, name: str, attributes: dict) -> str:
        """Convert structured attributes to a stable English prompt for image generation."""
        parts = []

        # Build appearance description
        build = attributes.get("build", {})
        height = build.get("height", "") if isinstance(build, dict) else ""
        build_type = build.get("type", "") if isinstance(build, dict) else ""
        age = attributes.get("age_appearance", "")

        if height or build_type or age:
            desc_parts = []
            if height:
                desc_parts.append(height)
            if build_type:
                desc_parts.append(build_type)
            if age:
                desc_parts.append(f"in {age}")
            parts.append("A " + " ".join(desc_parts) + " person")
        else:
            parts.append("A character")

        # Skin tone
        skin = attributes.get("skin", {})
        skin_tone = skin.get("tone", "") if isinstance(skin, dict) else ""
        skin_details = skin.get("details", "") if isinstance(skin, dict) else ""
        if skin_tone:
            skin_desc = skin_tone + (" skin" if "skin" not in skin_tone else "")
            if skin_details:
                skin_desc += f" ({skin_details})"
            parts.append(f"with {skin_desc}")

        # Hair
        hair = attributes.get("hair", {})
        if isinstance(hair, dict):
            h_color = hair.get("color", "")
            h_style = hair.get("style", "")
            h_details = hair.get("details", "")
            if h_color or h_style:
                hair_desc = " ".join(filter(None, [h_style, h_color, "hair"]))
                if h_details:
                    hair_desc += f" {h_details}"
                parts.append(hair_desc)

        # Eyes
        eyes = attributes.get("eyes", {})
        if isinstance(eyes, dict):
            e_color = eyes.get("color", "")
            e_shape = eyes.get("shape", "")
            if e_color or e_shape:
                eye_desc = " ".join(filter(None, [e_shape, e_color, "eyes"]))
                parts.append(eye_desc)

        # Face features
        face = attributes.get("face", {})
        if isinstance(face, dict):
            f_shape = face.get("shape", "")
            f_features = face.get("features", "")
            if f_shape:
                face_desc = f"{f_shape} face"
                if f_features:
                    face_desc += f" with {f_features}"
                parts.append(face_desc)
            elif f_features:
                parts.append(f_features)

        # Outfit
        outfit = attributes.get("outfit", {})
        if isinstance(outfit, dict):
            o_default = outfit.get("default", "")
            o_accessories = outfit.get("accessories", "")
            if o_default:
                outfit_desc = f"wearing {o_default}"
                if o_accessories:
                    outfit_desc += f" and {o_accessories}"
                parts.append(outfit_desc)

        # Distinguishing features not already mentioned
        dist = attributes.get("distinguishing_features", [])
        if isinstance(dist, list) and dist:
            parts.append(f"notable features: {', '.join(str(f) for f in dist[:3])}")

        base_prompt = ", ".join(parts)
        return f"{base_prompt}, fantasy art style, detailed character portrait"

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
        attributes = {k: (dict(v) if isinstance(v, dict) else list(v) if isinstance(v, list) else v)
                      for k, v in _DEFAULT_ATTRIBUTES.items()}
        appearance = getattr(character, "appearance", "")
        if appearance:
            attributes["outfit"]["default"] = appearance[:200]
        return attributes
