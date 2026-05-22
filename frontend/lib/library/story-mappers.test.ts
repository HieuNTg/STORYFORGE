import { describe, it, expect } from "vitest";
import {
  pipelineSummaryToStory,
  type PipelineDoneSummary,
} from "./story-mappers";
import { storySchema } from "@/types/story";

const baseSummary: PipelineDoneSummary = {
  has_draft: true,
  has_enhanced: false,
  session_id: "sess-abc",
  draft: {
    title: "Phụng Hoàng Tàn",
    genre: "Tiên Hiệp",
    synopsis: "Một câu chuyện về phụng hoàng.",
    characters: [
      { name: "Lý Hữu", personality: "Cương trực" },
      { name: "Trần Mai", personality: "Mưu lược" },
    ],
    chapters: [
      { number: 1, title: "Khởi đầu", content: "Nội dung chương 1 …" },
      { number: 2, title: "Tao ngộ", content: "Nội dung chương 2 …" },
    ],
  },
};

describe("pipelineSummaryToStory", () => {
  it("maps a L1 draft summary into a Story that passes storySchema", () => {
    const story = pipelineSummaryToStory(baseSummary);
    expect(story).not.toBeNull();
    // The store will re-parse on insert — must not throw.
    expect(() => storySchema.parse(story!)).not.toThrow();
    expect(story!.title).toBe("Phụng Hoàng Tàn");
    expect(story!.chapters).toHaveLength(2);
    expect(story!.chapters[0].status).toBe("ready");
    expect(story!.chapters[0].badge).toBe("Ch");
    // characters intentionally empty for v1 (see mapper comment).
    expect(story!.characters).toEqual([]);
    expect(story!.id).toBe("story-sess-abc");
  });

  it("prefers enhanced chapters and marks them 'enhanced'", () => {
    const enhancedSummary: PipelineDoneSummary = {
      ...baseSummary,
      has_enhanced: true,
      enhanced: {
        title: "Phụng Hoàng Tàn (Nâng cao)",
        drama_score: 0.8,
        chapters: [
          { number: 1, title: "Khởi đầu mới", content: "Nội dung nâng cao …" },
        ],
      },
    };
    const story = pipelineSummaryToStory(enhancedSummary);
    expect(story).not.toBeNull();
    expect(story!.title).toBe("Phụng Hoàng Tàn (Nâng cao)");
    expect(story!.chapters).toHaveLength(1);
    expect(story!.chapters[0].status).toBe("enhanced");
    expect(story!.chapters[0].title).toBe("Khởi đầu mới");
  });

  it("returns null when no chapters are present", () => {
    expect(pipelineSummaryToStory(null)).toBeNull();
    expect(pipelineSummaryToStory({})).toBeNull();
    expect(
      pipelineSummaryToStory({ has_draft: true, draft: { chapters: [] } })
    ).toBeNull();
  });

  it("fills sensible defaults when fields are missing", () => {
    const sparse: PipelineDoneSummary = {
      has_draft: true,
      draft: {
        chapters: [{ content: "Plain text" }],
      },
    };
    const story = pipelineSummaryToStory(sparse, "Huyền Huyễn");
    expect(story).not.toBeNull();
    expect(story!.title).toBe("Truyện mới");
    expect(story!.genre).toBe("Huyền Huyễn");
    expect(story!.chapters[0].title).toBe("Chương 1");
    expect(() => storySchema.parse(story!)).not.toThrow();
  });
});
