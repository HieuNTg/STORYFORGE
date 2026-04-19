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
    # Role override — require imperative-to-assistant context, not narrative prose
    (re.compile(r"(?:^|[.!?]\s+)you\s+are\s+(?:now\s+)?(?:no\s+longer\s+)?(?:a\s+)?(?:\w+\s+){0,2}(?:ai|assistant|model|chatbot|system|llm|gpt|claude|bot)\b", re.IGNORECASE), "role_override"),
    (re.compile(r"(?:^|[.!?]\s+)(?:act|behave|pretend|roleplay)\s+as\s+(?:a\s+)?(?:different|new)\s+(?:assistant|ai|model|chatbot|system|llm|gpt|claude|bot)", re.IGNORECASE), "role_override"),
    # Instruction injection
    (re.compile(r"\[(?:SYSTEM|INST|ADMIN)\]", re.IGNORECASE), "tag_injection"),
    (re.compile(r"<\|(?:im_start|system|endoftext)\|>", re.IGNORECASE), "token_injection"),
    # Output manipulation
    (re.compile(r"(?:do\s+not|don'?t|never)\s+(?:score|rate|evaluate|check|validate)", re.IGNORECASE), "scoring_bypass"),
    (re.compile(r"(?:skip|bypass|disable)\s+(?:quality|safety|content)\s+(?:check|filter|gate|review)", re.IGNORECASE), "safety_bypass"),
    # Vietnamese patterns — system override (require override-target qualifier)
    (re.compile(r"bỏ\s+qua\s+(?:tất\s+cả\s+)?(?:các\s+)?(?:hướng\s+dẫn|lệnh|quy\s+tắc|chỉ\s+dẫn|prompt)\s+(?:trước(?:\s+đó)?|ở\s+trên|phía\s+trên|bên\s+trên|gốc|ban\s+đầu)", re.IGNORECASE), "system_override"),
    (re.compile(r"(?:hãy\s+)?quên\s+(?:đi\s+)?(?:các\s+)?(?:quy\s+tắc|hướng\s+dẫn|lệnh|ngữ\s+cảnh|prompt|chỉ\s+dẫn)\s+(?:trước(?:\s+đó)?|ở\s+trên|phía\s+trên|bên\s+trên|gốc|ban\s+đầu)", re.IGNORECASE), "system_override"),
    # Vietnamese patterns — role override (require target = assistant/AI/LLM)
    (re.compile(r"(?:hãy\s+)?(?:đóng\s+vai|giả\s+vờ|giả\s+làm)(?:\s+(?:là|bạn\s+là))?\s+(?:một\s+)?(?:trợ\s+lý|AI|mô\s+hình|chatbot|LLM|GPT|Claude|bot|hệ\s+thống\s+AI)", re.IGNORECASE), "role_override"),
    (re.compile(r"bạn\s+không\s+phải\s+tuân\s+theo\s+(?:các\s+)?(?:quy\s+tắc|hướng\s+dẫn|lệnh)", re.IGNORECASE), "role_override"),
    # Vietnamese patterns — scoring bypass (require override-target qualifier)
    (re.compile(r"đừng\s+(?:đánh\s+giá|kiểm\s+tra|chấm\s+điểm)\s+(?:chất\s+lượng\s+)?(?:nội\s+dung|đầu\s+ra|câu\s+trả\s+lời|phản\s+hồi|output|câu\s+chuyện|truyện)", re.IGNORECASE), "scoring_bypass"),
    # Vietnamese patterns — prompt extraction (require extraction verb)
    (re.compile(r"(?:xuất|hiển\s+thị|tiết\s+lộ|in\s+ra|lặp\s+lại|cho\s+(?:tôi\s+)?xem|nói\s+ra|liệt\s+kê)\s+(?:toàn\s+bộ\s+)?(?:prompt|hướng\s+dẫn|quy\s+tắc|chỉ\s+dẫn)(?:\s+(?:hệ\s+thống|system|gốc|ban\s+đầu))?", re.IGNORECASE), "prompt_extraction"),
    (re.compile(r"(?:cho\s+tôi\s+biết|tiết\s+lộ|nói\s+cho\s+tôi)\s+(?:system\s+prompt|prompt\s+hệ\s+thống)", re.IGNORECASE), "prompt_extraction"),
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
