"""PR-1 regression tests — SSE drain coalescing (C1) + error-reason surfacing (H3).

These guard the two bugs the multi-agent re-review (2026-05-29) found in the SSE
consumer path:

* C1 — the drain loop silently dropped ``log`` frames, breaking the live progress
  UX. ``_drain_and_coalesce`` must preserve every ``log``/``error`` frame in order
  and only collapse *consecutive* ``stream`` snapshots (which are cumulative).
* H3 — failed runs reported the generic "Pipeline produced no output." instead of
  the real reason. ``_error_reason_from_logs`` must recover the logged cause.
"""

import queue as _queue

from api.pipeline_routes import _drain_and_coalesce, _error_reason_from_logs


def _drain(items):
    """Run a list of (type, data) frames through _drain_and_coalesce."""
    q: _queue.Queue = _queue.Queue()
    first = items[0]
    for it in items[1:]:
        q.put_nowait(it)
    return _drain_and_coalesce(q, first)


# --- C1: drain must not drop log frames -------------------------------------

def test_drain_preserves_all_log_frames_in_order():
    items = [("log", "a"), ("log", "b"), ("log", "c")]
    assert _drain(items) == items


def test_drain_keeps_logs_and_collapses_only_consecutive_streams():
    # [log, log, stream, log, stream] -> all logs kept, single trailing stream
    # (the lone streams are not consecutive, so none are dropped here).
    items = [
        ("log", "outline"),
        ("log", "quality"),
        ("stream", "partial-1"),
        ("log", "chapter-1-done"),
        ("stream", "partial-2"),
    ]
    assert _drain(items) == items


def test_drain_collapses_consecutive_streams_to_latest():
    items = [
        ("stream", "s1"),
        ("stream", "s2"),
        ("stream", "s3"),
        ("log", "chapter-done"),
    ]
    # s1 and s2 are superseded by the newer snapshot; s3 (last in the run) + log kept.
    assert _drain(items) == [("stream", "s3"), ("log", "chapter-done")]


def test_drain_preserves_error_frames():
    items = [("log", "a"), ("error", "boom"), ("log", "b")]
    assert _drain(items) == items


def test_drain_single_item():
    assert _drain([("log", "only")]) == [("log", "only")]


def test_drain_trailing_consecutive_streams_keep_last():
    items = [("log", "a"), ("stream", "s1"), ("stream", "s2")]
    assert _drain(items) == [("log", "a"), ("stream", "s2")]


# --- H3: error reason recovery ----------------------------------------------

def test_error_reason_returns_last_nonempty_log():
    logs = ["[OUTLINE] ...", "Không kết nối được LLM: timeout"]
    assert _error_reason_from_logs(logs) == "Không kết nối được LLM: timeout"


def test_error_reason_skips_trailing_blank_lines():
    logs = ["real reason here", "   ", ""]
    assert _error_reason_from_logs(logs) == "real reason here"


def test_error_reason_strips_whitespace():
    logs = ["  spaced reason  "]
    assert _error_reason_from_logs(logs) == "spaced reason"


def test_error_reason_fallback_when_empty():
    assert _error_reason_from_logs([]) == "Pipeline thất bại. Vui lòng thử lại."
    assert _error_reason_from_logs(None) == "Pipeline thất bại. Vui lòng thử lại."


def test_error_reason_custom_fallback():
    assert _error_reason_from_logs([], fallback="x") == "x"
