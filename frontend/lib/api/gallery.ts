"use client";

/**
 * gallery.ts — TanStack Query helpers for the public-shares gallery.
 *
 * Backend endpoint (probed against api/share_routes.py):
 *   GET /api/share/gallery?limit&offset → { items, total, limit, offset }
 *
 * Items contain { share_id, story_title, created_at, expires_at }. They do
 * NOT include genre, length, or cover image — the UI degrades gracefully and
 * the genre/length nuqs filters operate client-side over what we have.
 */

import {
  useInfiniteQuery,
  type InfiniteData,
  type QueryFunctionContext,
} from "@tanstack/react-query";
import { apiFetch } from "@/lib/api/client";

export interface GalleryItem {
  share_id: string;
  story_title: string;
  created_at: string;
  expires_at: string;
  /** Optional fields the backend MAY surface in the future. */
  genre?: string;
  length?: "short" | "medium" | "long";
  cover_url?: string;
}

export interface GalleryPage {
  items: GalleryItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface GalleryFilters {
  genre?: string;
  length?: string;
  pageSize?: number;
}

const DEFAULT_PAGE_SIZE = 24;

export function useGallery(filters: GalleryFilters = {}) {
  const pageSize = filters.pageSize ?? DEFAULT_PAGE_SIZE;
  return useInfiniteQuery<
    GalleryPage,
    Error,
    InfiniteData<GalleryPage>,
    ["gallery", GalleryFilters],
    number
  >({
    queryKey: ["gallery", filters],
    initialPageParam: 0,
    queryFn: async (
      ctx: QueryFunctionContext<["gallery", GalleryFilters], number>,
    ) => {
      const offset = ctx.pageParam ?? 0;
      return apiFetch<GalleryPage>(
        `/api/share/gallery?limit=${pageSize}&offset=${offset}`,
      );
    },
    getNextPageParam: (last) => {
      const next = last.offset + last.limit;
      return next < last.total ? next : undefined;
    },
    staleTime: 60_000,
  });
}

// ---------------------------------------------------------------------------
// Share a library story (localStorage) into the public gallery
// ---------------------------------------------------------------------------

import type { Story } from "@/types/story";

export interface LibraryShareResponse {
  share_id: string;
  story_title: string;
  created_at: string;
  expires_at: string;
  is_public: boolean;
  cover_url: string;
  /** Same-origin share page path, e.g. `/api/share/abc123`. */
  url: string;
}

/**
 * POST /api/share/create-from-library — serialize a library story (chapters,
 * prose, comic-page `/media/...` URLs) and publish it to the gallery.
 *
 * `replaceShareId` (the story's previous gallery share) makes the backend drop
 * the old entry first, so re-publishing never duplicates the story.
 */
export function createLibraryShare(
  story: Story,
  replaceShareId?: string,
): Promise<LibraryShareResponse> {
  return apiFetch<LibraryShareResponse>("/api/share/create-from-library", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      title: story.title,
      genre: story.genre,
      synopsis: story.description,
      chapters: story.chapters.map((ch) => ({
        title: ch.title,
        content: ch.content,
        summary: ch.summary,
        images: ch.images,
      })),
      characters: story.characters.map((c) => ({
        name: c.name,
        role: c.role,
        personality: c.description,
        motivation: c.conflict,
      })),
      is_public: true,
      replace_share_id: replaceShareId ?? "",
    }),
  });
}

export function filterGalleryItems(
  items: GalleryItem[],
  filters: GalleryFilters,
): GalleryItem[] {
  const g = (filters.genre ?? "").trim().toLowerCase();
  const l = (filters.length ?? "").trim().toLowerCase();
  return items.filter((it) => {
    if (g && (it.genre ?? "").toLowerCase() !== g) return false;
    if (l && (it.length ?? "") !== l) return false;
    return true;
  });
}
