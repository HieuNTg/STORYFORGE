"""Prompt versioning manager — loads prompts from YAML with fallback to hardcoded constants."""

from __future__ import annotations

import importlib
import logging
import os
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

# Maps prompt name -> constant name in services.prompts
_PROMPT_REGISTRY = {
    "suggest_title": "SUGGEST_TITLE",
    "generate_characters": "GENERATE_CHARACTERS",
    "generate_world": "GENERATE_WORLD",
    "generate_outline": "GENERATE_OUTLINE",
    "continue_outline": "CONTINUE_OUTLINE",
    "write_chapter": "WRITE_CHAPTER",
    "summarize_chapter": "SUMMARIZE_CHAPTER",
    "extract_character_state": "EXTRACT_CHARACTER_STATE",
    "extract_plot_events": "EXTRACT_PLOT_EVENTS",
    "score_chapter": "SCORE_CHAPTER",
    "analyze_story": "ANALYZE_STORY",
    "agent_persona": "AGENT_PERSONA",
    "evaluate_drama": "EVALUATE_DRAMA",
    "enhance_chapter": "ENHANCE_CHAPTER",
    "drama_suggestions": "DRAMA_SUGGESTIONS",
    "escalation_event": "ESCALATION_EVENT",
    "quick_drama_check": "QUICK_DRAMA_CHECK",
    "reenhance_chapter": "REENHANCE_CHAPTER",
    "rag_context_section": "RAG_CONTEXT_SECTION",
    "extract_chapter_emotions": "EXTRACT_CHAPTER_EMOTIONS",
    "smart_revise_chapter": "SMART_REVISE_CHAPTER",
    "generate_storyboard": "GENERATE_STORYBOARD",
    "generate_voice_script": "GENERATE_VOICE_SCRIPT",
    "character_image_prompt": "CHARACTER_IMAGE_PROMPT",
    "location_image_prompt": "LOCATION_IMAGE_PROMPT",
}


class PromptManager:
    """Loads prompts from YAML files with fallback to hardcoded constants.

    YAML files are optional overlays — if a YAML file exists for a prompt,
    it takes precedence. Otherwise the hardcoded constant in services/prompts/
    is used. This guarantees 100% backward compatibility.
    """

    def __init__(self, prompts_dir: str = "data/prompts") -> None:
        self._prompts_dir = prompts_dir
        # Cache: (prompt_name, version) -> dict payload
        self._cache: dict[tuple[str, str], dict] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, prompt_name: str, version: str = "latest", **kwargs) -> str:
        """Return formatted prompt template.

        Looks up YAML first; falls back to hardcoded constant.
        ``**kwargs`` are passed to ``str.format()``.
        """
        template = self.get_raw(prompt_name, version)
        if not kwargs:
            return template
        try:
            return template.format(**kwargs)
        except KeyError as exc:
            logger.warning(
                "Prompt '%s' missing variable %s — returning unformatted template",
                prompt_name,
                exc,
            )
            return template

    def get_raw(self, prompt_name: str, version: str = "latest") -> str:
        """Return unformatted template string."""
        yaml_data = self._load_yaml(prompt_name, version)
        if yaml_data and "template" in yaml_data:
            return yaml_data["template"]

        hardcoded = self._get_hardcoded(prompt_name)
        if hardcoded is not None:
            return hardcoded

        raise KeyError(
            f"Prompt '{prompt_name}' not found in YAML (version={version}) "
            "or hardcoded constants"
        )

    def list_prompts(self) -> list[dict]:
        """Return list of all registered prompts with metadata."""
        result = []
        for name, const_name in _PROMPT_REGISTRY.items():
            yaml_data = self._load_yaml(name, "latest")
            has_yaml = yaml_data is not None
            entry = {
                "name": name,
                "constant": const_name,
                "source": "yaml" if has_yaml else "hardcoded",
                "version": yaml_data.get("version", "hardcoded") if has_yaml else "hardcoded",
                "has_variants": has_yaml,
                "description": yaml_data.get("description", "") if has_yaml else "",
            }
            result.append(entry)
        return result

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _resolve_version(self, version: str) -> str:
        """Resolve 'latest' to the newest available version directory."""
        if version != "latest":
            return version
        base = self._prompts_dir
        try:
            dirs = [
                d for d in os.listdir(base)
                if os.path.isdir(os.path.join(base, d))
            ]
        except FileNotFoundError:
            return "v1"
        if not dirs:
            return "v1"
        # Sort version dirs (v1 < v2 …) by stripping leading 'v' and comparing ints
        def _ver_key(d: str) -> int:
            try:
                return int(d.lstrip("v"))
            except ValueError:
                return 0
        dirs.sort(key=_ver_key, reverse=True)
        return dirs[0]

    def _load_yaml(self, prompt_name: str, version: str) -> Optional[dict]:
        """Load prompt from ``data/prompts/{version}/{prompt_name}.yaml``.

        Returns None if the file doesn't exist or can't be parsed.
        """
        resolved = self._resolve_version(version)
        cache_key = (prompt_name, resolved)
        if cache_key in self._cache:
            return self._cache[cache_key]

        path = os.path.join(self._prompts_dir, resolved, f"{prompt_name}.yaml")
        if not os.path.isfile(path):
            self._cache[cache_key] = None  # type: ignore[assignment]
            return None

        try:
            with open(path, encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
            self._cache[cache_key] = data
            return data
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to load YAML prompt '%s': %s", path, exc)
            self._cache[cache_key] = None  # type: ignore[assignment]
            return None

    def _get_hardcoded(self, prompt_name: str) -> Optional[str]:
        """Import prompt constant from services.prompts module."""
        const_name = _PROMPT_REGISTRY.get(prompt_name)
        if not const_name:
            return None
        try:
            module = importlib.import_module("services.prompts")
            return getattr(module, const_name, None)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not import hardcoded prompt '%s': %s", const_name, exc)
            return None


# Module-level singleton
prompt_manager = PromptManager()
