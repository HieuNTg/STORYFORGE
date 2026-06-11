"""PR-4 #19 regression — per-IP session cap is enforced atomically.

The old code counted live sessions under the lock, released it, built the
orchestrator, then re-acquired the lock to insert. That split made the count and
the insert non-atomic: concurrent same-IP requests could each pass the count
check and then all insert, exceeding ``_MAX_SESSIONS_PER_IP``. The count+insert
now happen under a single lock acquire (``_try_reserve_session``).
"""

import asyncio

import pytest

import api.pipeline_routes as pr


@pytest.fixture(autouse=True)
def _clean_sessions():
    pr._sessions.clear()
    yield
    pr._sessions.clear()


@pytest.mark.asyncio
async def test_concurrent_same_ip_requests_never_exceed_cap():
    n = 10
    ip = "203.0.113.7"

    async def reserve(i):
        # A distinct session_id + sentinel "orchestrator" per caller.
        return await pr._try_reserve_session(f"sess-{i}", object(), ip)

    results = await asyncio.gather(*(reserve(i) for i in range(n)))

    granted = sum(1 for r in results if r)
    assert granted == pr._MAX_SESSIONS_PER_IP
    # And the registry holds exactly the cap — no extra slot slipped through.
    assert (
        sum(1 for (_, _, _ip) in pr._sessions.values() if _ip == ip)
        == pr._MAX_SESSIONS_PER_IP
    )


@pytest.mark.asyncio
async def test_distinct_ips_are_counted_independently():
    # Fill IP A to the cap …
    for i in range(pr._MAX_SESSIONS_PER_IP):
        assert await pr._try_reserve_session(f"a-{i}", object(), "10.0.0.1") is True
    # … A is now rejected …
    assert await pr._try_reserve_session("a-overflow", object(), "10.0.0.1") is False
    # … but a different IP still gets its own quota.
    assert await pr._try_reserve_session("b-0", object(), "10.0.0.2") is True


@pytest.mark.asyncio
async def test_slot_frees_up_after_eviction():
    ip = "198.51.100.5"
    for i in range(pr._MAX_SESSIONS_PER_IP):
        assert await pr._try_reserve_session(f"s-{i}", object(), ip) is True
    assert await pr._try_reserve_session("s-extra", object(), ip) is False

    # Evicting one (as the reaper would) frees a slot.
    pr._sessions.pop("s-0", None)
    assert await pr._try_reserve_session("s-new", object(), ip) is True
