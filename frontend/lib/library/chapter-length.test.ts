import { describe, it, expect } from "vitest";
import {
  clampWordCount,
  countWords,
  FALLBACK_WORD_COUNT,
  MAX_WORD_COUNT,
  MIN_WORD_COUNT,
  suggestWordCount,
} from "./chapter-length";
import type { StoryChapter } from "@/types/story";

function ch(words: number): StoryChapter {
  return {
    id: `ch-${words}`,
    title: "Chương",
    content: Array.from({ length: words }, (_, i) => `từ${i}`).join(" "),
    summary: "",
    badge: "Ch",
    status: "ready",
    images: [],
    createdAt: new Date(0).toISOString(),
  };
}

describe("chapter-length", () => {
  it("counts words, tolerating ragged whitespace", () => {
    expect(countWords("  một   hai\nba ")).toBe(3);
    expect(countWords("")).toBe(0);
    expect(countWords("   ")).toBe(0);
  });

  it("clamps to the backend's accepted range", () => {
    expect(clampWordCount(50)).toBe(MIN_WORD_COUNT);
    expect(clampWordCount(999_999)).toBe(MAX_WORD_COUNT);
    expect(clampWordCount(Number.NaN)).toBe(FALLBACK_WORD_COUNT);
    expect(clampWordCount(1234.6)).toBe(1235);
  });

  it("falls back when the story has no usable chapters", () => {
    expect(suggestWordCount([])).toBe(FALLBACK_WORD_COUNT);
    // Stubs below the backend minimum carry no signal.
    expect(suggestWordCount([ch(10)])).toBe(FALLBACK_WORD_COUNT);
  });

  it("derives the target from recent chapters, rounded to 100", () => {
    expect(suggestWordCount([ch(1180), ch(1230), ch(1210)])).toBe(1200);
  });

  it("uses the median so one outlier cannot drag the target", () => {
    // Mean would be ~4300; median stays with the body of the story.
    expect(suggestWordCount([ch(1200), ch(1200), ch(1200), ch(1200), ch(18000)])).toBe(
      1200,
    );
  });

  it("only samples the trailing chapters", () => {
    // Six chapters: the leading 900-word one must fall out of the window.
    const chapters = [ch(900), ch(2000), ch(2000), ch(2000), ch(2000), ch(2000)];
    expect(suggestWordCount(chapters)).toBe(2000);
  });

  it("never exceeds the backend ceiling", () => {
    expect(suggestWordCount([ch(19_999), ch(19_999)])).toBeLessThanOrEqual(
      MAX_WORD_COUNT,
    );
  });
});
