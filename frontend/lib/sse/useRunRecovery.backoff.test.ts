/**
 * Regression tests: a backend blip must not orphan a running pipeline.
 *
 * The poller gave up permanently after MAX_CONSECUTIVE_ERRORS (5) failures at a
 * fixed 1.5s cadence — so 7.5 seconds of backend trouble abandoned a 20-minute
 * run while the backend kept generating, with no way back except a manual page
 * reload. It now reports the interruption once and keeps retrying on a widening
 * interval. A 404 (session genuinely gone) still stops the loop.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { renderHook } from "@testing-library/react";
import { useRunRecovery } from "./useRunRecovery";
import { usePipelineStore } from "@/stores/pipeline-store";
import { useTheaterStore } from "@/stores/theater-store";

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as unknown as Response;
}

beforeEach(() => {
  usePipelineStore.getState().reset();
  useTheaterStore.getState().reset();
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

/** Drain pending timers + microtasks a few times so chained polls resolve. */
async function advance(ms: number, rounds = 6) {
  for (let i = 0; i < rounds; i++) {
    await vi.advanceTimersByTimeAsync(ms);
  }
}

describe("useRunRecovery backoff", () => {
  it("keeps polling after more than five consecutive failures", async () => {
    const fetchMock = vi.fn().mockRejectedValue(new Error("network down"));
    vi.stubGlobal("fetch", fetchMock);

    renderHook(() =>
      useRunRecovery({
        sessionId: "sess-blip",
        enabled: true,
        pollIntervalMs: 100,
        handlers: {},
      }),
    );

    // Backoff widens the gap after each failure (100, 200, 400, 800, …), so
    // give it enough virtual time to get past the old give-up threshold of 5.
    await advance(1_000, 12);
    const afterThreshold = fetchMock.mock.calls.length;
    expect(afterThreshold).toBeGreaterThan(5);

    // Backoff is widening, so give it a long window and confirm it is still alive.
    await advance(30_000, 4);
    expect(fetchMock.mock.calls.length).toBeGreaterThan(afterThreshold);
  });

  it("recovers and resumes the normal cadence once the backend returns", async () => {
    const fetchMock = vi.fn();
    for (let i = 0; i < 6; i++) {
      fetchMock.mockRejectedValueOnce(new Error("network down"));
    }
    fetchMock.mockResolvedValue(
      jsonResponse({
        session_id: "sess-blip",
        status: "running",
        logs: ["[L1] Đang viết chương 3..."],
        logs_count: 1,
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    renderHook(() =>
      useRunRecovery({
        sessionId: "sess-blip",
        enabled: true,
        pollIntervalMs: 100,
        handlers: {},
      }),
    );

    await advance(30_000, 8);

    const recovered = fetchMock.mock.results.some((r) => r.type === "return");
    expect(recovered).toBe(true);
    expect(usePipelineStore.getState().status).not.toBe("idle");
  });

  it("still stops for good on 404 — the session is genuinely gone", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({}, 404));
    vi.stubGlobal("fetch", fetchMock);

    const onExpired = vi.fn();
    renderHook(() =>
      useRunRecovery({
        sessionId: "sess-gone",
        enabled: true,
        pollIntervalMs: 100,
        handlers: {},
        onExpired,
      }),
    );

    await advance(100, 3);
    const callsAfterExpiry = fetchMock.mock.calls.length;

    await advance(30_000, 4);

    expect(onExpired).toHaveBeenCalled();
    expect(fetchMock.mock.calls.length).toBe(callsAfterExpiry);
  });
});
