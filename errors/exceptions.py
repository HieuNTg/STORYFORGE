"""Typed exceptions for StoryForge."""

__all__ = [
    "StoryForgeError", "ConfigError", "LLMError", "LLMQuotaExhausted",
    "LLMModelNotFound", "PipelineError", "InputSanitizationError",
    "ExportError", "StorageError",
]


class StoryForgeError(Exception):
    """Base exception. All custom exceptions inherit from this."""
    def __init__(self, message: str, code: str = "INTERNAL_ERROR"):
        self.message = message
        self.code = code
        super().__init__(message)


class ConfigError(StoryForgeError):
    def __init__(self, message: str):
        super().__init__(message, code="CONFIG_ERROR")


class LLMError(StoryForgeError):
    def __init__(self, message: str):
        super().__init__(message, code="LLM_ERROR")


class LLMQuotaExhausted(LLMError):
    def __init__(self, provider: str = ""):
        super().__init__(f"LLM quota exhausted{f' ({provider})' if provider else ''}")
        self.code = "LLM_QUOTA_EXHAUSTED"


class LLMModelNotFound(LLMError):
    def __init__(self, model: str = ""):
        super().__init__(f"Model not found{f': {model}' if model else ''}")
        self.code = "LLM_MODEL_NOT_FOUND"


class PipelineError(StoryForgeError):
    def __init__(self, message: str):
        super().__init__(message, code="PIPELINE_ERROR")


class InputSanitizationError(StoryForgeError):
    def __init__(self, threats: list[str]):
        self.threats = threats
        super().__init__(f"Input blocked: {', '.join(threats)}", code="INPUT_BLOCKED")


class ExportError(StoryForgeError):
    def __init__(self, message: str):
        super().__init__(message, code="EXPORT_ERROR")


class StorageError(StoryForgeError):
    def __init__(self, message: str):
        super().__init__(message, code="STORAGE_ERROR")
