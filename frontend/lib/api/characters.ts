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
