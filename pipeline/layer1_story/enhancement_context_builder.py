"""Build enhancement context strings for chapter writing prompts.

Aggregates theme premise, voice profiles, scene decomposition, and
show-don't-tell guidance into a single context string injected before writing.
"""

import logging

logger = logging.getLogger(__name__)


def build_enhancement_context(
    config,
    llm,
    genre: str,
    pacing: str = "",
    premise: dict = None,
    voice_profiles: list = None,
    outline=None,
    characters: list = None,
    world=None,
    layer_model: str = None,
) -> str:
    """Build combined enhancement context for a single chapter.

    All sub-steps are non-fatal — returns whatever context was successfully built.
    """
    parts = []

    # Theme premise
    if premise and getattr(config.pipeline, "enable_theme_premise", False):
        try:
            from pipeline.layer1_story.theme_premise_generator import format_premise_for_prompt
            text = format_premise_for_prompt(premise)
            if text:
                parts.append(text)
        except Exception as e:
            logger.debug("Enhancement: premise format failed: %s", e)

    # Voice profiles
    if voice_profiles and getattr(config.pipeline, "enable_voice_profiles", False):
        try:
            from pipeline.layer1_story.character_voice_profiler import format_voice_profiles_for_prompt
            text = format_voice_profiles_for_prompt(voice_profiles)
            if text:
                parts.append(text)
        except Exception as e:
            logger.debug("Enhancement: voice profiles format failed: %s", e)

    # Scene decomposition (requires LLM call)
    if (
        outline
        and characters
        and world
        and getattr(config.pipeline, "enable_scene_decomposition", False)
    ):
        try:
            from pipeline.layer1_story.scene_decomposer import (
                decompose_chapter_scenes, format_scenes_for_prompt, should_decompose,
            )
            if should_decompose(outline.chapter_number, pacing):
                scenes = decompose_chapter_scenes(llm, outline, characters, world, genre, model=layer_model)
                text = format_scenes_for_prompt(scenes)
                if text:
                    parts.append(text)
        except Exception as e:
            logger.debug("Enhancement: scene decomposition failed: %s", e)

    # Show-don't-tell guidance (no LLM call)
    if getattr(config.pipeline, "enable_show_dont_tell", False):
        try:
            from pipeline.layer1_story.show_dont_tell_enforcer import build_show_dont_tell_guidance
            text = build_show_dont_tell_guidance(genre, pacing)
            if text:
                parts.append(text)
        except Exception as e:
            logger.debug("Enhancement: show-dont-tell guidance failed: %s", e)

    return "\n\n".join(parts) if parts else ""


def build_shared_enhancement_context(
    config,
    genre: str,
    premise: dict = None,
    voice_profiles: list = None,
) -> str:
    """Build enhancement context shared across a parallel batch (no per-chapter LLM calls).

    Includes: premise, voice profiles, show-don't-tell.
    Scene decomposition excluded (per-chapter).
    """
    parts = []

    if premise and getattr(config.pipeline, "enable_theme_premise", False):
        try:
            from pipeline.layer1_story.theme_premise_generator import format_premise_for_prompt
            text = format_premise_for_prompt(premise)
            if text:
                parts.append(text)
        except Exception:
            pass

    if voice_profiles and getattr(config.pipeline, "enable_voice_profiles", False):
        try:
            from pipeline.layer1_story.character_voice_profiler import format_voice_profiles_for_prompt
            text = format_voice_profiles_for_prompt(voice_profiles)
            if text:
                parts.append(text)
        except Exception:
            pass

    if getattr(config.pipeline, "enable_show_dont_tell", False):
        try:
            from pipeline.layer1_story.show_dont_tell_enforcer import build_show_dont_tell_guidance
            text = build_show_dont_tell_guidance(genre)
            if text:
                parts.append(text)
        except Exception:
            pass

    return "\n\n".join(parts) if parts else ""
