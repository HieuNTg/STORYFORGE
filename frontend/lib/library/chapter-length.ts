"use client";

/**
 * Target chapter length for continuation.
 *
 * `ContinueLibraryRequest.word_count` on the backend accepts 100..20000. Rather
 * than hardcode a number that may not match what the story already reads like,
 * derive the default from the chapters the reader has: the median word count of
 * the most recent ones, so a continuation matches the established rhythm.
 */

import type { StoryChapter } from "@/types/story";

export const MIN_WORD_COUNT = 100;
export const MAX_WORD_COUNT = 20000;
export const FALLBACK_WORD_COUNT = 2000;

/** How many trailing chapters inform the estimate. */
const SAMPLE_SIZE = 5;

export function countWords(text: string): number {
  const trimmed = (text ?? "").trim();
  return trimmed ? trimmed.split(/\s+/).length : 0;
}

export function clampWordCount(value: number): number {
  if (!Number.isFinite(value)) return FALLBACK_WORD_COUNT;
  return Math.max(MIN_WORD_COUNT, Math.min(MAX_WORD_COUNT, Math.round(value)));
}

/**
 * Median length of the last few chapters, rounded to the nearest 100.
 *
 * Median, not mean, so one runaway or stub chapter doesn't drag the target.
 * Returns the fallback when the story has no usable chapters yet.
 */
export function suggestWordCount(chapters: StoryChapter[]): number {
  const counts = chapters
    .slice(-SAMPLE_SIZE)
    .map((ch) => countWords(ch.content))
    .filter((n) => n >= MIN_WORD_COUNT)
    .sort((a, b) => a - b);

  if (counts.length === 0) return FALLBACK_WORD_COUNT;

  const mid = Math.floor(counts.length / 2);
  const median =
    counts.length % 2 === 1 ? counts[mid] : (counts[mid - 1] + counts[mid]) / 2;

  return clampWordCount(Math.round(median / 100) * 100);
}
