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

export interface GenerateImagesResponse {
  image_paths: string[];
  message: string;
  count: number;
  chapter_images: Record<number, string[]>;
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

export function generateAllImages(
  sessionId: string,
  provider?: string,
): Promise<GenerateImagesResponse> {
  const body: { provider?: string } = {};
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
