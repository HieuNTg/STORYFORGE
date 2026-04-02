"""File-system helpers for audit log storage — internal use by audit_logger only.

Handles NDJSON file I/O, date-range file listing, and retention-based cleanup.
Do not import this module directly from outside the services package.

Storage format:
  data/audit/audit-YYYY-MM-DD.json — one JSON object per line (NDJSON).
"""
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

_AUDIT_DIR = os.path.join("data", "audit")


def audit_log_path(date_str: Optional[str] = None) -> str:
    """Return file path for the given UTC date string (YYYY-MM-DD).

    Args:
        date_str: ISO date string. Defaults to today's UTC date.

    Returns:
        Absolute-ish path to the audit log file for that date.
    """
    if date_str is None:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return os.path.join(_AUDIT_DIR, f"audit-{date_str}.json")


def write_event(event: dict, lock) -> None:
    """Append a single audit event to today's NDJSON log file.

    Args:
        event: Audit event dict to serialize as a single JSON line.
        lock: threading.Lock protecting file writes.
    """
    path = audit_log_path()
    os.makedirs(_AUDIT_DIR, exist_ok=True)
    line = json.dumps(event, ensure_ascii=False) + "\n"
    with lock:
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(line)
        except Exception as exc:
            logger.error(f"Failed to write audit event to {path}: {exc}")


def list_log_files(date_from: Optional[str], date_to: Optional[str]) -> list[str]:
    """Return sorted list of audit log file paths within the date range.

    Args:
        date_from: Start date "YYYY-MM-DD" (inclusive). None = no lower bound.
        date_to: End date "YYYY-MM-DD" (inclusive). None = today UTC.

    Returns:
        Sorted list of file paths.
    """
    if not os.path.isdir(_AUDIT_DIR):
        return []
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    date_to = date_to or today_str
    paths = []
    for filename in sorted(os.listdir(_AUDIT_DIR)):
        if not filename.startswith("audit-") or not filename.endswith(".json"):
            continue
        date_part = filename[len("audit-"):-len(".json")]
        if date_from and date_part < date_from:
            continue
        if date_part > date_to:
            continue
        paths.append(os.path.join(_AUDIT_DIR, filename))
    return paths


def read_log_file(path: str, field_filters: dict) -> list[dict]:
    """Read an NDJSON audit log file and return events matching all filters.

    Args:
        path: Path to the audit log file.
        field_filters: Dict of field_name -> required_value; all must match.

    Returns:
        List of matching event dicts.
    """
    results = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if all(event.get(k) == v for k, v in field_filters.items()):
                    results.append(event)
    except Exception as exc:
        logger.warning(f"Failed to read audit log {path}: {exc}")
    return results


def cleanup_old_logs(retention_days: int) -> int:
    """Delete audit log files older than retention_days.

    Args:
        retention_days: Files older than this many days are deleted.

    Returns:
        Number of files deleted.
    """
    if not os.path.isdir(_AUDIT_DIR):
        return 0
    cutoff_str = (datetime.now(timezone.utc) - timedelta(days=retention_days)).strftime("%Y-%m-%d")
    deleted = 0
    for filename in os.listdir(_AUDIT_DIR):
        if not filename.startswith("audit-") or not filename.endswith(".json"):
            continue
        date_part = filename[len("audit-"):-len(".json")]
        try:
            if date_part < cutoff_str:
                os.remove(os.path.join(_AUDIT_DIR, filename))
                deleted += 1
                logger.debug(f"Deleted old audit log: {filename}")
        except Exception as exc:
            logger.warning(f"Failed to delete audit log {filename}: {exc}")
    if deleted:
        logger.info(f"Audit cleanup: removed {deleted} file(s) older than {cutoff_str}")
    return deleted
