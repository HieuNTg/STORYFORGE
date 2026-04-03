# Shim: re-exports from new location for backward compatibility
from services.security.input_sanitizer import (
    SanitizationResult,
    InjectionBlockedError,
    sanitize_input,
    sanitize_story_input,
)

__all__ = ["SanitizationResult", "InjectionBlockedError", "sanitize_input", "sanitize_story_input"]
