"use client";

/**
 * illustration.ts — image-generation client wrappers for the reader UI.
 *
 * Backend routes wrapped (api/image_routes.py):
 *   POST /api/images/{session_id}/generate                              — full or per-chapter
 *   GET  /api/images/{session_id}/profiles                              — list character profiles
 *   POST /api/images/{session_id}/profiles/{character_name}/rebuild     — avatar refresh
 *
 * Per-chapter regeneration uses the existing `chapter` field on
 * GenerateImagesRequest — no backend change needed (YAGNI, CLAUDE.md Rule 2).
 */

import { apiFetch } from "@/lib/api/client";
import type { Story } from "@/types/story";

export interface GenerateImagesResponse {
  image_paths: string[];
  message: string;
  count: number;
  chapter_images: Record<number, string[]>;
  /** Chapters the backend skipped because they already had panels. */
  skipped_chapters?: number[];
}

/** Per-chapter comic state from GET /api/images/{session_id}/status. */
export interface ChapterComicStatus {
  chapter_number: number;
  title: string;
  has_images: boolean;
  image_count: number;
  /** Already `/media/...`-prefixed and ready to render. */
  image_urls: string[];
}

export interface ComicStatusResponse {
  /** "none" => image provider not configured in Settings. */
  provider: string;
  panels_per_chapter: number;
  total_chapters: number;
  chapters_with_images: number;
  chapters: ChapterComicStatus[];
}

/**
 * GET /api/images/{session_id}/status — read-only render state for the comic
 * control. `sessionId` is the checkpoint filename (e.g. `story_<id>.json`)
 * the Library/reader already addresses stories by.
 */
export function getComicStatus(
  sessionId: string,
): Promise<ComicStatusResponse> {
  return apiFetch<ComicStatusResponse>(
    `/api/images/${encodeURIComponent(sessionId)}/status`,
    { method: "GET" },
  );
}

/**
 * POST /api/images/{session_id}/generate with `only_missing: true` —
 * incremental generation. Generates comics ONLY for chapters that lack them
 * (the default case, including chapters appended by "Continue"). Idempotent.
 * Backend keeps new chapters visually consistent with already-generated ones.
 */
export function generateMissingImages(
  sessionId: string,
  provider?: string,
): Promise<GenerateImagesResponse> {
  const body: { only_missing: true; provider?: string } = { only_missing: true };
  if (provider) body.provider = provider;
  return apiFetch<GenerateImagesResponse>(
    `/api/images/${encodeURIComponent(sessionId)}/generate`,
    { method: "POST", body: JSON.stringify(body) },
  );
}

export interface CharacterProfile {
  name: string;
  frozen_prompt: string;
  prompt_version?: number | null;
  has_reference_image?: boolean;
  reference_url?: string | null;
}

export interface CharacterProfileRebuildResponse extends CharacterProfile {
  rebuilt: boolean;
}

export interface CharacterProfilesResponse {
  profiles: CharacterProfile[];
}

export function generateChapterImage(
  sessionId: string,
  chapter: number,
  provider?: string,
): Promise<GenerateImagesResponse> {
  const body: { chapter: number; provider?: string } = { chapter };
  if (provider) body.provider = provider;
  return apiFetch<GenerateImagesResponse>(
    `/api/images/${encodeURIComponent(sessionId)}/generate`,
    { method: "POST", body: JSON.stringify(body) },
  );
}

/**
 * POST /api/images/{session_id}/generate with `only_missing: false` — full
 * regenerate of ALL chapters (capped at 10/call by the backend → 400 if
 * exceeded). Prefer `generateMissingImages` for the common case.
 */
export function generateAllImages(
  sessionId: string,
  provider?: string,
): Promise<GenerateImagesResponse> {
  const body: { only_missing: false; provider?: string } = { only_missing: false };
  if (provider) body.provider = provider;
  return apiFetch<GenerateImagesResponse>(
    `/api/images/${encodeURIComponent(sessionId)}/generate`,
    { method: "POST", body: JSON.stringify(body) },
  );
}

export function listCharacterProfiles(
  sessionId: string,
): Promise<CharacterProfilesResponse> {
  return apiFetch<CharacterProfilesResponse>(
    `/api/images/${encodeURIComponent(sessionId)}/profiles`,
    { method: "GET" },
  );
}

export function rebuildCharacterAvatar(
  sessionId: string,
  characterName: string,
): Promise<CharacterProfileRebuildResponse> {
  return apiFetch<CharacterProfileRebuildResponse>(
    `/api/images/${encodeURIComponent(sessionId)}/profiles/${encodeURIComponent(characterName)}/rebuild`,
    { method: "POST" },
  );
}

// ---------------------------------------------------------------------------
// Payload-based comic generation for localStorage-only Library stories.
//
// These stories have no backend checkpoint, so the whole Story travels in the
// request body — the SAME shape the export endpoint accepts. The backend keeps
// every chapter visually consistent by scoping its CharacterVisualProfileStore
// to the story TITLE (so chapters generated now match chapters generated after
// "Continue"). The client owns persistence: write the returned `chapter_images`
// onto each Chapter.images and persist the Story to localStorage.
// ---------------------------------------------------------------------------

