"""Async-safe audit logger for StoryForge security events.

Writes structured audit records to daily rotating NDJSON log files:
  data/audit/audit-YYYY-MM-DD.json — one JSON object per line.

Log record fields:
  timestamp, user_id, action, resource, ip_address, user_agent, result, details

Design:
  - Non-blocking writes via background daemon thread + queue.Queue
  - Thread-safe singleton (double-checked locking)
  - Retention cleanup runs once at process startup
  - File I/O is delegated to services._audit_store (kept separate for line-count)

Usage:
    from services.audit_logger import get_audit_logger

    log = get_audit_logger()
    log.log_event("login", "/api/auth/login", user_id="uuid", ip="1.2.3.4", result="success")
    events = log.query_events({"user_id": "uuid", "date_from": "2026-04-01"})
"""
import logging
import os
import queue
import threading
from datetime import datetime, timezone
from typing import Optional

from services._audit_store import (
    write_event, list_log_files, read_log_file, cleanup_old_logs
)

logger = logging.getLogger(__name__)

_DEFAULT_RETENTION_DAYS = int(os.environ.get("AUDIT_LOG_RETENTION_DAYS", "90"))
_QUEUE_TIMEOUT = 5  # seconds; writer blocks this long between drain attempts


def _build_event(
    action: str,
    resource: str,
    user_id: Optional[str],
    ip: Optional[str],
    result: str,
    details: Optional[dict],
    user_agent: Optional[str],
) -> dict:
    """Build a normalized audit event dict ready for JSON serialization.

    Args:
        action: Short event label, e.g. "login", "pipeline_run", "export".
        resource: HTTP path or resource identifier.
        user_id: Authenticated user UUID; None for anonymous requests.
        ip: Client IP address; None if unavailable.
        result: "success" | "failure" | "error".
        details: Arbitrary extra context (no PII in production).
        user_agent: HTTP User-Agent header value.

    Returns:
        Dict with all audit fields; timestamp is ISO-8601 UTC string.
    """
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user_id": user_id or "anonymous",
        "action": action,
        "resource": resource,
        "ip_address": ip or "unknown",
        "user_agent": user_agent or "",
        "result": result,
        "details": details or {},
    }


class AuditLogger:
    """Thread-safe, non-blocking audit event logger.

    Writes are enqueued and flushed to disk by a background daemon thread
    so callers are never blocked by disk I/O.
    """

    _instance: Optional["AuditLogger"] = None
    _init_lock = threading.Lock()

    def __new__(cls) -> "AuditLogger":
        """Return process-wide singleton (double-checked locking)."""
        if cls._instance is None:
            with cls._init_lock:
                if cls._instance is None:
                    inst = super().__new__(cls)
                    inst._queue: queue.Queue = queue.Queue()
                    inst._write_lock = threading.Lock()
                    inst._retention_days = _DEFAULT_RETENTION_DAYS
                    inst._started = False
                    cls._instance = inst
        return cls._instance

    # ------------------------------------------------------------------
    # Background writer
    # ------------------------------------------------------------------

    def _start_writer(self) -> None:
        """Start background writer daemon thread and trigger initial cleanup."""
        if self._started:
            return
        t = threading.Thread(target=self._writer_loop, daemon=True, name="audit-writer")
        t.start()
        self._started = True
        # Kick off retention cleanup on a separate thread to avoid blocking start
        threading.Thread(target=self.cleanup_old_logs, daemon=True, name="audit-cleanup").start()

    def _writer_loop(self) -> None:
        """Drain event queue and write events to disk. Runs forever."""
        while True:
            try:
                event = self._queue.get(timeout=_QUEUE_TIMEOUT)
                write_event(event, self._write_lock)
                self._queue.task_done()
            except queue.Empty:
                continue
            except Exception as exc:
                logger.error(f"Audit writer error: {exc}")

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def log_event(
        self,
        action: str,
        resource: str,
        user_id: Optional[str] = None,
        ip: Optional[str] = None,
        result: str = "success",
        details: Optional[dict] = None,
        user_agent: Optional[str] = None,
    ) -> None:
        """Enqueue an audit event for non-blocking disk write.

        Args:
            action: Event type label (e.g. "login", "pipeline_run", "export").
            resource: HTTP path or resource identifier.
            user_id: Authenticated user UUID; None for anonymous.
            ip: Client IP address; None if unavailable.
            result: "success" | "failure" | "error".
            details: Optional dict with extra context.
            user_agent: HTTP User-Agent header value.
        """
        if not self._started:
            self._start_writer()
        event = _build_event(action, resource, user_id, ip, result, details, user_agent)
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            logger.warning("Audit queue full — dropping event %s %s", action, resource)

    def query_events(self, filters: Optional[dict] = None) -> list[dict]:
        """Search audit log files and return matching events.

        Supported filter keys:
            date_from (str): "YYYY-MM-DD" — earliest log file to scan.
            date_to (str): "YYYY-MM-DD" — latest log file to scan.
            user_id, action, result, ip_address — exact-match field filters.

        Args:
            filters: Dict of filter conditions (all ANDed). None = no filter.

        Returns:
            List of matching audit event dicts, ordered oldest-first.
        """
        filters = filters or {}
        date_from = filters.get("date_from")
        date_to = filters.get("date_to")
        field_filters = {k: v for k, v in filters.items() if k not in ("date_from", "date_to")}
        results: list[dict] = []
        for path in list_log_files(date_from, date_to):
            results.extend(read_log_file(path, field_filters))
        return results

    def cleanup_old_logs(self) -> int:
        """Delete audit log files older than the configured retention period.

        Returns:
            Number of log files deleted.
        """
        return cleanup_old_logs(self._retention_days)


def get_audit_logger() -> AuditLogger:
    """Return the process-wide AuditLogger singleton.

    Returns:
        AuditLogger instance ready for use.
    """
    return AuditLogger()
