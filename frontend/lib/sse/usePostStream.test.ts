/**
 * usePostStream: a non-2xx answer on open must reach `onError` with the
 * backend's message (e.g. 400 `api_key_missing` from POST /api/pipeline/run),
 * not a bare "SSE 400".
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { usePostStream } from "./usePostStream";
import { ApiError } from "@/lib/api/client";

type Opts = { onopen: (res: Response) => Promise<void> };

const state = vi.hoisted(() => ({ captured: null as unknown, run: null as Promise<void> | null }));

vi.mock("@microsoft/fetch-event-source", () => ({
  fetchEventSource: vi.fn((_url: string, opts: unknown) => {
    state.captured = opts;
    return Promise.resolve();
  }),
}));

const captured = () => state.captured as Opts;
const body = { idea: "a long enough idea" };

describe("usePostStream", () => {
  beforeEach(() => {
    state.captured = null;
  });

  it("rejects a non-ok open with the backend's error envelope", async () => {
    const onError = vi.fn();
    renderHook(() =>
      usePostStream({ url: "/api/pipeline/run", body, onMessage: () => {}, onError }),
    );
    await waitFor(() => expect(state.captured).not.toBeNull());

    const message = "Set an API key in Settings → API Keys";
    const res = new Response(
      JSON.stringify({ error: { code: "api_key_missing", message } }),
      { status: 400, headers: { "Content-Type": "application/json" } },
    );
    const err = await captured().onopen(res).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).message).toBe(message);
    expect((err as ApiError).code).toBe("api_key_missing");
  });

  it("keeps the status in the message when the body has none", async () => {
    renderHook(() =>
      usePostStream({ url: "/api/pipeline/run", body, onMessage: () => {} }),
    );
    await waitFor(() => expect(state.captured).not.toBeNull());

    const err = await captured()
      .onopen(new Response("", { status: 502 }))
      .catch((e: unknown) => e);
    expect((err as Error).message).toBe("SSE 502");
  });
});
