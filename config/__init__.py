"""Config package — re-exports for backward compatibility.

All existing imports of the form:
    from config import ConfigManager
    from config import ConfigManager, PIPELINE_PRESETS, PROVIDER_PRESETS
    from config import LLMConfig, PipelineConfig
continue to work unchanged.
"""

import os


def _load_dotenv_once() -> None:
    """Populate os.environ from .env before any config is read.

    Nothing in the backend used to call this, so STORYFORGE_SECRET_KEY was never
    set: secret_manager returned no key, encryption at rest silently did nothing,
    and API keys sat in data/config.json as plaintext. Every entry in
    persistence._ENV_MAP was dead for the same reason, along with
    STORYFORGE_ALLOWED_ORIGINS, REDIS_URL and DATABASE_URL.

    Loading here rather than in app.py covers every entry point — server, MCP
    server, scripts. Existing environment variables always win (load_dotenv does
    not override), so an explicit export still beats the file. Tests set
    STORYFORGE_SKIP_DOTENV to stay hermetic.
    """
    if os.environ.get("STORYFORGE_SKIP_DOTENV"):
        return
    try:
        from dotenv import load_dotenv
    except ImportError:  # optional dependency; env vars still work
        return
    load_dotenv()


_load_dotenv_once()

from .config import ConfigManager  # noqa: E402
from .defaults import LLMConfig, PipelineConfig  # noqa: E402
from .presets import PIPELINE_PRESETS, PROVIDER_PRESETS  # noqa: E402

__all__ = [
    "ConfigManager",
    "LLMConfig",
    "PipelineConfig",
    "PIPELINE_PRESETS",
    "PROVIDER_PRESETS",
]
