"""Prompts and prompt-building for the character visual extractor.

Internal module for services/character_visual_extractor.py: the extraction
prompts, the default attribute structure, and the attributes → frozen image
prompt formatter live here so the extractor class stays focused on LLM
orchestration.
"""

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
    "You are a character visual analyst. Extract physical appearance attributes ONLY from "
    "what is EXPLICITLY stated in the provided character description. Do NOT invent, infer "
    "from genre tropes, or add stylistic flourishes. If a field is not mentioned in the "
    "source text, return an empty string. Always respond in JSON format."
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

STRICT EXTRACTION RULES:
- ONLY extract attributes that are EXPLICITLY stated in the appearance/background/personality text above.
- If a detail is NOT in the source text, return "" (empty string) — do NOT guess.
- Do NOT invent props, motifs, animals (cranes, dragons, phoenixes), weapons, or symbolic
  flourishes based on the character's name or apparent genre. A wuxia name does not mean
  the character has a sword or carries flowers.
- Do NOT extrapolate from role or personality (e.g. "antagonist" does NOT imply dark clothing).
- distinguishing_features must be 0-5 items that are LITERALLY mentioned in the source,
  not inferred. Empty list is the correct answer when nothing distinctive is described.
- All values must be in English.
- Keep descriptions concise but specific."""


def build_frozen_prompt(attributes: dict) -> str:
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
