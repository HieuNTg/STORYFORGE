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
import type {
  ForgeCharacter,
  ForgeResponse,
  ForgeRole,
  Story,
  StoryChapter,
} from "@/types/story";

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
    images: [],
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
    galleryShareId: "",
    characters: forge.characters,
    chapters: [chapter],
    pendingChoices: forge.firstChapter.choices,
    language: "vi",
    targetChapters: null,
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
    target_total_chapters?: number | null;
    written_chapters?: number;
    characters?: Array<{
      name?: string;
      role?: string;
      personality?: string;
      background?: string;
      secret?: string;
      motivation?: string;
      internal_conflict?: string;
    }>;
    chapters?: Array<{
      number?: number;
      title?: string;
      content?: string;
      summary?: string;
    }>;
  };
  enhanced?: {
    title?: string;
    drama_score?: number;
    chapters?: Array<{
      number?: number;
      title?: string;
      content?: string;
      summary?: string;
    }>;
  };
}

/**
 * Map a backend `Character.role` onto the Library's four-way role enum.
 *
 * L1 writes free-form Vietnamese ("chính", "phản diện", …); the forge writes
 * the enum directly. Anything unrecognised becomes "supporting" — a wrong
 * badge is recoverable, a dropped character is not.
 */
export function normaliseRole(role: string | undefined): ForgeRole {
  const r = (role ?? "").trim().toLowerCase();
  if (!r) return "supporting";
  if (["protagonist", "antagonist", "rival", "supporting"].includes(r)) {
    return r as ForgeRole;
  }
  if (r.includes("phản") || r.includes("ác")) return "antagonist";
  if (r.includes("đối thủ") || r.includes("kình địch")) return "rival";
  if (r.includes("chính")) return "protagonist";
  return "supporting";
}

/**
 * Prefer the enhanced (L2) draft when present; otherwise fall back to the L1
 * draft. Returns null when no usable chapters exist.
 */
export function pipelineSummaryToStory(
  summary: PipelineDoneSummary | null | undefined,
  fallbackGenre: string = "",
  targetChapters: number | null = null,
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

  // L2 rewrites prose but does not re-summarise, so a chapter's summary lives
  // on the draft. Match by chapter number rather than index — the enhanced list
  // is not guaranteed to be dense.
  const draftSummaries = new Map<number, string>(
    (draft?.chapters ?? []).map((ch, idx) => [ch.number ?? idx + 1, ch.summary ?? ""]),
  );

  const chapters: StoryChapter[] = sourceChapters.map((ch, idx) => {
    const number = ch.number ?? idx + 1;
    return {
      id: `ch-${idx + 1}-${Date.now().toString(36)}`,
      title: (ch.title ?? `Chương ${number}`).trim() || `Chương ${number}`,
      content: ch.content ?? "",
      summary: ch.summary || draftSummaries.get(number) || "",
      badge: "Ch" as const,
      status,
      images: [],
      createdAt: now,
    };
  });

  // Carry the roster across. The pipeline models personality/backstory/secret/
  // conflict but has no 0-100 trait axes, so `traits` stays null and the
  // Characters page offers to generate them — previously the whole roster was
  // dropped, which also cost the continuation pipeline its character context.
  const characters: ForgeCharacter[] = (draft?.characters ?? [])
    .filter((c) => (c.name ?? "").trim())
    .map((c) => ({
      name: (c.name ?? "").trim(),
      role: normaliseRole(c.role),
      traits: null,
      description: c.personality ?? "",
      backstory: c.background ?? "",
      secret: c.secret ?? "",
      conflict: c.internal_conflict || c.motivation || "",
    }));

  // Prefer explicit caller value; fall back to backend's draft.target_total_chapters.
  const effectiveTarget =
    targetChapters ??
    (typeof draft?.target_total_chapters === "number" && draft.target_total_chapters > 0
      ? draft.target_total_chapters
      : null);

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
    galleryShareId: "",
    characters,
    chapters,
    pendingChoices: null,
    language: "vi",
    targetChapters: effectiveTarget,
    createdAt: now,
    updatedAt: now,
  };
}
