"use client";

/**
 * "Viết tiếp truyện" → the real continuation pipeline.
 *
 * The Library is localStorage-only, so there is no checkpoint id to address a
 * story by: the whole story travels in the request body and the backend
 * hydrates a StoryDraft from it (see `services/library_continuation.py`). The
 * response carries ONLY the newly written chapters, which the caller appends to
 * the local story.
 *
 * This replaced a call to `/api/forge/sentence/stream` — the cheap one-sentence
 * forge — which re-invented the story from a 2000-char prompt on every chapter
 * and ran none of the L1/L2 stages.
 */

import type { Story } from "@/types/story";
import { apiFetch } from "./client";

export const CONTINUE_LIBRARY_URL = "/api/pipeline/continue/library";
export const CONTINUE_LIBRARY_OUTLINES_URL =
  "/api/pipeline/continue/library/outlines";

/** One planned chapter, as returned by the outline preview. */
export interface ContinuationOutline {
  chapter_number: number;
  title: string;
  summary: string;
  [key: string]: unknown;
}

export interface OutlinePreviewResponse {
  outlines: ContinuationOutline[];
  hydration_source?: "checkpoint" | "payload";
  existing_chapters?: number;
  /** Set when the request was clamped to the story's remaining arc. */
  note?: string | null;
}

/** One chapter as returned by `done.data.new_chapters`. */
export interface ContinuedChapter {
  number: number;
  title: string;
  content: string;
  summary: string;
  wordCount: number;
}

/** `done.data` payload of the continue stream. */
export interface ContinueDoneData {
  new_chapters?: ContinuedChapter[];
  /** "checkpoint" = full L1 signals were available; "payload" = rebuilt from prose. */
  hydration_source?: "checkpoint" | "payload";
  total_chapters?: number;
  enhanced_chapters?: number;
}

export interface ContinueRequestBody extends Record<string, unknown> {
  story: {
    id: string;
    title: string;
    genre: string;
    setting: string;
    tone: string;
    description: string;
    language: string;
    targetChapters: number | null;
    characters: Array<{
      name: string;
      role: string;
      description: string;
      backstory: string;
      secret: string;
      conflict: string;
    }>;
    chapters: Array<{ title: string; content: string; summary: string }>;
  };
  additional_chapters: number;
  word_count: number;
  direction: string;
  run_enhancement: boolean;
  /** Pre-approved outlines; empty = let the pipeline plan during the run. */
  outlines: ContinuationOutline[];
}

function storyPayload(story: Story): ContinueRequestBody["story"] {
  return {
    id: story.id,
    title: story.title,
    genre: story.genre,
    setting: story.setting,
    tone: story.tone,
    description: story.description,
    language: story.language,
    targetChapters: story.targetChapters,
    characters: story.characters.map((c) => ({
      name: c.name,
      role: c.role,
      description: c.description,
      backstory: c.backstory,
      secret: c.secret,
      conflict: c.conflict,
    })),
    chapters: story.chapters.map((ch) => ({
      title: ch.title,
      content: ch.content,
      summary: ch.summary,
    })),
  };
}

/**
 * Plan the next chapters without writing them, so the reader can review and
 * edit the direction before paying for prose.
 */
export async function fetchContinueOutlines(
  story: Story,
  opts: { additionalChapters: number; direction: string },
): Promise<OutlinePreviewResponse> {
  return apiFetch<OutlinePreviewResponse>(CONTINUE_LIBRARY_OUTLINES_URL, {
    method: "POST",
    body: JSON.stringify({
      story: storyPayload(story),
      additional_chapters: opts.additionalChapters,
      direction: opts.direction.trim(),
    }),
  });
}

/**
 * Project a Library story into the continuation payload.
 *
 * Everything the pipeline needs for continuity goes across — full character
 * sheets (not just names) and every chapter with its summary — because that is
 * exactly what the old forge path threw away.
 */
export function buildContinueBody(
  story: Story,
  opts: {
    additionalChapters: number;
    direction: string;
    wordCount?: number;
    runEnhancement?: boolean;
    outlines?: ContinuationOutline[];
  },
): ContinueRequestBody {
  return {
    story: storyPayload(story),
    additional_chapters: opts.additionalChapters,
    word_count: opts.wordCount ?? 2000,
    direction: opts.direction.trim(),
    run_enhancement: opts.runEnhancement ?? true,
    outlines: opts.outlines ?? [],
  };
}
