/**
 * Character traits generation client.
 *
 * Mirrors `forge.ts` pattern: typed POST, validated with zod.
 */
import {
  forgeCharacterSchema,
  type CharacterGenerateRequest,
  type ForgeCharacter,
} from "@/types/story";
import { apiFetch } from "./client";
import { z } from "zod";

export async function generateCharacter(
  req: CharacterGenerateRequest & { language?: string },
): Promise<ForgeCharacter> {
  const raw = await apiFetch<unknown>("/api/characters/generate", {
    method: "POST",
    body: JSON.stringify({ language: "vi", ...req }),
  });
  return forgeCharacterSchema.parse(raw);
}

export async function extractStoryCharacters(req: {
  title: string;
  description: string;
  setting: string;
  text_context: string;
  /**
   * Source story language. Drives the output language of every text field
   * on the returned characters. Defaults to "vi" server-side.
   */
  language?: string;
  /**
   * Optional library story id. When provided, the backend writes generated
   * avatars under `output/images/avatars/<story_id>/` so two unrelated
   * stories with same-named characters don't collide. Falls back to the
   * legacy unscoped directory when omitted.
   */
  story_id?: string;
  /**
   * Optional Vietnamese genre label (e.g. "Tiên Hiệp"). Drives the avatar
   * prompt's style anchor so a sci-fi character doesn't come back wearing
   * hanfu. Unknown / empty falls back to a generic anime baseline.
   */
  genre?: string;
}): Promise<ForgeCharacter[]> {
  const raw = await apiFetch<unknown>("/api/characters/extract-story", {
    method: "POST",
    body: JSON.stringify({ language: "vi", ...req }),
  });
  return z.array(forgeCharacterSchema).parse(raw);
}

/**
 * Look up existing on-disk portraits for a story's characters.
 *
 * Backed by the store-independent `character_avatar` system, so it works for
 * localStorage-only library stories (which 404 on /api/images/{id}/profiles).
 * Returns a name→/media-URL map; names without a portrait are omitted.
 */
export async function lookupCharacterAvatars(
  storyId: string,
  names: string[],
): Promise<Record<string, string>> {
  const raw = await apiFetch<{ avatars?: Record<string, string> }>(
    "/api/characters/avatars/lookup",
    {
      method: "POST",
      body: JSON.stringify({ story_id: storyId, names }),
    },
  );
  return raw.avatars ?? {};
}

/**
 * Regenerate a single character portrait via FlowKit (story-scoped, no backend
 * store needed). Returns the fresh, cache-busted `/media` URL. Slow (~25-30s);
 * the caller shows a spinner.
 */
export async function regenerateCharacterAvatar(
  character: ForgeCharacter,
  storyId: string,
  genre?: string,
): Promise<{ name: string; avatar_url: string | null }> {
  return apiFetch<{ name: string; avatar_url: string | null }>(
    "/api/characters/avatar",
    {
      method: "POST",
      body: JSON.stringify({ character, story_id: storyId, genre }),
    },
  );
}
