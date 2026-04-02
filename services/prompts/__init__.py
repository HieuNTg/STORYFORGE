"""Prompt templates package — re-exports all prompts for backward compatibility.

All prompts are Vietnamese by default. localize_prompt() handles runtime
translation when config.pipeline.language != "vi".
"""


def localize_prompt(prompt: str, language: str = "vi") -> str:
    """Wrap prompt with language instruction for non-Vietnamese output."""
    if language == "vi":
        return prompt
    lang_names = {"en": "English", "vi": "Vietnamese"}
    lang_name = lang_names.get(language, language)
    return (
        f"IMPORTANT: Respond entirely in {lang_name}. "
        f"Translate all content, names, and descriptions to {lang_name}.\n\n"
        f"{prompt}"
    )


from services.prompts.story_prompts import (  # noqa: E402
    SUGGEST_TITLE, GENERATE_CHARACTERS, GENERATE_WORLD,
    GENERATE_OUTLINE, CONTINUE_OUTLINE, WRITE_CHAPTER,
    SUMMARIZE_CHAPTER, EXTRACT_CHARACTER_STATE,
    EXTRACT_PLOT_EVENTS, SCORE_CHAPTER,
)
from services.prompts.analysis_prompts import (  # noqa: E402
    ANALYZE_STORY, AGENT_PERSONA, EVALUATE_DRAMA,
    ENHANCE_CHAPTER, DRAMA_SUGGESTIONS,
)
from services.prompts.revision_prompts import (  # noqa: E402
    ESCALATION_EVENT, QUICK_DRAMA_CHECK, REENHANCE_CHAPTER,
    RAG_CONTEXT_SECTION, EXTRACT_CHAPTER_EMOTIONS,
    SMART_REVISE_CHAPTER,
)
from services.prompts.system_prompts import (  # noqa: E402
    GENERATE_STORYBOARD, GENERATE_VOICE_SCRIPT,
    CHARACTER_IMAGE_PROMPT, LOCATION_IMAGE_PROMPT,
)

__all__ = [
    "localize_prompt",
    # Layer 1
    "SUGGEST_TITLE", "GENERATE_CHARACTERS", "GENERATE_WORLD",
    "GENERATE_OUTLINE", "CONTINUE_OUTLINE", "WRITE_CHAPTER",
    "SUMMARIZE_CHAPTER", "EXTRACT_CHARACTER_STATE",
    "EXTRACT_PLOT_EVENTS", "SCORE_CHAPTER",
    # Layer 2 + Analytics
    "ANALYZE_STORY", "AGENT_PERSONA", "EVALUATE_DRAMA",
    "ENHANCE_CHAPTER", "DRAMA_SUGGESTIONS",
    "ESCALATION_EVENT", "QUICK_DRAMA_CHECK", "REENHANCE_CHAPTER",
    "RAG_CONTEXT_SECTION", "EXTRACT_CHAPTER_EMOTIONS",
    "SMART_REVISE_CHAPTER",
    # Layer 3
    "GENERATE_STORYBOARD", "GENERATE_VOICE_SCRIPT",
    "CHARACTER_IMAGE_PROMPT", "LOCATION_IMAGE_PROMPT",
]
