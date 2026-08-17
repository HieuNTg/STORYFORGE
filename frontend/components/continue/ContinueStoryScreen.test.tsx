/**
 * "Viết tiếp truyện" wiring tests.
 *
 * The regression these guard: this screen used to call the cheap one-sentence
 * forge (`/api/forge/sentence/stream`), flattening the story into a 2000-char
 * prompt — no character sheets, no prior chapters, no L1/L2 stages. It must now
 * post the whole story to the real continuation pipeline and append only the
 * chapters that pipeline returns.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import * as React from "react";
import { render, fireEvent, act } from "@testing-library/react";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
  useSearchParams: () => new URLSearchParams(""),
}));

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string) => key,
}));

const toastError = vi.fn();
const toastSuccess = vi.fn();
const toastInfo = vi.fn();
vi.mock("sonner", () => ({
  toast: {
    error: (...a: unknown[]) => toastError(...a),
    success: (...a: unknown[]) => toastSuccess(...a),
    info: (...a: unknown[]) => toastInfo(...a),
  },
}));

const fetchOutlines = vi.fn();
vi.mock("@/lib/api/continueStory", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/continueStory")>();
  return { ...actual, fetchContinueOutlines: (...a: unknown[]) => fetchOutlines(...a) };
});

// Capture what the screen streams, and keep a handle on its callbacks so tests
// can push SSE frames at it.
let streamOpts: {
  url: string | null;
  body: Record<string, unknown> | null;
  onMessage: (ev: { data: string }) => void;
  onClose?: () => void;
} | null = null;
vi.mock("@/lib/sse/usePostStream", () => ({
  usePostStream: (opts: typeof streamOpts) => {
    streamOpts = opts;
    return { readyState: "idle", abort: vi.fn() };
  },
}));

import { ContinueStoryScreen } from "./ContinueStoryScreen";
import { useLibraryStore } from "@/stores/library-store";
import type { Story } from "@/types/story";

const STORY: Story = {
  id: "story-1",
  title: "Vô Gia Vạn Hồn Phả",
  genre: "Tiên Hiệp",
  setting: "Bắc Vực",
  tone: "bi tráng",
  description: "Một thiếu niên gánh vạn hồn.",
  coverUrl: null,
  galleryShareId: "",
  characters: [
    {
      name: "Lý Trầm",
      role: "protagonist",
      traits: { strength: 70, wisdom: 60, agility: 80, scheme: 40 },
      description: "Trầm mặc.",
      backstory: "Mồ côi.",
      secret: "Có ma hồn.",
      conflict: "Cứu người hay giữ mình.",
    },
  ],
  chapters: [
    {
      id: "ch-1",
      title: "Chương 1",
      content: "Nội dung một.",
      summary: "Tóm tắt một.",
      badge: "Ch",
      status: "ready",
      images: [],
      createdAt: new Date(0).toISOString(),
    },
  ],
  pendingChoices: null,
  language: "vi",
  targetChapters: 10,
  createdAt: new Date(0).toISOString(),
  updatedAt: new Date(0).toISOString(),
};

function seedStore() {
  useLibraryStore.setState({
    stories: [structuredClone(STORY)],
    selectedId: STORY.id,
    hydrated: true,
  });
}

function send(frame: Record<string, unknown>) {
  act(() => {
    streamOpts?.onMessage({ data: JSON.stringify(frame) });
  });
}

function clickWrite(getByRole: ReturnType<typeof render>["getByRole"]) {
  fireEvent.click(getByRole("button", { name: /btn_write_n/ }));
}

describe("ContinueStoryScreen", () => {
  beforeEach(() => {
    streamOpts = null;
    push.mockClear();
    toastError.mockClear();
    toastSuccess.mockClear();
    toastInfo.mockClear();
    fetchOutlines.mockReset();
    seedStore();
  });

  it("is idle until the user asks to write", () => {
    render(<ContinueStoryScreen />);
    expect(streamOpts?.url).toBeNull();
    expect(streamOpts?.body).toBeNull();
  });

  it("posts the whole story to the continuation pipeline, not a prompt string", () => {
    const { getByRole } = render(<ContinueStoryScreen />);
    clickWrite(getByRole);

    expect(streamOpts?.url).toBe("/api/pipeline/continue/library");
    const body = streamOpts?.body as {
      story: {
        characters: Array<Record<string, string>>;
        chapters: Array<Record<string, string>>;
        targetChapters: number;
      };
      additional_chapters: number;
      run_enhancement: boolean;
    };
    // Full character sheets travel — the old path sent only names.
    expect(body.story.characters[0].secret).toBe("Có ma hồn.");
    expect(body.story.characters[0].backstory).toBe("Mồ côi.");
    // Every chapter travels with its summary — the old path sent one, truncated.
    expect(body.story.chapters).toHaveLength(1);
    expect(body.story.chapters[0].summary).toBe("Tóm tắt một.");
    expect(body.story.targetChapters).toBe(10);
    expect(body.additional_chapters).toBe(1);
    expect(body.run_enhancement).toBe(true);
  });

  it("forwards the user's direction verbatim", () => {
    const { getByRole, container } = render(<ContinueStoryScreen />);
    const textarea = container.querySelector("textarea") as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: "Hé lộ bí mật của Lý Trầm" } });
    clickWrite(getByRole);

    expect((streamOpts?.body as { direction: string }).direction).toBe(
      "Hé lộ bí mật của Lý Trầm",
    );
  });

  it("appends the returned chapters and moves to the reader", () => {
    const { getByRole } = render(<ContinueStoryScreen />);
    clickWrite(getByRole);

    send({
      type: "done",
      data: {
        new_chapters: [
          {
            number: 2,
            title: "Chương 2",
            content: "Chương do pipeline viết.",
            summary: "Tóm tắt hai.",
            wordCount: 4,
          },
        ],
        hydration_source: "checkpoint",
        total_chapters: 2,
        enhanced_chapters: 1,
      },
    });

    const story = useLibraryStore.getState().stories[0];
    expect(story.chapters).toHaveLength(2);
    expect(story.chapters[1].title).toBe("Chương 2");
    expect(story.chapters[1].summary).toBe("Tóm tắt hai.");
    // L2 ran over the new chapters, so they are marked enhanced.
    expect(story.chapters[1].status).toBe("enhanced");
    expect(toastSuccess).toHaveBeenCalled();
    expect(push).toHaveBeenCalledWith("/reader/?id=story-1");
    // Stream torn down after a terminal frame.
    expect(streamOpts?.body).toBeNull();
  });

  it("surfaces a pipeline error and stops writing", () => {
    const { getByRole } = render(<ContinueStoryScreen />);
    clickWrite(getByRole);

    send({ type: "error", data: "Truyện đã đạt 10/10 chương." });

    expect(toastError).toHaveBeenCalled();
    expect(useLibraryStore.getState().stories[0].chapters).toHaveLength(1);
    expect(streamOpts?.body).toBeNull();
    expect(push).not.toHaveBeenCalled();
  });

  it("does not append anything when the pipeline returns no chapters", () => {
    const { getByRole } = render(<ContinueStoryScreen />);
    clickWrite(getByRole);

    send({ type: "done", data: { new_chapters: [] } });

    expect(useLibraryStore.getState().stories[0].chapters).toHaveLength(1);
    expect(toastError).toHaveBeenCalled();
    expect(push).not.toHaveBeenCalled();
  });

  it("warns when the stream closes mid-run", () => {
    const { getByRole } = render(<ContinueStoryScreen />);
    clickWrite(getByRole);

    act(() => streamOpts?.onClose?.());

    expect(toastError).toHaveBeenCalled();
    expect(streamOpts?.body).toBeNull();
  });

  it("does not warn when the stream closes after a terminal frame", () => {
    const { getByRole } = render(<ContinueStoryScreen />);
    clickWrite(getByRole);

    send({
      type: "done",
      data: {
        new_chapters: [
          { number: 2, title: "Chương 2", content: "x", summary: "s", wordCount: 1 },
        ],
      },
    });
    toastError.mockClear();

    // The server always closes right after `done` — that must stay silent.
    act(() => streamOpts?.onClose?.());

    expect(toastError).not.toHaveBeenCalled();
  });

  it("previews an editable outline without writing prose", async () => {
    fetchOutlines.mockResolvedValue({
      outlines: [
        { chapter_number: 2, title: "Manh mối", summary: "Lý Trầm tới Trấn Nam." },
      ],
      hydration_source: "checkpoint",
    });
    const { getByRole, findByDisplayValue } = render(<ContinueStoryScreen />);

    fireEvent.click(getByRole("button", { name: /btn_preview_outline/ }));
    await findByDisplayValue("Manh mối");

    // Planning must not start a write stream.
    expect(streamOpts?.body).toBeNull();
    expect(useLibraryStore.getState().stories[0].chapters).toHaveLength(1);
  });

  it("sends the edited outline instead of re-planning", async () => {
    fetchOutlines.mockResolvedValue({
      outlines: [
        { chapter_number: 2, title: "Manh mối", summary: "Lý Trầm tới Trấn Nam." },
      ],
    });
    const { getByRole, findByDisplayValue } = render(<ContinueStoryScreen />);

    fireEvent.click(getByRole("button", { name: /btn_preview_outline/ }));
    const titleField = await findByDisplayValue("Manh mối");
    fireEvent.change(titleField, { target: { value: "Máu trên tuyết" } });

    fireEvent.click(getByRole("button", { name: /btn_write_approved/ }));

    const body = streamOpts?.body as {
      outlines: Array<{ title: string; summary: string }>;
    };
    expect(body.outlines).toHaveLength(1);
    expect(body.outlines[0].title).toBe("Máu trên tuyết");
    expect(body.outlines[0].summary).toBe("Lý Trầm tới Trấn Nam.");
  });

  it("writes without outlines when none were reviewed", () => {
    const { getByRole } = render(<ContinueStoryScreen />);
    clickWrite(getByRole);
    expect((streamOpts?.body as { outlines: unknown[] }).outlines).toEqual([]);
  });

  it("surfaces a planning failure and stays idle", async () => {
    fetchOutlines.mockRejectedValue(new Error("boom"));
    const { getByRole } = render(<ContinueStoryScreen />);

    await act(async () => {
      fireEvent.click(getByRole("button", { name: /btn_preview_outline/ }));
    });

    expect(toastError).toHaveBeenCalled();
    expect(streamOpts?.body).toBeNull();
  });

  it("ignores non-terminal frames", () => {
    const { getByRole } = render(<ContinueStoryScreen />);
    clickWrite(getByRole);

    send({ type: "session", session_id: "abc" });
    send({ type: "log", data: "Đang lên dàn ý..." });

    expect(streamOpts?.body).not.toBeNull(); // still streaming
    expect(toastError).not.toHaveBeenCalled();
  });
});
