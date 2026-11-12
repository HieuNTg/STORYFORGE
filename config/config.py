"""Main ConfigManager — thin singleton orchestrator."""

import contextlib
import copy
import logging
import threading
from contextvars import ContextVar
from typing import Iterator

from .defaults import LLMConfig, PipelineConfig
from .validation import validate_config
from .persistence import load_config, save_config

logger = logging.getLogger(__name__)

#: The config snapshot of the pipeline run executing in this context, if any.
#: A ContextVar, so it follows awaits and ``asyncio.gather``; thread hops carry
#: it via ``services.llm.run_context`` (``run_in_thread`` & co.).
_active_config: ContextVar["ConfigManager | None"] = ContextVar(
    "_active_config", default=None
)


class ConfigManager:
    """Singleton quản lý cấu hình (thread-safe).

    Inside ``run_scope(cfg)`` the constructor returns ``cfg`` — the run's own
    snapshot — instead of the singleton, so a pipeline run keeps the settings
    it started with even if ``PUT /api/config`` saves new ones mid-run, and
    two concurrent runs never see each other's per-run overrides.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        active = _active_config.get()
        if active is not None:
            return active
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        # Double-checked: the flag flips only once loading is done, so another
        # thread never sees a half-built instance (no ``llm`` yet, or defaults
        # that load_config is about to overwrite). It blocks on the lock instead.
        if self._initialized:
            return
        with self._lock:
            if self._initialized:
                return
            self.llm = LLMConfig()
            self.pipeline = PipelineConfig()
            load_config(self.llm, self.pipeline)
            self._initialized = True

    def snapshot(self) -> "ConfigManager":
        """An independent deep copy of ``llm`` and ``pipeline``.

        Not registered as the singleton. It is born initialised, so
        ``ConfigManager()`` returning it inside ``run_scope`` never reloads
        from disk.
        """
        clone = object.__new__(type(self))
        clone.llm = copy.deepcopy(self.llm)
        clone.pipeline = copy.deepcopy(self.pipeline)
        clone._initialized = True
        return clone

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
            critical = [
                w for w in warnings if "bắt buộc" in w or "phải" in w or "requires" in w
            ]
            if critical:
                raise ValueError(f"Config invalid: {'; '.join(critical)}")
            if warnings:
                for w in warnings:
                    logger.warning(f"Config: {w}")
            save_config(self.llm, self.pipeline)
            return warnings


@contextlib.contextmanager
def run_scope(cfg: ConfigManager) -> Iterator[ConfigManager]:
    """Make ``ConfigManager()`` return ``cfg`` for the duration of the block.

    Nests: the previous scope (or none) is restored on exit, even on error.
    """
    token = _active_config.set(cfg)
    try:
        yield cfg
    finally:
        _active_config.reset(token)
