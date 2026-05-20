"use client";

/**
 * branching.ts — TanStack Query helpers for Branch session endpoints.
 *
 * Backend mount: `/api/branch/{sessionId}/...` (see api/branch_routes.py).
 *
 * Queries:
 *   GET /current      → ['branch', sessionId, 'current']
 *   GET /tree         → ['branch', sessionId, 'tree']
 *   GET /tree/layout  → ['branch', sessionId, 'layout']
 *   GET /tree/minimap → ['branch', sessionId, 'minimap']
 *   GET /analytics    → ['branch', sessionId, 'analytics']
 *   GET /bookmarks    → ['branch', sessionId, 'bookmarks']
 *
 * Mutations:
 *   POST /choose, /back, /undo, /redo, /goto
 *   POST /bookmarks, DELETE /bookmarks/{id}, POST /bookmarks/{id}/goto
 *
 * /choose/stream is consumed via usePostStream — not exposed here.
 */

import {
  useQuery,
  useMutation,
  useQueryClient,
  type UseQueryOptions,
} from "@tanstack/react-query";
import { apiFetch } from "@/lib/api/client";

// ---------- Types (mirror branch_routes.py + branch_narrative manager shape) ----------

export interface BranchChoice {
  text?: string;
  index?: number;
  [k: string]: unknown;
}

export interface BranchNode {
  id: string;
  text: string;
  choices: Array<string | BranchChoice>;
  parent?: string | null;
  depth?: number;
  child_ids?: string[];
  bookmark_id?: string | null;
  character_states?: Record<string, { mood?: string; arc_position?: string }>;
  [k: string]: unknown;
}

export interface BranchCurrentResponse {
  node: BranchNode;
}

export interface BranchTreeNode {
  id: string;
  parent?: string | null;
  text?: string;
  depth?: number;
  choices?: Array<string | BranchChoice>;
  child_ids?: string[];
  [k: string]: unknown;
}

/**
 * Backend (`BranchManager.get_tree`) returns:
 *   { session_id, root, current, nodes: { [nodeId]: BranchTreeNode } }
 */
export interface BranchTreeResponse {
  session_id?: string;
  root?: string;
  current?: string;
  nodes: Record<string, BranchTreeNode>;
  [k: string]: unknown;
}

export interface BranchLayoutPos {
  x: number;
  y: number;
}

/**
 * Backend (`BranchManager.get_tree_layout`) returns:
 *   { session_id, root, current, layout: { [nodeId]: {x,y} }, bounds, stats }
 * NOT a flat array — see services/pipeline/branch_narrative.py.
 */
export interface BranchLayoutResponse {
  session_id?: string;
  root?: string;
  current?: string;
  layout: Record<string, BranchLayoutPos>;
  bounds?: {
    min_x?: number;
    max_x?: number;
    max_y?: number;
    width?: number;
    height?: number;
  };
  stats?: { total_nodes?: number; max_depth?: number; leaf_count?: number };
  [k: string]: unknown;
}

export interface BranchMinimapNode {
  id: string;
  x: number;
  y: number;
  is_current?: boolean;
  is_leaf?: boolean;
  has_bookmark?: boolean;
}

export interface BranchMinimapResponse {
  nodes: BranchMinimapNode[];
  edges?: Array<{ from: string; to: string }>;
  bounds?: { min_x?: number; max_x?: number; max_y?: number };
  current?: string;
}

export interface BranchAnalyticsResponse {
  total_choices?: number;
  choice_popularity?: Record<string, number>;
  popular_paths?: Array<{ path: string[]; count: number }>;
  [k: string]: unknown;
}

export interface BranchBookmark {
  id: string;
  node_id: string;
  label?: string;
  created_at?: string;
  [k: string]: unknown;
}

export interface BranchBookmarksResponse {
  bookmarks: BranchBookmark[];
}

// ---------- Query keys ----------

export const branchKeys = {
  current: (sessionId: string) => ["branch", sessionId, "current"] as const,
  tree: (sessionId: string) => ["branch", sessionId, "tree"] as const,
  layout: (sessionId: string) => ["branch", sessionId, "layout"] as const,
  minimap: (sessionId: string) => ["branch", sessionId, "minimap"] as const,
  analytics: (sessionId: string) => ["branch", sessionId, "analytics"] as const,
  bookmarks: (sessionId: string) => ["branch", sessionId, "bookmarks"] as const,
};

// ---------- Queries ----------

export function useBranchCurrent(
  sessionId: string | null,
  opts?: Partial<UseQueryOptions<BranchCurrentResponse, Error>>
) {
  return useQuery<BranchCurrentResponse, Error>({
    queryKey: sessionId ? branchKeys.current(sessionId) : ["branch", null, "current"],
    queryFn: () =>
      apiFetch<BranchCurrentResponse>(
        `/api/branch/${encodeURIComponent(sessionId!)}/current`
      ),
    enabled: !!sessionId,
    staleTime: 5_000,
    ...opts,
  });
}

export function useBranchTree(sessionId: string | null) {
  return useQuery<BranchTreeResponse, Error>({
    queryKey: sessionId ? branchKeys.tree(sessionId) : ["branch", null, "tree"],
    queryFn: () =>
      apiFetch<BranchTreeResponse>(`/api/branch/${encodeURIComponent(sessionId!)}/tree`),
    enabled: !!sessionId,
    staleTime: 10_000,
  });
}

export function useBranchLayout(sessionId: string | null) {
  return useQuery<BranchLayoutResponse, Error>({
    queryKey: sessionId ? branchKeys.layout(sessionId) : ["branch", null, "layout"],
    queryFn: () =>
      apiFetch<BranchLayoutResponse>(
        `/api/branch/${encodeURIComponent(sessionId!)}/tree/layout`
      ),
    enabled: !!sessionId,
    staleTime: 10_000,
  });
}

