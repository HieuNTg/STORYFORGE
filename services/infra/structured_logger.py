"""Structured JSON logging for StoryForge.

Usage: LOG_FORMAT=json for JSON output, LOG_FORMAT=text (default) for human-readable.
"""
import json
import logging
import os
import sys
from datetime import datetime, timezone


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

    root.addHandler(handler)
    # File handler always uses text format for readability
    file_handler = logging.FileHandler("storyforge.log", encoding="utf-8")
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    ))
    root.addHandler(file_handler)
