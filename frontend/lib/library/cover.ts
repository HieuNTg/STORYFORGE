"use client";

/**
 * cover.ts — best-effort cover art for Library stories.
 *
 * Wraps `POST /api/images/library/generate-cover` (api/image_routes.py) and
 * patches the returned `/media/...` URL onto the story via the library store,
 * which persists it to localStorage and re-renders the bookshelf card.
 *
 * Contract with every save path (Khai sinh auto-save, 1-sentence forge,
 * manual create): the story is ALREADY saved before this is called, and this
 * never throws — a slow or down image provider must not affect the save. The
 * card simply keeps its gradient placeholder until a cover lands.
 */

import { apiFetch } from "@/lib/api/client";
import { useLibraryStore } from "@/stores/library-store";
import type { Story } from "@/types/story";

interface GenerateCoverResponse {
  /** `/media/...` URL, or null when the provider is disabled / failed. */
  cover_url: string | null;
  message: string;
}

/**
 * Fire-and-forget cover generation for a just-saved story. Resolves when the
 * cover has been persisted (or skipped); call sites use `void requestStoryCover(s)`.
 * The backend dedupes concurrent requests per story (409), which this treats
 * like any other failure: silently.
 */
export async function requestStoryCover(story: Story): Promise<void> {
  if (story.coverUrl) return;
  try {
    const res = await apiFetch<GenerateCoverResponse>(
      "/api/images/library/generate-cover",
      {
        method: "POST",
        body: JSON.stringify({
          story_id: story.id,
          title: story.title,
          genre: story.genre,
          synopsis: story.description,
        }),
      },
    );
    if (res.cover_url) {
      useLibraryStore.getState().updateStory(story.id, {
        coverUrl: res.cover_url,
      });
    }
  } catch {
    // Cover is a nice-to-have; the placeholder stays until a retry succeeds.
  }
}
