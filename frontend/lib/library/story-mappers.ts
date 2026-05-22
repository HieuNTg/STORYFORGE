"use client";

/**
 * Mappers that convert external payloads (cheap forge + full pipeline)
 * into the Library `Story` shape persisted by `useLibraryStore`.
 *
 * Two source payloads:
 *   - `ForgeResponse` (1-sentence forge in Library) → existing path
 *   - Pipeline `/api/pipeline/run` `done.data` summary → new save-from-Khai-sinh path
 *
 * Both must produce a value that passes `storySchema.parse` because
 * `useLibraryStore.addStory` re-parses on insert.
 */

import { genStoryId } from "@/lib/library/ids";
import type { ForgeResponse, Story, StoryChapter } from "@/types/story";

function genChapterId(): string {
  return `ch-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`;
}

/**
 * Convert a cheap 1-sentence forge response into a single-chapter Library story.
 * Lifted verbatim from `BookshelfScreen` so other screens can reuse it.
 */
export function forgeToStory(forge: ForgeResponse): Story {
  const now = new Date().toISOString();
  const chapter: StoryChapter = {
    id: genChapterId(),
    title: forge.firstChapter.title,
    content: forge.firstChapter.content,
    summary: forge.firstChapter.summary,
    badge: "ĐK",
    status: "ready",
    createdAt: now,
  };
  return {
    id: genStoryId(),
    title: forge.title,
    genre: forge.genre,
    setting: forge.setting,
    tone: forge.tone,
    description: forge.description,
    coverUrl: null,
    characters: forge.characters,
    chapters: [chapter],
    pendingChoices: forge.firstChapter.choices,
    createdAt: now,
    updatedAt: now,
  };
}

/* ---------------------------------------------------------------------- */
/* Pipeline /api/pipeline/run → Story                                      */
/* ---------------------------------------------------------------------- */

/**
 * Shape of the `done` event payload emitted by `/api/pipeline/run`.
 *
 * Source of truth: `api/pipeline_output_builder.build_output_summary` +
 * `_sanitize_summary`. The frontend mirrors *only* the fields it consumes —
 * extra fields are tolerated (we never re-serialise this object).
 */
export interface PipelineDoneSummary {
  has_draft?: boolean;
  has_enhanced?: boolean;
  session_id?: string;
  draft?: {
    title?: string;
    genre?: string;
    synopsis?: string;
    characters?: Array<{ name?: string; personality?: string }>;
    chapters?: Array<{
      number?: number;
      title?: string;
      content?: string;
    }>;
  };
  enhanced?: {
    title?: string;
    drama_score?: number;
    chapters?: Array<{
      number?: number;
      title?: string;
      content?: string;
    }>;
  };
}

/**
 * Prefer the enhanced (L2) draft when present; otherwise fall back to the L1
 * draft. Returns null when no usable chapters exist.
 */
export function pipelineSummaryToStory(
  summary: PipelineDoneSummary | null | undefined,
  fallbackGenre: string = "",
): Story | null {
  if (!summary) return null;
  const enhanced = summary.has_enhanced ? summary.enhanced : null;
  const draft = summary.has_draft ? summary.draft : null;
  const sourceChapters = enhanced?.chapters ?? draft?.chapters ?? [];
  if (sourceChapters.length === 0) return null;

  const now = new Date().toISOString();
  const title =
    enhanced?.title?.trim() || draft?.title?.trim() || "Truyện mới";
  const genre = draft?.genre?.trim() || fallbackGenre;
  const description = draft?.synopsis?.trim() ?? "";
  const status: StoryChapter["status"] = enhanced ? "enhanced" : "ready";

  const chapters: StoryChapter[] = sourceChapters.map((ch, idx) => ({
    id: `ch-${idx + 1}-${Date.now().toString(36)}`,
    title: (ch.title ?? `Chương ${ch.number ?? idx + 1}`).trim() ||
      `Chương ${ch.number ?? idx + 1}`,
    content: ch.content ?? "",
    summary: "",
    badge: "Ch" as const,
    status,
    createdAt: now,
  }));

  // Pipeline character schema is `{name, personality}` — far thinner than the
  // ForgeCharacter (role + traits + backstory + …) required by `storySchema`.
  // Persist an empty character roster for v1; the user can flesh it out later
  // via the Characters page. Avoids forcing a fake `role` / zero-stat traits.
  return {
    id: summary.session_id
      ? `story-${summary.session_id}`
      : genStoryId(),
    title,
    genre,
    setting: "",
    tone: "",
    description,
    coverUrl: null,
    characters: [],
    chapters,
    pendingChoices: null,
    createdAt: now,
    updatedAt: now,
  };
}
