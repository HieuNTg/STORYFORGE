"""Unit tests for services/audit_logger.py and services/_audit_store.py.

The store is exercised against a tmp_path audit dir; the logger's
singleton is reset around each test and its background writer thread is
suppressed so tests stay deterministic.
"""

from __future__ import annotations

import json
import threading
from unittest.mock import patch

import pytest

import services._audit_store as audit_store
from services._audit_store import (
    audit_log_path,
    cleanup_old_logs,
    list_log_files,
    read_log_file,
    write_event,
)
from services.audit_logger import AuditLogger, _build_event, get_audit_logger


@pytest.fixture
def audit_dir(tmp_path, monkeypatch):
    path = tmp_path / "audit"
    monkeypatch.setattr(audit_store, "_AUDIT_DIR", str(path))
    return path


@pytest.fixture
def fresh_logger():
    """Provide an isolated AuditLogger singleton with the writer thread off."""
    saved = AuditLogger._instance
    AuditLogger._instance = None
    logger = AuditLogger()
    logger._started = True  # suppress background writer + cleanup threads
    yield logger
    AuditLogger._instance = saved


class TestBuildEvent:
    def test_fills_anonymous_defaults(self):
        event = _build_event(
            "login", "/api/auth/login", None, None, "failure", None, None
        )
        assert event["user_id"] == "anonymous"
        assert event["ip_address"] == "unknown"
        assert event["user_agent"] == ""
        assert event["details"] == {}
        assert event["result"] == "failure"
        assert event["timestamp"].endswith("+00:00")  # ISO-8601 UTC

    def test_preserves_provided_fields(self):
        event = _build_event(
            "export",
            "/api/stories/1",
            "u-1",
            "1.2.3.4",
            "success",
            {"fmt": "epub"},
            "UA",
        )
        assert event["user_id"] == "u-1"
        assert event["details"] == {"fmt": "epub"}


class TestAuditStore:
    def test_write_then_read_roundtrip(self, audit_dir):
        lock = threading.Lock()
        write_event({"action": "login", "user_id": "u-1"}, lock)
        write_event({"action": "export", "user_id": "u-2"}, lock)
        events = read_log_file(audit_log_path(), {})
        assert [e["action"] for e in events] == ["login", "export"]

    def test_read_applies_field_filters_and_skips_garbage(self, audit_dir):
        audit_dir.mkdir(parents=True)
        path = audit_dir / "audit-2026-06-01.json"
        path.write_text(
            json.dumps({"action": "login", "user_id": "u-1"})
            + "\nkhông phải json\n\n"
            + json.dumps({"action": "login", "user_id": "u-2"})
            + "\n",
            encoding="utf-8",
        )
        events = read_log_file(str(path), {"user_id": "u-2"})
        assert events == [{"action": "login", "user_id": "u-2"}]

    def test_list_log_files_respects_date_range(self, audit_dir):
        audit_dir.mkdir(parents=True)
        for day in ("2026-06-01", "2026-06-05", "2026-06-10"):
            (audit_dir / f"audit-{day}.json").write_text("", encoding="utf-8")
        (audit_dir / "other.txt").write_text("", encoding="utf-8")
        paths = list_log_files("2026-06-02", "2026-06-10")
        assert [p.replace("\\", "/").rsplit("/", 1)[-1] for p in paths] == [
            "audit-2026-06-05.json",
            "audit-2026-06-10.json",
        ]

    def test_list_log_files_missing_dir_returns_empty(self, audit_dir):
        assert list_log_files(None, None) == []

    def test_cleanup_deletes_only_files_past_retention(self, audit_dir):
        audit_dir.mkdir(parents=True)
        (audit_dir / "audit-2000-01-01.json").write_text("", encoding="utf-8")
        recent = audit_log_path()  # today — never past retention
        write_event({"action": "keep"}, threading.Lock())
        assert cleanup_old_logs(retention_days=90) == 1
        assert not (audit_dir / "audit-2000-01-01.json").exists()
        assert read_log_file(recent, {}) == [{"action": "keep"}]


class TestAuditLogger:
    def test_get_audit_logger_returns_singleton(self, fresh_logger):
        assert get_audit_logger() is fresh_logger
        assert AuditLogger() is fresh_logger

    def test_log_event_enqueues_normalized_event(self, fresh_logger):
        fresh_logger.log_event("login", "/api/auth/login", user_id="u-9", ip="5.6.7.8")
        event = fresh_logger._queue.get_nowait()
        assert event["action"] == "login"
        assert event["user_id"] == "u-9"
        assert event["ip_address"] == "5.6.7.8"
        assert event["result"] == "success"

    def test_query_events_scans_files_in_range(self, fresh_logger):
        with (
            patch(
                "services.audit_logger.list_log_files",
                return_value=["a.json", "b.json"],
            ) as mock_list,
            patch(
                "services.audit_logger.read_log_file",
                side_effect=[[{"action": "login"}], [{"action": "export"}]],
            ) as mock_read,
        ):
            events = fresh_logger.query_events(
                {"date_from": "2026-06-01", "date_to": "2026-06-10", "user_id": "u-1"}
            )
        assert [e["action"] for e in events] == ["login", "export"]
        mock_list.assert_called_once_with("2026-06-01", "2026-06-10")
        # date keys must be stripped from field filters
        assert mock_read.call_args_list[0].args == ("a.json", {"user_id": "u-1"})

    def test_cleanup_delegates_with_retention_days(self, fresh_logger):
        with patch(
            "services.audit_logger.cleanup_old_logs", return_value=3
        ) as mock_cleanup:
            assert fresh_logger.cleanup_old_logs() == 3
        mock_cleanup.assert_called_once_with(fresh_logger._retention_days)
