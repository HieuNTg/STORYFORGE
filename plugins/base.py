"""Base class for StoryForge plugins.

All plugins should inherit from StoryForgePlugin and override the hook methods
they care about. Unoverridden hooks are no-ops by default so plugins only
implement what they need.
"""

from __future__ import annotations

from typing import Any


class StoryForgePlugin:
    """Abstract base class for StoryForge plugins.

    Lifecycle:
        register() is called once by the plugin loader at startup.
        Each hook is called at the relevant pipeline stage and receives mutable
        data that the plugin may modify in-place or return a replacement for.

    Hook contract:
        - Hooks that return None mean "no change"; the original data is used.
        - Hooks that return a non-None value replace the data for downstream hooks.
        - Exceptions raised in hooks are caught by the loader and logged; the
          pipeline continues with the original data.
    """

    # Human-readable name shown in logs and admin UI
    name: str = "unnamed-plugin"
    version: str = "0.1.0"
    description: str = ""

    def register(self) -> None:
        """Called once on plugin load. Use for setup/validation."""
        pass

    # ------------------------------------------------------------------
    # Hooks
    # ------------------------------------------------------------------

    def on_genre_rules(self, genre: str, rules: dict[str, Any]) -> dict[str, Any] | None:
        """Called before genre drama rules are applied to a chapter.

        Args:
            genre: Genre name string (e.g. "Tiên Hiệp").
            rules: The current rule dict from GENRE_DRAMA_RULES or plugin override.

        Returns:
            Modified rules dict, or None to leave rules unchanged.
        """
        return None

    def on_score(self, scores: dict[str, float]) -> dict[str, float] | None:
        """Called after quality_scorer produces chapter scores.

        Args:
            scores: Dict with keys coherence, character_consistency, drama,
                    writing_quality, overall.

        Returns:
            Modified scores dict, or None to leave scores unchanged.
        """
        return None

    def on_export(self, format: str, data: Any) -> Any | None:
        """Called before story data is serialised to an export format.

        Args:
            format: Export format string, e.g. "epub", "pdf", "html".
            data: The data payload being exported (format-specific structure).

        Returns:
            Modified data, or None to leave data unchanged.
        """
        return None
