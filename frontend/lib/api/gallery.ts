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
