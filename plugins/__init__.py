"""StoryForge plugin system.

Public API:
    StoryForgePlugin  — base class for all plugins
    PluginManager     — loader + hook dispatcher
    plugin_manager    — module-level singleton (call load_all() once at startup)

Usage:
    from plugins import plugin_manager

    plugin_manager.load_all()
    rules   = plugin_manager.apply_genre_rules(genre, rules)
    scores  = plugin_manager.apply_score(scores)
    data    = plugin_manager.apply_export(fmt, data)
"""

from plugins.base import StoryForgePlugin
from plugins.loader import PluginManager, plugin_manager

__all__ = ["StoryForgePlugin", "PluginManager", "plugin_manager"]
