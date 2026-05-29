/**
 * Tests for pipelineBridge.ts — focused on the `done` frame unwrap (PR-4 #17).
 *
 * The backend's done envelope is `{type:"done", data:<summary>}`, but some
 * producers double-wrap it as `{type:"done", data:{data:<summary>}}`. The bridge
 * must unwrap that single extra envelope EXACTLY ONCE so that BOTH downstream
 * consumers receive the same canonical inner summary:
 *   - the theater store via `applyDone({data: inner})`
 *   - the caller via `onDone(inner)`
 * and no consumer has to repeat a `p.data ?? p` dance.
 */

import { describe, it, expect, beforeEach } from "vitest";
import { applySseFrame, type SseFrame } from "./pipelineBridge";
import { useTheaterStore } from "@/stores/theater-store";
import { usePipelineStore } from "@/stores/pipeline-store";

const INNER = {
  session_id: "sess-1",
  title: "Truyện thử",
  draft: {
    chapters: [{ number: 1, title: "Chương 1", word_count: 1200 }],
    characters: [{ name: "Anh Khoa", personality: "điềm tĩnh" }],
  },
  quality: [{ layer: 1, overall: 0.8, name: "tổng thể", value: 0.8 }],
};

beforeEach(() => {
  useTheaterStore.setState({ characters: [], quality: undefined });
  usePipelineStore.setState({ status: "running" });
});

describe("pipelineBridge done-frame unwrap (#17)", () => {
  it("delivers the canonical inner summary to onDone for the current single-wrap shape", () => {
    let received: unknown = null;
    const frame: SseFrame = { type: "done", data: INNER };

    applySseFrame(frame, { onDone: (p) => (received = p) });

    const inner = received as typeof INNER;
    expect(inner.draft.chapters).toHaveLength(1);
    expect(inner.draft.chapters[0].number).toBe(1);
    expect(inner.session_id).toBe("sess-1");
  });

  it("unwraps the extra envelope so onDone still receives draft.chapters for the double-wrapped shape", () => {
    let received: unknown = null;
    const frame: SseFrame = { type: "done", data: { data: INNER } };

    applySseFrame(frame, { onDone: (p) => (received = p) });

    const inner = received as typeof INNER;
    // The caller must NOT see a nested `.data`; chapters live at the top level.
    expect((inner as { data?: unknown }).data).toBeUndefined();
    expect(inner.draft.chapters).toHaveLength(1);
    expect(inner.draft.chapters[0].number).toBe(1);
  });

  it("feeds the same canonical inner to the theater store for both shapes", () => {
    // single-wrap
    applySseFrame({ type: "done", data: INNER });
    expect(useTheaterStore.getState().characters.map((c) => c.name)).toContain(
      "Anh Khoa"
    );
    expect(useTheaterStore.getState().quality?.value).toBeCloseTo(0.8);

    // reset, then double-wrap must produce the identical store result
    useTheaterStore.setState({ characters: [], quality: undefined });
    applySseFrame({ type: "done", data: { data: INNER } });
    expect(useTheaterStore.getState().characters.map((c) => c.name)).toContain(
      "Anh Khoa"
    );
    expect(useTheaterStore.getState().quality?.value).toBeCloseTo(0.8);
  });

  it("flips the pipeline status to done", () => {
    applySseFrame({ type: "done", data: INNER });
    expect(usePipelineStore.getState().status).toBe("done");
  });
});
