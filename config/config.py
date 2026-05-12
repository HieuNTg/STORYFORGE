"""Main ConfigManager — thin singleton orchestrator."""

import logging
import threading

from .defaults import LLMConfig, PipelineConfig
from .validation import validate_config
from .persistence import load_config, save_config

logger = logging.getLogger(__name__)


class ConfigManager:
    """Singleton quản lý cấu hình (thread-safe)."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.llm = LLMConfig()
        self.pipeline = PipelineConfig()
        load_config(self.llm, self.pipeline)

    def validate(self) -> list[str]:
        """Validate config. Returns list of warning messages."""
        return validate_config(self.llm, self.pipeline)

    def load(self) -> "ConfigManager":
        """Backward-compatible accessor used by older call sites."""
        return self

    def save(self) -> list[str]:
        """Save config. Returns warnings. Raises ValueError on critical errors."""
        with self._lock:
            warnings = self.validate()
            critical = [w for w in warnings if "bắt buộc" in w or "phải" in w]
            if critical:
                raise ValueError(f"Config invalid: {'; '.join(critical)}")
            if warnings:
                for w in warnings:
                    logger.warning(f"Config: {w}")
            save_config(self.llm, self.pipeline)
            return warnings
