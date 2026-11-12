"""Deterministic concurrency checks for tests — no wall-clock bounds.

A test that asserts "this took less than 0.35 s" measures the machine as much as
the code, and fails on a loaded CI runner. These helpers check the structure
instead: how many calls were in flight at the same time.
"""

from __future__ import annotations

import threading


class InFlightProbe:
    """Count how many calls are in flight at once.

    Wrap the body of a fake in ``with probe:``. Each call holds until
    ``rendezvous`` calls are in flight together, then all of them proceed. A
    concurrent implementation reaches the rendezvous at once, so the test never
    sleeps. A serial one never reaches it: each call gives up after ``timeout``
    and ``peak`` stays at 1, so the assertion fails rather than the test hanging.

    Two uses:

    * Proving concurrency: set ``rendezvous`` at or below the worker limit and
      assert ``peak`` reached it. A correct implementation never waits.
    * Proving a bound: set ``rendezvous`` to limit + 1 with a short
      ``timeout`` and assert ``peak == limit``. Every call then stays in
      flight until the timeout, so an unbounded pool is guaranteed to pile up
      more than ``limit`` calls; a bounded one pays ``timeout`` per batch.
    """

    def __init__(self, rendezvous: int = 2, timeout: float = 10.0) -> None:
        self.rendezvous = rendezvous
        self.timeout = timeout
        self.peak = 0
        self._live = 0
        self._lock = threading.Lock()
        self._reached = threading.Event()

    def __enter__(self) -> "InFlightProbe":
        with self._lock:
            self._live += 1
            self.peak = max(self.peak, self._live)
            if self._live >= self.rendezvous:
                self._reached.set()
        self._reached.wait(self.timeout)
        return self

    def __exit__(self, *exc) -> None:
        with self._lock:
            self._live -= 1
