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
  req: CharacterGenerateRequest,
): Promise<ForgeCharacter> {
  const raw = await apiFetch<unknown>("/api/characters/generate", {
    method: "POST",
    body: JSON.stringify(req),
  });
  return forgeCharacterSchema.parse(raw);
}

export async function extractStoryCharacters(req: {
  title: string;
  description: string;
  setting: string;
  text_context: string;
}): Promise<ForgeCharacter[]> {
  const raw = await apiFetch<unknown>("/api/characters/extract-story", {
    method: "POST",
    body: JSON.stringify(req),
  });
  return z.array(forgeCharacterSchema).parse(raw);
}
