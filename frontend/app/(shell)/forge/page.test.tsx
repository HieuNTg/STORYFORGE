/**
 * ForgePage auto-save behaviour.
 *
 * Regression guard for "tạo truyện xong nhưng thư viện trống": the library is
 * localStorage-only and a story entered it solely via the manual "Lưu vào thư
 * viện" CTA, which only appears after the `done` frame. If the user never
 * reached that panel (reload mid-run / stream drop), the story was lost. The
 * fix auto-saves on `done`, so a finished run must land in `useLibraryStore`
 * without any click.
 *
 * Only the chrome is mocked: `next-intl` (passthrough keys), `sonner`, and
 * `PipelineScreen` (stubbed to fire `onResult` on mount). The real store and
 * the real `pipelineSummaryToStory` run, so this also covers the mapping.
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import * as React from "react";
import { render } from "@testing-library/react";

// Shared, hoisted holder so the PipelineScreen mock can fire whatever `done`
// payload a given test sets before render.
const h = vi.hoisted(() => ({ done: undefined as unknown }));

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string) => key,
}));

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

vi.mock("@/components/pipeline/PipelineScreen", () => ({
  PipelineScreen: ({ onResult }: { onResult?: (raw: unknown) => void }) => {
    React.useEffect(() => {
      if (h.done !== undefined) onResult?.(h.done);
    }, [onResult]);
    return null;
  },
}));

import ForgePage from "./page";
import { useLibraryStore } from "@/stores/library-store";

beforeEach(() => {
  useLibraryStore.getState().clearAll();
  h.done = undefined;
});

describe("ForgePage auto-save", () => {
  it("auto-saves the finished story to the library on `done` (no click)", () => {
    h.done = {
      has_draft: true,
      session_id: "sess-auto-1",
      draft: {
        title: "Truyện tự lưu",
        genre: "Tiên Hiệp",
        chapters: [{ number: 1, title: "Chương 1", content: "Nội dung..." }],
      },
    };

    render(<ForgePage />);

    const { stories } = useLibraryStore.getState();
    expect(stories).toHaveLength(1);
    expect(stories[0]!.title).toBe("Truyện tự lưu");
    // Deterministic id keeps the auto-save idempotent across re-saves.
    expect(stories[0]!.id).toBe("story-sess-auto-1");
  });

  it("does not save anything when no run has finished", () => {
    render(<ForgePage />);
    expect(useLibraryStore.getState().stories).toHaveLength(0);
  });
});
