"""Config package — re-exports for backward compatibility.

All existing imports of the form:
    from config import ConfigManager
    from config import ConfigManager, PIPELINE_PRESETS, MODEL_PRESETS
    from config import LLMConfig, PipelineConfig
continue to work unchanged.
"""

from .config import ConfigManager
from .defaults import LLMConfig, PipelineConfig
from .presets import PIPELINE_PRESETS, MODEL_PRESETS

__all__ = [
    "ConfigManager",
    "LLMConfig",
    "PipelineConfig",
    "PIPELINE_PRESETS",
    "MODEL_PRESETS",
]
