import type { Story } from "@/types/story";

const ID_LIKE_TITLE = /^story-[0-9a-f-]{6,}$/i;

export function displayStoryTitle(story: Story, fallback: string): string {
  const trimmed = story.title?.trim() ?? "";
  if (trimmed && !ID_LIKE_TITLE.test(trimmed)) return trimmed;
  const firstChapter = story.chapters[0]?.title?.trim();
  if (firstChapter) return firstChapter;
  return fallback;
}
