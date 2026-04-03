"""Input sanitization against prompt injection attacks.

Detects common injection patterns in user-provided story ideas,
character descriptions, and other text inputs before they're
used in LLM prompt construction.

Blocking behavior is ON by default. Set STORYFORGE_BLOCK_INJECTION=false to disable.
"""
import os
import re
import logging

logger = logging.getLogger(__name__)

# Secure by default: block when threat detected unless explicitly disabled
_BLOCK_ON_DETECT = os.environ.get("STORYFORGE_BLOCK_INJECTION", "true").lower() != "false"

# Patterns that indicate prompt injection attempts
_INJECTION_PATTERNS = [
    # System prompt extraction
    (re.compile(r"(?:ignore|forget|disregard)\s+(?:all\s+)?(?:previous|prior|above)\s+(?:instructions?|prompts?|rules?|context)", re.IGNORECASE), "system_override"),
    (re.compile(r"(?:what|show|reveal|repeat|print|output)\s+(?:is\s+)?(?:your|the|my)\s+(?:system\s+)?(?:prompt|instructions?|rules?)", re.IGNORECASE), "prompt_extraction"),
    # Role override
    (re.compile(r"you\s+are\s+(?:now|no\s+longer)\s+a", re.IGNORECASE), "role_override"),
    (re.compile(r"(?:act|behave|pretend|roleplay)\s+as\s+(?:a\s+)?(?:different|new)", re.IGNORECASE), "role_override"),
    # Instruction injection
    (re.compile(r"\[(?:SYSTEM|INST|ADMIN)\]", re.IGNORECASE), "tag_injection"),
    (re.compile(r"<\|(?:im_start|system|endoftext)\|>", re.IGNORECASE), "token_injection"),
    # Output manipulation
    (re.compile(r"(?:do\s+not|don'?t|never)\s+(?:score|rate|evaluate|check|validate)", re.IGNORECASE), "scoring_bypass"),
    (re.compile(r"(?:skip|bypass|disable)\s+(?:quality|safety|content)\s+(?:check|filter|gate|review)", re.IGNORECASE), "safety_bypass"),
]


class SanitizationResult:
    """Result of input sanitization check."""
    __slots__ = ("is_safe", "cleaned_text", "threats_found")

    def __init__(self, is_safe: bool, cleaned_text: str, threats_found: list[str]):
        self.is_safe = is_safe
        self.cleaned_text = cleaned_text
        self.threats_found = threats_found


class InjectionBlockedError(ValueError):
    """Raised when prompt injection is detected and blocking is enabled."""


def sanitize_input(text: str) -> SanitizationResult:
    """Check text for injection patterns. Returns sanitization result.

    When _BLOCK_ON_DETECT is True (default), raises InjectionBlockedError on threat.
    Set STORYFORGE_BLOCK_INJECTION=false env var to disable blocking (log-only mode).
    """
    if not text or not text.strip():
        return SanitizationResult(True, text, [])

    threats = []
    for pattern, threat_type in _INJECTION_PATTERNS:
        if pattern.search(text):
            threats.append(threat_type)
            logger.warning(f"Prompt injection detected: {threat_type}")

    if threats and _BLOCK_ON_DETECT:
        raise InjectionBlockedError(
            f"Input blocked: prompt injection detected ({', '.join(threats)})"
        )

    return SanitizationResult(
        is_safe=len(threats) == 0,
        cleaned_text=text,
        threats_found=threats,
    )


def sanitize_story_input(title: str = "", idea: str = "", genre: str = "") -> SanitizationResult:
    """Sanitize all story creation inputs combined."""
    combined = f"{title} {idea} {genre}"
    return sanitize_input(combined)
