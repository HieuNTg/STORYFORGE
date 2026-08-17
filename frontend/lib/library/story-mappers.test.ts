import { describe, it, expect } from "vitest";
import {
  normaliseRole,
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
      {
        name: "Lý Hữu",
        role: "chính",
        personality: "Cương trực",
        background: "Xuất thân hàn vi",
        secret: "Là hậu duệ phụng hoàng",
        internal_conflict: "Trung nghĩa hay tự do",
      },
      { name: "Trần Mai", role: "phản diện", personality: "Mưu lược" },
    ],
    chapters: [
      {
        number: 1,
        title: "Khởi đầu",
        content: "Nội dung chương 1 …",
        summary: "Lý Hữu rời quê.",
      },
      {
        number: 2,
        title: "Tao ngộ",
        content: "Nội dung chương 2 …",
        summary: "Gặp Trần Mai.",
      },
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
    expect(story!.id).toBe("story-sess-abc");
  });

  it("carries the character roster across", () => {
    // Regression: the roster used to be dropped entirely, which also cost the
    // continuation pipeline its character context.
    const story = pipelineSummaryToStory(baseSummary);
    expect(story!.characters).toHaveLength(2);
    const [ly, tran] = story!.characters;
    expect(ly.name).toBe("Lý Hữu");
    expect(ly.role).toBe("protagonist");
    expect(ly.description).toBe("Cương trực");
    expect(ly.backstory).toBe("Xuất thân hàn vi");
    expect(ly.secret).toBe("Là hậu duệ phụng hoàng");
    expect(ly.conflict).toBe("Trung nghĩa hay tự do");
    // No trait axes exist in the L1 model — must stay null, never invented.
    expect(ly.traits).toBeNull();
    expect(tran.role).toBe("antagonist");
  });

  it("carries per-chapter summaries across", () => {
    const story = pipelineSummaryToStory(baseSummary);
    expect(story!.chapters.map((c) => c.summary)).toEqual([
      "Lý Hữu rời quê.",
      "Gặp Trần Mai.",
    ]);
  });

  it("falls back to the draft summary for enhanced chapters", () => {
    // L2 rewrites prose but does not re-summarise.
    const story = pipelineSummaryToStory({
      ...baseSummary,
      has_enhanced: true,
      enhanced: {
        title: "Nâng cao",
        chapters: [{ number: 2, title: "Tao ngộ", content: "Bản nâng cao …" }],
      },
    });
    expect(story!.chapters[0].summary).toBe("Gặp Trần Mai.");
  });

  it("drops characters with no name", () => {
    const story = pipelineSummaryToStory({
      ...baseSummary,
      draft: { ...baseSummary.draft, characters: [{ name: "  " }] },
    });
    expect(story!.characters).toEqual([]);
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

  it("normalises backend role strings onto the Library enum", () => {
    expect(normaliseRole("chính")).toBe("protagonist");
    expect(normaliseRole("phản diện")).toBe("antagonist");
    expect(normaliseRole("đối thủ")).toBe("rival");
    expect(normaliseRole("phụ")).toBe("supporting");
    expect(normaliseRole("protagonist")).toBe("protagonist");
    // Unknown roles degrade to a badge, never to a dropped character.
    expect(normaliseRole("kẻ dẫn chuyện")).toBe("supporting");
    expect(normaliseRole(undefined)).toBe("supporting");
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
