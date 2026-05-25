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
}): Promise<ForgeCharacter[]> {
  const raw = await apiFetch<unknown>("/api/characters/extract-story", {
    method: "POST",
    body: JSON.stringify({ language: "vi", ...req }),
  });
  return z.array(forgeCharacterSchema).parse(raw);
}
