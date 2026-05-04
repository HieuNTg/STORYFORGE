"""Character voice profiler — generates detailed voice profiles for distinct dialogue."""

import logging
from models.schemas import Character
from pipeline.layer1_story._legacy_voice_aliases import canonicalise_voice_profile

logger = logging.getLogger(__name__)

GENERATE_VOICE_PROFILES = """Bạn là chuyên gia xây dựng giọng văn nhân vật cho tiểu thuyết thể loại {genre}.

Dựa trên danh sách nhân vật sau, hãy tạo hồ sơ giọng nói chi tiết cho từng nhân vật:

{characters_description}

Yêu cầu: Trả về JSON array, mỗi phần tử tương ứng một nhân vật theo thứ tự trên.
Mỗi phần tử có cấu trúc:
{{
  "name": "tên nhân vật",
  "vocabulary_level": "formal | casual | archaic | mixed",
  "sentence_style": "short_punchy | long_flowing | fragmented | poetic",
  "verbal_tics": ["tic 1", "tic 2"],
  "emotional_expression": {{
    "anger": "cách biểu đạt khi giận",
    "joy": "cách biểu đạt khi vui",
    "sadness": "cách biểu đạt khi buồn"
  }},
  "dialogue_example": ["câu thoại mẫu 1", "câu thoại mẫu 2", "câu thoại mẫu 3"]
}}

Nguyên tắc:
- Mỗi nhân vật phải có giọng nói RÕ RÀNG KHÁC BIỆT với nhân vật khác
- verbal_tics phải cụ thể (ví dụ: "hay thêm 'thật ra là...' khi giải thích", "kết câu bằng '...vậy đó'")
- dialogue_example phải thể hiện rõ tính cách và giọng văn đặc trưng
- emotional_expression phải phù hợp với tính cách và xuất thân nhân vật

Chỉ trả về JSON array, không giải thích thêm."""


def _build_characters_description(characters: list[Character]) -> str:
    parts = []
    for i, c in enumerate(characters, 1):
        lines = [f"{i}. {c.name} ({c.role})"]
        lines.append(f"   Tính cách: {c.personality}")
        if c.background:
            lines.append(f"   Xuất thân: {c.background}")
        if c.motivation:
            lines.append(f"   Động lực: {c.motivation}")
        if c.speech_pattern:
            lines.append(f"   Phong cách nói hiện tại: {c.speech_pattern}")
        parts.append("\n".join(lines))
    return "\n\n".join(parts)


def generate_voice_profiles(llm, characters: list[Character], genre: str, model=None) -> list[dict]:
    """Generate detailed voice profiles for each character via LLM.

    Args:
        llm: LLMClient instance
        characters: list of Character objects
        genre: story genre string
        model: optional model override

    Returns:
        list of voice profile dicts (one per character, same order as input).
        Returns empty list on total failure; partial results preserved on per-character errors.
    """
    if not characters:
        return []

    chars_desc = _build_characters_description(characters)
    system_prompt = GENERATE_VOICE_PROFILES.format(
        genre=genre,
        characters_description=chars_desc,
    )
    user_prompt = f"Tạo hồ sơ giọng nói cho {len(characters)} nhân vật trên."

    kwargs = {"system_prompt": system_prompt, "user_prompt": user_prompt}
    if model:
        kwargs["model"] = model

    try:
        result = llm.generate_json(**kwargs)
    except Exception as exc:
        logger.warning("generate_voice_profiles: LLM call failed — %s", exc)
        return []

    # Result may be a list directly or a dict wrapping a list
    if isinstance(result, list):
        profiles = result
    elif isinstance(result, dict):
        # Try common wrapper keys
        for key in ("profiles", "characters", "data", "result"):
            if key in result and isinstance(result[key], list):
                profiles = result[key]
                break
        else:
            # LLM may return single profile dict directly (when 1 character)
            # Sometimes LLM omits "name" key — infer from input if only 1 character
            voice_profile_keys = {"vocabulary_level", "sentence_style", "verbal_tics", "emotional_expression", "dialogue_example"}
            if "vocabulary_level" in result and voice_profile_keys & set(result.keys()):
                if "name" not in result and len(characters) == 1:
                    result["name"] = characters[0].name
                    logger.debug("generate_voice_profiles: inferred name '%s' for single-character profile", result["name"])
                profiles = [result]
            else:
                logger.warning("generate_voice_profiles: unexpected dict shape, keys=%s", list(result.keys()))
                return []
    else:
        logger.warning("generate_voice_profiles: unexpected result type %s", type(result))
        return []

    # Ensure each profile is a dict; drop malformed entries non-fatally
    cleaned = []
    for item in profiles:
        if isinstance(item, dict):
            cleaned.append(canonicalise_voice_profile(item))
        else:
            logger.debug("generate_voice_profiles: skipping non-dict profile entry: %s", item)

    if len(cleaned) != len(characters):
        logger.warning(
            "generate_voice_profiles: expected %d profiles, got %d",
            len(characters),
            len(cleaned),
        )

    return cleaned


def format_voice_profiles_for_prompt(profiles: list[dict]) -> str:
    """Format voice profiles into a compact prompt section for chapter writing.

    Args:
        profiles: list of voice profile dicts from generate_voice_profiles()

    Returns:
        Formatted string ready to embed in a chapter-writing prompt.
    """
    if not profiles:
        return ""

    lines = ["GIỌNG NÓI NHÂN VẬT:"]
    for p in profiles:
        name = p.get("name", "?")
        vocab = p.get("vocabulary_level", "")
        style = p.get("sentence_style", "")
        tics = p.get("verbal_tics") or []
        emotional = p.get("emotional_expression") or {}
        examples = p.get("dialogue_examples") or p.get("dialogue_example") or []

        header_parts = [x for x in [vocab, style] if x]
        header = f"[{', '.join(header_parts)}]" if header_parts else ""
        lines.append(f"\n{name} {header}".strip())

        if tics:
            lines.append(f"  Tật nói: {'; '.join(tics[:3])}")

        anger = emotional.get("anger", "")
        if anger:
            lines.append(f"  Khi giận: {anger}")

        if examples:
            lines.append(f"  Ví dụ: \"{examples[0]}\"")
            if len(examples) > 1:
                lines.append(f"          \"{examples[1]}\"")

    return "\n".join(lines)


def update_character_speech_patterns(characters: list[Character], profiles: list[dict]) -> None:
    """Update each Character's speech_pattern field with a summary from their voice profile.

    Mutates characters in place. Matches by name (case-insensitive).
    Characters with no matching profile are left unchanged.

    Args:
        characters: list of Character objects to update
        profiles: list of voice profile dicts from generate_voice_profiles()
    """
    profile_map = {p.get("name", "").lower(): p for p in profiles if isinstance(p, dict)}

    for char in characters:
        profile = profile_map.get(char.name.lower())
        if not profile:
            continue

        parts = []
        vocab = profile.get("vocabulary_level", "")
        style = profile.get("sentence_style", "")
        if vocab:
            parts.append(vocab)
        if style:
            parts.append(style)

        tics = profile.get("verbal_tics") or []
        if tics:
            parts.append(f"tật: {'; '.join(tics[:2])}")

        emotional = profile.get("emotional_expression") or {}
        anger = emotional.get("anger", "")
        if anger:
            parts.append(f"giận: {anger}")

        examples = profile.get("dialogue_examples") or profile.get("dialogue_example") or []
        if examples:
            parts.append(f"vd: \"{examples[0]}\"")

        char.speech_pattern = " | ".join(parts) if parts else char.speech_pattern
