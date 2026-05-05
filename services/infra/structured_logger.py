"""Structured JSON logging for StoryForge.

Usage: LOG_FORMAT=json for JSON output, LOG_FORMAT=text (default) for human-readable.
"""
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone

# Patterns that may contain secrets — scrub values before writing to disk/stdout
_REDACT_KEYS_RE = re.compile(
    r"(Authorization|x-api-key|x-goog-api-key|api_key|OPENAI_API_KEY|ANTHROPIC_API_KEY"
    r"|GOOGLE_AI_API_KEY|ZAI_API_KEY|HF_TOKEN|SEEDREAM_API_KEY)",
    re.IGNORECASE,
)
# Bearer / key values: keep first 4 chars, mask the rest
_SECRET_VALUE_RE = re.compile(
    r"(Bearer\s+|sk-ant-|AIza|sk-or-|sk-proj-|sk-)([A-Za-z0-9\-_\.]{4})([A-Za-z0-9\-_\.]+)"
)


def _redact(text: str) -> str:
    """Replace recognisable secret values in a string with ***REDACTED***."""
    text = _SECRET_VALUE_RE.sub(r"\1\2***REDACTED***", text)
    # key=value / "key": "value" patterns
    text = re.sub(
        r'("(?:' + _REDACT_KEYS_RE.pattern + r')"\\s*:\\s*"?)([^"\\s,}]+)',
        lambda m: m.group(0)[: m.end(0) - len(m.group(m.lastindex))] + "***REDACTED***",
        text,
        flags=re.IGNORECASE,
    )
    return text


class _RedactFilter(logging.Filter):
    """Strip secrets from log record message and exception text."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = _redact(str(record.msg))
        if record.exc_info and record.exc_info[1]:
            # Re-format traceback as plain text and redact; store in exc_text
            import traceback
            tb = "".join(traceback.format_exception(*record.exc_info))
            record.exc_text = _redact(tb)
            record.exc_info = None  # prevent double-formatting
        return True


class JSONFormatter(logging.Formatter):
    """Format log records as single-line JSON."""

    def format(self, record):
        log_entry = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Add extra context fields if present
        for key in ("request_id", "pipeline_run_id", "layer"):
            val = getattr(record, key, None)
            if val is not None:
                log_entry[key] = val
        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry, ensure_ascii=False)


def configure_logging():
    """Configure root logging based on LOG_FORMAT env var."""
    log_format = os.environ.get("LOG_FORMAT", "text").lower()
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    # Remove existing handlers to avoid duplicates
    root.handlers.clear()

    import io
    utf8_stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if log_format == "json":
        handler = logging.StreamHandler(utf8_stdout)
        handler.setFormatter(JSONFormatter())
    else:
        handler = logging.StreamHandler(utf8_stdout)
        handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        ))

    redact = _RedactFilter()
    handler.addFilter(redact)
    root.addHandler(handler)
    # File handler always uses text format for readability
    file_handler = logging.FileHandler("storyforge.log", encoding="utf-8")
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    ))
    file_handler.addFilter(redact)
    root.addHandler(file_handler)