/** The exact body POST /api/images/library/generate expects. */
interface LibraryImagePayload {
  story: {
    id: string;
    title: string;
    genre: string;
    setting: string;
    tone: string;
    description: string;
    characters: Story["characters"];
    chapters: Array<{
      title: string;
      content: string;
      summary: string;
      images: string[];
    }>;
  };
  provider?: string;
  chapter?: number;
  only_missing?: boolean;
}

/** Map a localStorage Story to the backend library-image payload. */
function toLibraryImagePayload(story: Story): LibraryImagePayload["story"] {
  return {
    id: story.id,
    title: story.title,
    genre: story.genre,
    setting: story.setting,
    tone: story.tone,
    description: story.description,
    characters: story.characters,
    chapters: story.chapters.map((ch) => ({
      title: ch.title,
      content: ch.content,
      summary: ch.summary,
      // Round-trips existing panels so the backend can skip illustrated chapters.
      images: ch.images ?? [],
    })),
  };
}

// ---------------------------------------------------------------------------
// Phase B — async background comic generation.
//
// `POST /api/images/library/generate` no longer runs generation on the request
// thread. It accepts the job and returns 202 + `job_id` immediately; the work
// runs server-side and the client polls `GET .../jobs/{job_id}` until a
// terminal state, persisting accreting `chapter_images` to localStorage as
// chapters land. See docs/comic-async-generation-phase-b-proposal.md §2.1–2.6.
// ---------------------------------------------------------------------------

/** 202 body from POST /api/images/library/generate (LibraryJobAcceptedResponse). */
export interface LibraryJobAccepted {
  job_id: string;
  /** "queued" | "running" (running when reattaching to a live job). */
  state: string;
  /** Idempotency key (story title). */
  title: string;
  total_chapters: number;
  /** 1-based chapter numbers this job will generate. */
  target_chapters: number[];
  /** true => an identical-scope job was already running; we attached to it. */
  already_running: boolean;
}

/** Per-chapter progress inside a library job (LibraryJobChapterStatus). */
export interface LibraryJobChapterStatus {
  chapter_number: number;
  title: string;
  has_images: boolean;
  image_count: number;
  /** Already `/media/...`-prefixed and ready to render. */
  image_urls: string[];
  /** "pending" | "running" | "done" | "error". */
  state: string;
  error?: string | null;
}

/** GET /api/images/library/jobs/{job_id} body (LibraryJobStatusResponse). */
export interface LibraryJobStatus {
  job_id: string;
  /** "queued" | "running" | "done" | "error" | "cancelled". */
  state: string;
  title: string;
  /** "none" => image provider not configured in Settings. */
  provider: string;
  panels_per_chapter: number;
  total_chapters: number;
  chapters_done: number;
  chapters: LibraryJobChapterStatus[];
  /** Accreting 1-based chapter -> URLs map; FE persists incrementally. */
  chapter_images: Record<number, string[]>;
  error?: string | null;
  count: number;
  skipped_chapters: number[];
}

/**
 * POST /api/images/library/generate — submit an async whole-story (or
 * single-chapter) comic job. Returns 202 + `job_id` immediately; poll
 * `getLibraryComicJob` for progress. Mode is selected via `opts`:
 *   - { only_missing: true }  → illustrate only chapters lacking panels
 *   - { only_missing: false } → full regenerate of all chapters
 *   - { chapter: N }          → regenerate a single chapter
 * Over-cap / empty-chapter 400s and provider conflicts (409) are raised
 * synchronously at submit, before the 202.
 */
export function submitLibraryComicJob(
  story: Story,
  opts?: { chapter?: number; only_missing?: boolean; provider?: string },
): Promise<LibraryJobAccepted> {
  const body: LibraryImagePayload = { story: toLibraryImagePayload(story) };
  if (opts?.chapter !== undefined) body.chapter = opts.chapter;
  if (opts?.only_missing !== undefined) body.only_missing = opts.only_missing;
  if (opts?.provider) body.provider = opts.provider;
  return apiFetch<LibraryJobAccepted>(`/api/images/library/generate`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** GET /api/images/library/jobs/{job_id} — poll job progress (404 if evicted). */
export function getLibraryComicJob(jobId: string): Promise<LibraryJobStatus> {
  return apiFetch<LibraryJobStatus>(
    `/api/images/library/jobs/${encodeURIComponent(jobId)}`,
    { method: "GET" },
  );
}

/** DELETE /api/images/library/jobs/{job_id} — cooperatively cancel a running job. */
export function cancelLibraryComicJob(jobId: string): Promise<void> {
  return apiFetch<void>(
    `/api/images/library/jobs/${encodeURIComponent(jobId)}`,
    { method: "DELETE" },
  );
}