export function useBranchMinimap(sessionId: string | null) {
  return useQuery<BranchMinimapResponse, Error>({
    queryKey: sessionId ? branchKeys.minimap(sessionId) : ["branch", null, "minimap"],
    queryFn: () =>
      apiFetch<BranchMinimapResponse>(
        `/api/branch/${encodeURIComponent(sessionId!)}/tree/minimap`
      ),
    enabled: !!sessionId,
    staleTime: 10_000,
  });
}

export function useBranchAnalytics(sessionId: string | null) {
  return useQuery<BranchAnalyticsResponse, Error>({
    queryKey: sessionId
      ? branchKeys.analytics(sessionId)
      : ["branch", null, "analytics"],
    queryFn: () =>
      apiFetch<BranchAnalyticsResponse>(
        `/api/branch/${encodeURIComponent(sessionId!)}/analytics`
      ),
    enabled: !!sessionId,
    staleTime: 30_000,
  });
}

export interface BranchUndoRedoStatus {
  can_undo: boolean;
  can_redo: boolean;
}

export function useBranchUndoRedoStatus(sessionId: string | null) {
  return useQuery<BranchUndoRedoStatus, Error>({
    queryKey: sessionId
      ? (["branch", sessionId, "undo-redo"] as const)
      : (["branch", null, "undo-redo"] as const),
    queryFn: () =>
      apiFetch<BranchUndoRedoStatus>(
        `/api/branch/${encodeURIComponent(sessionId!)}/undo-redo-status`
      ),
    enabled: !!sessionId,
    staleTime: 5_000,
  });
}

export function useBranchBookmarks(sessionId: string | null) {
  return useQuery<BranchBookmarksResponse, Error>({
    queryKey: sessionId
      ? branchKeys.bookmarks(sessionId)
      : ["branch", null, "bookmarks"],
    queryFn: () =>
      apiFetch<BranchBookmarksResponse>(
        `/api/branch/${encodeURIComponent(sessionId!)}/bookmarks`
      ),
    enabled: !!sessionId,
    staleTime: 30_000,
  });
}

// ---------- Mutations ----------

function invalidateSession(qc: ReturnType<typeof useQueryClient>, sessionId: string) {
  qc.invalidateQueries({ queryKey: ["branch", sessionId] });
}

export function useChoose(sessionId: string | null) {
  const qc = useQueryClient();
  return useMutation<unknown, Error, { choice_index: number }>({
    mutationFn: (body) =>
      apiFetch(`/api/branch/${encodeURIComponent(sessionId!)}/choose`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => sessionId && invalidateSession(qc, sessionId),
  });
}

export function useBack(sessionId: string | null) {
  const qc = useQueryClient();
  return useMutation<unknown, Error, void>({
    mutationFn: () =>
      apiFetch(`/api/branch/${encodeURIComponent(sessionId!)}/back`, { method: "POST" }),
    onSuccess: () => sessionId && invalidateSession(qc, sessionId),
  });
}

export function useUndo(sessionId: string | null) {
  const qc = useQueryClient();
  return useMutation<unknown, Error, void>({
    mutationFn: () =>
      apiFetch(`/api/branch/${encodeURIComponent(sessionId!)}/undo`, { method: "POST" }),
    onSuccess: () => sessionId && invalidateSession(qc, sessionId),
  });
}

export function useRedo(sessionId: string | null) {
  const qc = useQueryClient();
  return useMutation<unknown, Error, void>({
    mutationFn: () =>
      apiFetch(`/api/branch/${encodeURIComponent(sessionId!)}/redo`, { method: "POST" }),
    onSuccess: () => sessionId && invalidateSession(qc, sessionId),
  });
}

export function useGotoNode(sessionId: string | null) {
  const qc = useQueryClient();
  return useMutation<unknown, Error, { node_id: string }>({
    mutationFn: (body) =>
      apiFetch(`/api/branch/${encodeURIComponent(sessionId!)}/goto`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => sessionId && invalidateSession(qc, sessionId),
  });
}

export function useAddBookmark(sessionId: string | null) {
  const qc = useQueryClient();
  return useMutation<unknown, Error, { node_id: string; label?: string }>({
    mutationFn: (body) =>
      apiFetch(`/api/branch/${encodeURIComponent(sessionId!)}/bookmarks`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => sessionId && invalidateSession(qc, sessionId),
  });
}

export function useDeleteBookmark(sessionId: string | null) {
  const qc = useQueryClient();
  return useMutation<unknown, Error, string>({
    mutationFn: (bookmarkId) =>
      apiFetch(
        `/api/branch/${encodeURIComponent(sessionId!)}/bookmarks/${encodeURIComponent(bookmarkId)}`,
        { method: "DELETE" }
      ),
    onSuccess: () => sessionId && invalidateSession(qc, sessionId),
  });
}

export function useGotoBookmark(sessionId: string | null) {
  const qc = useQueryClient();
  return useMutation<unknown, Error, string>({
    mutationFn: (bookmarkId) =>
      apiFetch(
        `/api/branch/${encodeURIComponent(sessionId!)}/bookmarks/${encodeURIComponent(bookmarkId)}/goto`,
        { method: "POST" }
      ),
    onSuccess: () => sessionId && invalidateSession(qc, sessionId),
  });
}

// ---------- Convenience: invalidator hook ----------

export function useInvalidateBranchSession(sessionId: string | null) {
  const qc = useQueryClient();
  return () => {
    if (sessionId) invalidateSession(qc, sessionId);
  };
}
