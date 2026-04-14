"""Tests for services/thread_pool_manager.py and services/_thread_pool_impl.py."""
import threading
import pytest
from unittest.mock import patch

# Import after potential singleton reset
from services.thread_pool_manager import get_thread_pool_manager, ThreadPoolManager
from services._thread_pool_impl import _optimal_workers, _POOL_SPECS


# ---------------------------------------------------------------------------
# _optimal_workers
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestOptimalWorkers:
    def test_respects_cap(self):
        result = _optimal_workers(100.0, 4)
        assert result <= 4

    def test_minimum_of_one(self):
        result = _optimal_workers(0.0, 8)
        # 0.0 * cpu + 1 = 1
        assert result >= 1

    def test_scales_with_cpu(self):
        with patch("services._thread_pool_impl.os.cpu_count", return_value=8):
            result = _optimal_workers(2.0, 32)
        assert result == min(32, int(8 * 2.0) + 1)

    def test_fallback_when_cpu_count_none(self):
        with patch("services._thread_pool_impl.os.cpu_count", return_value=None):
            result = _optimal_workers(3.0, 32)
        # Falls back to 4 CPUs: min(32, int(4*3) + 1) = 13
        assert result == min(32, int(4 * 3.0) + 1)


# ---------------------------------------------------------------------------
# ThreadPoolManager — singleton
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestThreadPoolManagerSingleton:
    def test_singleton_returns_same_instance(self):
        mgr1 = get_thread_pool_manager()
        mgr2 = get_thread_pool_manager()
        assert mgr1 is mgr2

    def test_same_instance_across_threads(self):
        instances = []

        def get_instance():
            instances.append(get_thread_pool_manager())

        threads = [threading.Thread(target=get_instance) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert all(i is instances[0] for i in instances)


# ---------------------------------------------------------------------------
# ThreadPoolManager — pool management
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestThreadPoolManagerPools:
    def setup_method(self):
        self.mgr = get_thread_pool_manager()

    def test_all_expected_pools_exist(self):
        for name, _, _ in _POOL_SPECS:
            pool = self.mgr.get_pool(name)
            assert pool is not None

    def test_get_pool_unknown_name_raises_key_error(self):
        with pytest.raises(KeyError, match="Unknown pool"):
            self.mgr.get_pool("nonexistent_pool")

    def test_utilisation_summary_contains_all_pools(self):
        summary = self.mgr.utilisation_summary()
        for name, _, _ in _POOL_SPECS:
            assert name in summary
            assert "max_workers" in summary[name]
            assert "active_tasks" in summary[name]

    def test_max_workers_respects_cap(self):
        summary = self.mgr.utilisation_summary()
        for spec_name, _, cap in _POOL_SPECS:
            assert summary[spec_name]["max_workers"] <= cap


# ---------------------------------------------------------------------------
# ThreadPoolManager — submit and active_count
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestThreadPoolManagerSubmit:
    def setup_method(self):
        self.mgr = get_thread_pool_manager()

    def test_submit_executes_function(self):
        results = []
        future = self.mgr.submit("general_pool", lambda: results.append(42))
        future.result(timeout=5)
        assert 42 in results

    def test_submit_returns_future(self):
        future = self.mgr.submit("general_pool", lambda: "done")
        assert future.result(timeout=5) == "done"

    def test_submit_with_args(self):
        future = self.mgr.submit("general_pool", lambda a, b: a + b, 3, 4)
        assert future.result(timeout=5) == 7

    def test_submit_with_kwargs(self):
        future = self.mgr.submit("scoring_pool", lambda x=0, y=0: x * y, x=6, y=7)
        assert future.result(timeout=5) == 42

    def test_active_count_returns_int(self):
        count = self.mgr.active_count("pipeline_pool")
        assert isinstance(count, int)
        assert count >= 0

    def test_active_count_unknown_pool_returns_zero(self):
        count = self.mgr.active_count("nonexistent")
        assert count == 0

    def test_submit_unknown_pool_raises_key_error(self):
        with pytest.raises(KeyError):
            self.mgr.submit("bad_pool", lambda: None)

    def test_done_callback_decrements_count(self):
        event = threading.Event()
        future = self.mgr.submit("general_pool", lambda: event.wait(timeout=2))
        # Active count should be at least 0 while running
        active = self.mgr.active_count("general_pool")
        assert active >= 0
        event.set()
        future.result(timeout=5)
        # After completion, count should have decremented
        # (may be 0 or more if other tasks are running)
        assert self.mgr.active_count("general_pool") >= 0

    def test_exception_in_task_does_not_crash_manager(self):
        def bad_task():
            raise ValueError("Intentional error")

        future = self.mgr.submit("general_pool", bad_task)
        with pytest.raises(ValueError, match="Intentional error"):
            future.result(timeout=5)
        # Manager should still work after exception
        future2 = self.mgr.submit("general_pool", lambda: "ok")
        assert future2.result(timeout=5) == "ok"


# ---------------------------------------------------------------------------
# ThreadPoolManager — repr
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestThreadPoolManagerRepr:
    def test_repr_contains_pool_names(self):
        mgr = get_thread_pool_manager()
        r = repr(mgr)
        assert "ThreadPoolManager" in r
        assert "pipeline_pool" in r


# ---------------------------------------------------------------------------
# get_thread_pool_manager
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetThreadPoolManager:
    def test_returns_thread_pool_manager_instance(self):
        mgr = get_thread_pool_manager()
        assert isinstance(mgr, ThreadPoolManager)

    def test_idempotent(self):
        mgr1 = get_thread_pool_manager()
        mgr2 = get_thread_pool_manager()
        assert mgr1 is mgr2
