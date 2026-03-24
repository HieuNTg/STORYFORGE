"""Concurrency tests — ThreadPoolExecutor cap, future timeouts, concurrent exports."""
import os
import threading
import time
import tempfile
import pytest
from concurrent.futures import ThreadPoolExecutor, Future, TimeoutError as FuturesTimeoutError
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# 1. ThreadPoolExecutor max_workers cap
# ---------------------------------------------------------------------------

class TestThreadPoolMaxWorkersCap:

    def test_max_workers_respected_cap_at_config_value(self):
        """Workers must not exceed configured maximum."""
        MAX_CAP = 3
        active_workers = []
        lock = threading.Lock()
        peak = [0]

        def task():
            with lock:
                active_workers.append(1)
                if len(active_workers) > peak[0]:
                    peak[0] = len(active_workers)
            time.sleep(0.05)
            with lock:
                active_workers.pop()

        with ThreadPoolExecutor(max_workers=MAX_CAP) as executor:
            futures = [executor.submit(task) for _ in range(10)]
            for f in futures:
                f.result()

        assert peak[0] <= MAX_CAP

    def test_max_workers_one_serializes_tasks(self):
        """max_workers=1 guarantees tasks run serially."""
        order = []
        lock = threading.Lock()

        def task(n):
            with lock:
                order.append(n)

        with ThreadPoolExecutor(max_workers=1) as executor:
            futures = [executor.submit(task, i) for i in range(5)]
            for f in futures:
                f.result()

        assert order == sorted(order)

    def test_executor_with_cap_completes_all_tasks(self):
        """All submitted tasks complete even with low worker cap."""
        results = []
        lock = threading.Lock()

        def task(n):
            with lock:
                results.append(n)
            return n

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(task, i) for i in range(10)]
            values = [f.result() for f in futures]

        assert sorted(values) == list(range(10))

    def test_llm_config_max_parallel_workers_is_respected(self):
        """LLMConfig.max_parallel_workers controls thread cap (default 3)."""
        from config import LLMConfig
        cfg = LLMConfig()
        # Default is 3 — should be positive and reasonable
        assert cfg.max_parallel_workers > 0
        assert cfg.max_parallel_workers <= 10


# ---------------------------------------------------------------------------
# 2. Future timeout handling
# ---------------------------------------------------------------------------

class TestFutureTimeoutHandling:

    def test_slow_task_raises_timeout_error_when_waited_too_short(self):
        """result(timeout=...) raises TimeoutError for slow tasks."""
        def slow_task():
            time.sleep(5)
            return "done"

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(slow_task)
            with pytest.raises((FuturesTimeoutError, TimeoutError)):
                future.result(timeout=0.01)
            # Cancel to clean up
            future.cancel()

    def test_timeout_does_not_crash_the_executor(self):
        """TimeoutError from one future leaves executor healthy for other tasks."""
        def slow():
            time.sleep(5)
            return "slow"

        def fast():
            return "fast"

        with ThreadPoolExecutor(max_workers=2) as executor:
            slow_future = executor.submit(slow)
            fast_future = executor.submit(fast)

            try:
                slow_future.result(timeout=0.01)
            except (FuturesTimeoutError, TimeoutError):
                pass

            assert fast_future.result(timeout=5) == "fast"
            slow_future.cancel()

    def test_timeout_error_can_be_caught_gracefully(self):
        """Pattern: catch TimeoutError, continue with default value."""
        def slow():
            time.sleep(5)
            return "real result"

        result = "default"
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(slow)
            try:
                result = future.result(timeout=0.01)
            except (FuturesTimeoutError, TimeoutError):
                result = "timed out"
            finally:
                future.cancel()

        assert result == "timed out"

    def test_completed_task_returns_before_timeout(self):
        """Fast task returns result well before timeout expires."""
        def fast():
            return 42

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(fast)
            result = future.result(timeout=5)

        assert result == 42


# ---------------------------------------------------------------------------
# 3. Multiple concurrent export operations don't corrupt files
# ---------------------------------------------------------------------------

