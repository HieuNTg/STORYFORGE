"""PluginManager — loads and dispatches hooks to registered plugins.

Separated from __init__.py so the manager can be imported without triggering
auto-load side-effects (e.g. in tests or when the caller wants to control
when plugins are loaded).

Usage:
    from plugins.loader import plugin_manager

    plugin_manager.load_all()               # call once at startup
    rules = plugin_manager.apply_genre_rules(genre, rules)
    scores = plugin_manager.apply_score(scores)
    data   = plugin_manager.apply_export(fmt, data)
"""

from __future__ import annotations

import importlib.util
import logging
import sys
from pathlib import Path
from typing import Any

from plugins.base import StoryForgePlugin

logger = logging.getLogger(__name__)

_PLUGINS_DIR = Path(__file__).parent


class PluginManager:
    """Loads and dispatches hooks to all registered plugins."""

    def __init__(self) -> None:
        self._plugins: list[StoryForgePlugin] = []
        self._loaded = False

    def load_all(self, directory: Path = _PLUGINS_DIR) -> None:
        """Scan directory for plugin modules and register StoryForgePlugin subclasses.

        Idempotent: calling more than once is a no-op (plugins won't be double-loaded).
        """
        if self._loaded:
            return
        self._loaded = True

        for path in sorted(directory.glob("*.py")):
            # Skip loader infrastructure files
            if path.stem in ("__init__", "base", "loader"):
                continue
            self._load_file(path)
        logger.info("plugin_manager: %d plugin(s) loaded", len(self._plugins))

    def _load_file(self, path: Path) -> None:
        """Import a single plugin file and register any StoryForgePlugin subclasses."""
        module_name = f"plugins._dyn_{path.stem}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, path)
            if spec is None or spec.loader is None:
                logger.warning("plugin_manager: cannot load spec for %s", path)
                return
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)  # type: ignore[attr-defined]
        except Exception as exc:
            logger.error("plugin_manager: failed to import %s — %s", path.name, exc)
            return

        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type)
                and issubclass(attr, StoryForgePlugin)
                and attr is not StoryForgePlugin
            ):
                try:
                    instance = attr()
                    instance.register()
                    self._plugins.append(instance)
                    logger.info(
                        "plugin_manager: registered '%s' v%s from %s",
                        instance.name, instance.version, path.name,
                    )
                except Exception as exc:
                    logger.error(
                        "plugin_manager: register() failed for %s in %s — %s",
                        attr_name, path.name, exc,
                    )

    # ------------------------------------------------------------------
    # Hook dispatchers
    # ------------------------------------------------------------------

    def apply_genre_rules(self, genre: str, rules: dict[str, Any]) -> dict[str, Any]:
        """Run on_genre_rules through all plugins; each may modify the dict."""
        current = rules
        for plugin in self._plugins:
            try:
                result = plugin.on_genre_rules(genre, current)
                if result is not None:
                    current = result
            except Exception as exc:
                logger.warning(
                    "plugin '%s' on_genre_rules raised: %s", plugin.name, exc
                )
        return current

    def apply_score(self, scores: dict[str, float]) -> dict[str, float]:
        """Run on_score through all plugins; each may modify the scores dict."""
        current = scores
        for plugin in self._plugins:
            try:
                result = plugin.on_score(current)
                if result is not None:
                    current = result
            except Exception as exc:
                logger.warning("plugin '%s' on_score raised: %s", plugin.name, exc)
        return current

    def apply_export(self, format: str, data: Any) -> Any:
        """Run on_export through all plugins; each may modify the export data."""
        current = data
        for plugin in self._plugins:
            try:
                result = plugin.on_export(format, current)
                if result is not None:
                    current = result
            except Exception as exc:
                logger.warning(
                    "plugin '%s' on_export raised: %s", plugin.name, exc
                )
        return current

    @property
    def plugins(self) -> list[StoryForgePlugin]:
        """Read-only list of loaded plugin instances."""
        return list(self._plugins)


# Module-level singleton — does NOT auto-load; caller must invoke load_all()
plugin_manager = PluginManager()
