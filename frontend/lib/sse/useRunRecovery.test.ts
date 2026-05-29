/**
 * Tests for useRunRecovery.ts — recovering a running pipeline after the SSE
 * stream is gone (reload mid-run / ECONNRESET).
 *
 * The bug this guards against: PipelineScreen opens the live stream only on a
 * fresh submit, so a remount mid-run left the stepper stuck on "Outline" and
 * the "Hội thoại tác giả" panel empty even though the backend was at chapter N.
 * Recovery must replay job.logs through the same bridge to rebuild that state,
 * then deliver the terminal frame.
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

describe("useRunRecovery", () => {
  it("replays running-job logs to advance the stepper + fill author dialogue, then finishes", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    // Poll 1: job still running, with outline + two chapter-writing lines.
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        session_id: "sess-x",
        status: "running",
        logs: [
          "[OUTLINE] Đang lập dàn ý...",
          "[L1] Đang viết chương 1: Mở đầu...",
          "[L1] Đang viết chương 2: Biến cố...",
        ],
        logs_count: 3,
      }),
    );
    // Poll 2: finished — only the terminal delta + summary.
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        session_id: "sess-x",
        status: "done",
        logs: [],
        logs_count: 3,
        summary: {
          session_id: "sess-x",
          title: "Truyện phục hồi",
          draft: { chapters: [{ number: 1, title: "Chương 1", word_count: 900 }] },
        },
      }),
    );

    const onDone = vi.fn();
    renderHook(() =>
      useRunRecovery({
        sessionId: "sess-x",
        enabled: true,
        pollIntervalMs: 1500,
        handlers: { onDone },
      }),
    );

    // First poll fires immediately (not behind a timer); flush its microtasks.
    await vi.advanceTimersByTimeAsync(0);

    // Stepper advanced to Layer 1 (phase index 1) from the "chương N" lines…
    expect(usePipelineStore.getState().currentPhase).toBe(1);
    // …and the author dialogue is no longer empty.
    expect(useTheaterStore.getState().agents.length).toBeGreaterThan(0);
    // Session id wired for the resume timer.
    expect(usePipelineStore.getState().sessionId).toBe("sess-x");

    // Advance to the scheduled second poll → terminal done.
    await vi.advanceTimersByTimeAsync(1500);

    expect(usePipelineStore.getState().status).toBe("done");
    expect(onDone).toHaveBeenCalledTimes(1);
    expect((onDone.mock.calls[0]![0] as { title?: string }).title).toBe(
      "Truyện phục hồi",
    );

    // Polling stopped after the terminal frame (no third request).
    await vi.advanceTimersByTimeAsync(5000);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("calls onExpired and stops polling on a 404 (session aged out)", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({}, 404));
    vi.stubGlobal("fetch", fetchMock);

    const onExpired = vi.fn();
    renderHook(() =>
      useRunRecovery({ sessionId: "gone", enabled: true, onExpired }),
    );

    await vi.advanceTimersByTimeAsync(0);
    expect(onExpired).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(5000);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("does nothing while disabled (live stream owns the session)", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({}));
    vi.stubGlobal("fetch", fetchMock);

    renderHook(() =>
      useRunRecovery({ sessionId: "sess-y", enabled: false }),
    );

    await vi.advanceTimersByTimeAsync(2000);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