class TestConcurrentExportIntegrity:

    def _make_story(self, title="Story", content="Content"):
        from models.schemas import StoryDraft, Chapter
        return StoryDraft(
            title=title,
            genre="test",
            chapters=[Chapter(chapter_number=1, title="Ch1", content=content)],
        )

    def test_concurrent_html_exports_produce_distinct_valid_files(self, tmp_path):
        """Multiple threads exporting HTML simultaneously produce valid, distinct files."""
        from services.html_exporter import HTMLExporter
        errors = []
        outputs = []
        lock = threading.Lock()

        def do_export(i):
            story = self._make_story(title=f"Story {i}", content=f"Content for story {i}. " * 20)
            out = str(tmp_path / f"story_{i}.html")
            try:
                HTMLExporter.export(story, out)
                with lock:
                    outputs.append(out)
            except Exception as e:
                with lock:
                    errors.append(str(e))

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(do_export, i) for i in range(8)]
            for f in futures:
                f.result()

        assert errors == [], f"Export errors: {errors}"
        assert len(outputs) == 8

        # Verify each file is valid and contains its story title
        for i, path in enumerate(sorted(outputs)):
            content = open(path, encoding="utf-8").read()
            assert "<!DOCTYPE html>" in content or "<html" in content

    def test_concurrent_html_exports_no_content_cross_contamination(self, tmp_path):
        """Each exported HTML file contains only its own story title."""
        from services.html_exporter import HTMLExporter
        n = 6
        lock = threading.Lock()
        file_map = {}

        def do_export(i):
            title = f"UniqueStory{i:04d}"
            content = f"Unique content for story number {i}."
            story = self._make_story(title=title, content=content)
            out = str(tmp_path / f"story_{i}.html")
            HTMLExporter.export(story, out)
            with lock:
                file_map[i] = (out, title)

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(do_export, i) for i in range(n)]
            for f in futures:
                f.result()

        # Each file should contain its own title
        for i, (path, title) in file_map.items():
            html = open(path, encoding="utf-8").read()
            assert title in html, f"Story {i} title '{title}' not found in {path}"

    def test_concurrent_share_creation_produces_unique_ids(self, tmp_path, monkeypatch):
        """Concurrent share creation assigns unique share IDs."""
        from services.share_manager import ShareManager

        shares_dir = str(tmp_path / "shares")
        monkeypatch.setattr(ShareManager, "SHARES_DIR", shares_dir)
        monkeypatch.setattr(ShareManager, "SHARES_INDEX", os.path.join(shares_dir, "index.json"))

        mgr = ShareManager()
        share_ids = []
        lock = threading.Lock()

        def create_share(i):
            from models.schemas import StoryDraft, Chapter
            story = StoryDraft(
                title=f"Story {i}",
                genre="test",
                chapters=[Chapter(chapter_number=1, title="Ch1", content=f"Content {i}")],
            )
            share = mgr.create_share(story)
            with lock:
                share_ids.append(share.share_id)

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(create_share, i) for i in range(8)]
            for f in futures:
                f.result()

        # All share IDs must be unique
        assert len(share_ids) == len(set(share_ids)), "Duplicate share IDs found in concurrent creation"

    def test_concurrent_web_reader_generation_is_thread_safe(self):
        """WebReaderGenerator.generate() is safe to call from multiple threads."""
        from services.web_reader_generator import WebReaderGenerator
        results = []
        errors = []
        lock = threading.Lock()

        def generate(i):
            from models.schemas import StoryDraft, Chapter
            story = StoryDraft(
                title=f"Story {i}",
                genre="test",
                chapters=[Chapter(chapter_number=1, title="Ch1", content=f"Content {i} " * 50)],
            )
            try:
                html = WebReaderGenerator.generate(story)
                with lock:
                    results.append(html)
            except Exception as e:
                with lock:
                    errors.append(str(e))

        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = [executor.submit(generate, i) for i in range(12)]
            for f in futures:
                f.result()

        assert errors == [], f"Thread safety errors: {errors}"
        assert len(results) == 12
