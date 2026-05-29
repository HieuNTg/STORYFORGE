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
import { apiFetch, ApiError } from "./client";
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
   * avatars under the story's own folder (`output/<story-slug>/images/avatars/`,
   * resolved via services.output_paths) so two unrelated stories with
   * same-named characters don't collide. Falls back to the shared `_unsorted`
   * bucket when omitted.
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

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/**
 * Queue portrait generation for every character of a story at once.
 *
 * Fire-and-forget on the backend (mirrors extract-story): FlowKit serializes
 * portraits (~25-30s each), so the server kicks the whole batch off the request
 * path and returns immediately. Use {@link waitForAllAvatars} to poll for the
 * results. Returns the number of portraits the backend accepted.
 */
export async function generateAllCharacterAvatars(
  characters: ForgeCharacter[],
  storyId: string,
  genre?: string,
): Promise<{ accepted: number }> {
  return apiFetch<{ accepted: number }>("/api/characters/avatars/generate", {
    method: "POST",
    body: JSON.stringify({ characters, story_id: storyId, genre }),
  });
}

/**
 * Poll `/avatars/lookup` until every name has a portrait (or the deadline hits).
 *
 * `onTick` fires after each poll with the current name→URL map so the caller can
 * surface portraits as they land and show "done/total" progress. Resolves with
 * the last map seen — partial if some portraits never arrived (e.g. FlowKit
 * disabled), so the caller can decide success vs. partial.
 */
export async function waitForAllAvatars(
  storyId: string,
  names: string[],
  opts?: {
    timeoutMs?: number;
    intervalMs?: number;
    onTick?: (avatars: Record<string, string>) => void;
  },
): Promise<Record<string, string>> {
  const timeoutMs = opts?.timeoutMs ?? 300_000;
  const intervalMs = opts?.intervalMs ?? 4000;
  const deadline = Date.now() + timeoutMs;
  let latest: Record<string, string> = {};
  while (Date.now() < deadline) {
    await sleep(intervalMs);
    try {
      latest = await lookupCharacterAvatars(storyId, names);
      opts?.onTick?.(latest);
      if (names.length > 0 && names.every((n) => latest[n])) return latest;
    } catch {
      /* transient — keep polling until the deadline */
    }
  }
  return latest;
}

/**
 * Poll `/avatars/lookup` until a *new* portrait file appears for `name`.
 *
 * The lookup URL carries a `?v=<mtime>` cache-buster, so a freshly written
 * portrait yields a different string than `priorUrl`. Returns the new URL, or
 * null if nothing newer showed up before the deadline.
 */
async function pollForNewAvatar(
  storyId: string,
  name: string,
  priorUrl: string | null,
  timeoutMs: number,
): Promise<string | null> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    await sleep(3000);
    try {
      const map = await lookupCharacterAvatars(storyId, [name]);
      const url = map[name] ?? null;
      if (url && url !== priorUrl) return url;
    } catch {
      /* transient — keep polling until the deadline */
    }
  }
  return null;
}

/**
 * Regenerate a single character portrait via FlowKit (story-scoped, no backend
 * store needed). Returns the fresh, cache-busted `/media` URL. Slow (~25-30s);
 * the caller shows a spinner.
 *
 * Dev-proxy resilience: in `next dev` the request crosses the rewrite proxy,
 * which resets long upstream connections (~30s) with "socket hang up" -> HTTP
 * 500 even though the backend keeps generating and writes the portrait to disk.
 * The backend route only ever returns 200 / 502 (FlowKit unavailable) / 504
 * (its own timeout) — so a 500, or a raw network throw, means the proxy dropped
 * the response, NOT that generation failed. In that case we recover by polling
 * the on-disk avatar until the new file appears. Production serves a same-origin
 * static export (no proxy), so the POST returns inline and the poll never runs.
 */
export async function regenerateCharacterAvatar(
  character: ForgeCharacter,
  storyId: string,
  genre?: string,
): Promise<{ name: string; avatar_url: string | null }> {
  const name = character.name;

  // Snapshot the current portrait so the recovery poll can tell when a *new*
  // file lands (vs. the one we already had). Best-effort — a failed snapshot
  // just means we treat any returned URL as new.
  let priorUrl: string | null = null;
  try {
    const before = await lookupCharacterAvatars(storyId, [name]);
    priorUrl = before[name] ?? null;
  } catch {
    /* best effort */
  }

  try {
    return await apiFetch<{ name: string; avatar_url: string | null }>(
      "/api/characters/avatar",
      {
        method: "POST",
        body: JSON.stringify({ character, story_id: storyId, genre }),
      },
    );
  } catch (err) {
    // Only a proxy-dropped response is recoverable: a raw network throw (no
    // Response at all) or an HTTP 500 the backend never emits. Genuine backend
    // failures (502 unavailable, 504 timeout, 429 rate-limit) are real — rethrow.
    const proxyDropped = !(err instanceof ApiError) || err.status === 500;
    if (!proxyDropped) throw err;

    const recovered = await pollForNewAvatar(storyId, name, priorUrl, 90_000);
    if (recovered) return { name, avatar_url: recovered };
    throw err;
  }
}
