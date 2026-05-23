"use client";

/**
 * queries.ts — TanStack Query helpers for StoryForge API.
 *
 * Endpoints discovered from `api/pipeline_routes.py`:
 *   GET  /api/pipeline/genres   → choices
 *   GET  /api/pipeline/stories  → paginated story list (limit/offset, total)
 *   GET  /api/pipeline/checkpoints/{filename} → single story detail
 *
 * Defaults: genres stale forever (rarely change), stories 30s.
 */

import {
  useQuery,
  useInfiniteQuery,
  useMutation,
  useQueryClient,
  type InfiniteData,
  type QueryFunctionContext,
} from "@tanstack/react-query";
import { apiFetch } from "@/lib/api/client";
import {
  configResponseSchema,
  allProviderStatusSchema,
  sessionUsageSchema,
  type ConfigResponse,
  type ConfigUpdate,
  type AllProviderStatus,
  type SessionUsage,
} from "@/lib/schemas/config";

// ---------- Types ----------

export interface GenreChoices {
  genres: string[];
  styles: string[];
  drama_levels: string[];
  languages: Array<{ code: string; label: string }>;
}

export interface StorySummary {
  filename: string;
  title: string;
  genre: string;
  chapter_count: number;
  current_layer: number;
  size_kb: number;
  modified: string;
}

export interface StoriesPage {
  items: StorySummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface StoriesFilters {
  q?: string;
  sort?: "recent" | "title" | "length";
  pageSize?: number;
}

export interface CreateStoryRequest {
  title?: string;
  genre: string;
  style: string;
  language: string;
  idea: string;
  num_chapters: number;
  num_characters: number;
  word_count: number;
  num_sim_rounds: number;
  drama_level: string;
  enable_agents: boolean;
  enable_quality_gate: boolean;
  [key: string]: unknown;
}

// ---------- Queries ----------

export function useGenres() {
  return useQuery<GenreChoices>({
    queryKey: ["genres"],
    queryFn: () => apiFetch<GenreChoices>("/api/pipeline/genres"),
    staleTime: Infinity,
  });
}

// Backend exposes story detail via the pipeline checkpoints endpoint
// (`GET /api/pipeline/checkpoints/{filename}` — see api/pipeline_routes.py).
// There is no separate `/api/stories/{id}` route. `id` here is the
// checkpoint filename returned by `useStories()`.
export interface StoryChapter {
  number?: number;
  title?: string;
  content?: string;
  word_count?: number;
  [k: string]: unknown;
}

export interface StoryDetail {
  title?: string;
  filename?: string;
  genre?: string;
  language?: string;
  chapters?: StoryChapter[];
  draft?: { chapters?: StoryChapter[]; [k: string]: unknown };
  characters?: Array<{ name?: string; role?: string; personality?: string; [k: string]: unknown }>;
  analytics?: Record<string, unknown>;
  quality?: Record<string, unknown>;
  word_count?: number;
  [k: string]: unknown;
}

export function useStory(filename: string | null) {
  return useQuery<StoryDetail, Error>({
    queryKey: ["story", filename],
    queryFn: () =>
      apiFetch<StoryDetail>(
        `/api/pipeline/checkpoints/${encodeURIComponent(filename!)}`
      ),
    enabled: !!filename,
    staleTime: 30_000,
  });
}

/**
 * Analytics for a *story* (not a branch session). Reuses `useStory` data —
 * the backend embeds analytics + quality fields in the checkpoint payload, so
 * a separate endpoint is not required. The hook just selects/normalises.
 */
export interface StoryAnalytics {
  wordCount: number;
  chapterCount: number;
  averageWords: number;
  qualityScore: number | null;
  chapters: Array<{ number: number; title: string; wordCount: number }>;
  events: Array<{ label: string; at?: string }>;
}

export function useStoryAnalytics(filename: string | null) {
  return useQuery<StoryAnalytics, Error>({
    queryKey: ["story", filename, "analytics"],
    queryFn: async () => {
      const story = await apiFetch<StoryDetail>(
        `/api/pipeline/checkpoints/${encodeURIComponent(filename!)}`
      );
      const chapters: StoryChapter[] =
        story.chapters ?? story.draft?.chapters ?? [];
      const chapterRows = chapters.map((c, i) => ({
        number: typeof c.number === "number" ? c.number : i + 1,
        title: c.title ?? `Chương ${i + 1}`,
        wordCount: typeof c.word_count === "number" ? c.word_count : (c.content ?? "").split(/\s+/).length,
      }));
      const wordCount =
        typeof story.word_count === "number"
          ? story.word_count
          : chapterRows.reduce((a, c) => a + c.wordCount, 0);
      const averageWords =
        chapterRows.length > 0 ? Math.round(wordCount / chapterRows.length) : 0;
      const q = story.quality as Record<string, unknown> | undefined;
      const qualityScore =
        typeof q?.overall === "number" ? (q.overall as number) :
        typeof q?.score === "number" ? (q.score as number) : null;
      const eventsRaw = (story.analytics as { events?: unknown })?.events;
      const events = Array.isArray(eventsRaw)
        ? eventsRaw
            .filter((e): e is { label: string; at?: string } =>
              !!e && typeof e === "object" && typeof (e as { label?: unknown }).label === "string")
            .slice(0, 20)
        : [];
      return {
        wordCount,
        chapterCount: chapterRows.length,
        averageWords,
        qualityScore,
        chapters: chapterRows,
        events,
      };
    },
    enabled: !!filename,
    staleTime: 30_000,
  });
}

/**
 * `useInfiniteQuery` for the paginated story list.
 *
 * Backend uses offset paging (no cursors). We use offset as the page param.
 * Client-side filter+sort because backend does not yet expose q/sort params.
 */
export function useStories(filters: StoriesFilters = {}) {
  const pageSize = filters.pageSize ?? 20;
  return useInfiniteQuery<
    StoriesPage,
    Error,
    InfiniteData<StoriesPage>,
    ["stories", StoriesFilters],
    number
  >({
    queryKey: ["stories", filters],
    initialPageParam: 0,
    queryFn: async (ctx: QueryFunctionContext<["stories", StoriesFilters], number>) => {
      const offset = ctx.pageParam ?? 0;
      return apiFetch<StoriesPage>(
        `/api/pipeline/stories?limit=${pageSize}&offset=${offset}`
      );
    },
    getNextPageParam: (last) => {
      const next = last.offset + last.limit;
      return next < last.total ? next : undefined;
    },
    staleTime: 30_000,
  });
}

// ---------- Mutations ----------

export interface CreateStoryResult {
  session_id?: string | null;
}

/**
 * Stub `useCreateStory` — does NOT POST. The actual generation is a streaming
 * endpoint consumed by `usePostStream`. We use this mutation only as a
 * trigger to flip the UI into "generating" mode + persist the session id once
 * the first SSE `session` frame arrives.
 *
 * Phase-01 spec calls for a `useMutation`, but the backend has no non-stream
 * `POST /api/stories` analog. The pipeline page wires the form submit
 * directly to `usePostStream` and stores the session id from the first frame.
 */
export function useCreateStory() {
  return useMutation<CreateStoryResult, Error, CreateStoryRequest>({
    mutationFn: async (req) => {
      // No-op: caller hands the request to usePostStream. Returning the body
      // shape keeps the hook signature stable for future non-stream variants.
      return { session_id: null, ...((req as unknown) as object) } as CreateStoryResult;
    },
  });
}

// ---------- Client-side helpers ----------

// ---------- Config (Settings page) ----------

/**
 * GET /api/config — current settings with masked secrets.
 *
 * Defense-in-depth (F3/F17): cache lifetime is zero. The response body
 * carries masked-only secrets today, but if the backend ever regresses to
 * plaintext we don't want stale copies sitting in Query cache or in any
 * service-worker / browser cache after the settings page unmounts.
 *  - `staleTime: 0` → every mount triggers a fresh fetch.
 *  - `gcTime: 0`    → cache entry is GC'd as soon as the last observer unmounts.
 */
export function useConfig() {
  return useQuery<ConfigResponse, Error>({
    queryKey: ["config"],
    queryFn: async () => {
      const raw = await apiFetch<unknown>("/api/config");
      return configResponseSchema.parse(raw);
    },
    staleTime: 0,
    gcTime: 0,
  });
}

/**
 * PUT /api/config — partial update. Invalidates ['config'] on success so
 * the next render shows the freshly-masked secrets returned by the server.
 *
 * IMPORTANT: caller MUST NOT spread the raw config response into the mutation
 * payload — that would echo masked strings back as real values. Always pass
 * only fields the user changed.
 */
export function useUpdateConfig() {
  const qc = useQueryClient();
  return useMutation<{ status: string }, Error, ConfigUpdate>({
    mutationFn: (body) =>
      apiFetch<{ status: string }>("/api/config", {
        method: "PUT",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["config"] });
    },
  });
}

// ---------- FlowKit (Settings → Provider=flowkit) ----------

export interface FlowkitStatus {
  connected: boolean;
  last_token_age_s: number;
  pending_ws_requests: number;
  poll_running: boolean;
  workers_current: number;
  workers_max: number;
}

export function useFlowkitStatus(enabled: boolean) {
  return useQuery<FlowkitStatus, Error>({
    queryKey: ["flowkit", "status"],
    queryFn: () => apiFetch<FlowkitStatus>("/api/flowkit/status"),
    enabled,
    refetchInterval: enabled ? 5_000 : false,
    staleTime: 2_000,
  });
}

// ---------- Providers (Providers page) ----------

/**
 * GET /api/providers/status — live rate-limit + model availability for each
 * configured provider. The data also derives the LLM profile list directly
 * from the config response, so we surface both here for the UI.
 */
export function useProviderStatus() {
  return useQuery<AllProviderStatus, Error>({
    queryKey: ["providers", "status"],
    queryFn: async () => {
      const raw = await apiFetch<unknown>("/api/providers/status");
      return allProviderStatusSchema.parse(raw);
    },
    staleTime: 30_000,
  });
}

/**
 * POST /api/config/test-connection — runs primary + every fallback profile
 * against the configured `base_url`. Returns per-profile pass/fail.
 */
export interface ConnectionTestProfile {
  name: string;
  ok: boolean | null;
  message: string;
}
export interface ConnectionTestResult {
  ok: boolean;
  message: string;
  profiles: ConnectionTestProfile[];
}

export function useTestConnection() {
  return useMutation<ConnectionTestResult, Error, void>({
    mutationFn: () =>
      apiFetch<ConnectionTestResult>("/api/config/test-connection", {
        method: "POST",
        body: "{}",
      }),
  });
}

/**
 * PATCH /api/config/profiles/{index}/toggle — toggle a fallback profile's
 * `enabled` flag. Backend takes the index as path param.
 */
export function useToggleProfile() {
  const qc = useQueryClient();
  return useMutation<{ status: string; enabled: boolean }, Error, number>({
    mutationFn: (index) =>
      apiFetch<{ status: string; enabled: boolean }>(
        `/api/config/profiles/${index}/toggle`,
        { method: "PATCH" },
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["config"] });
    },
  });
}

/**
 * PUT /api/config/profiles/{index} — replace a fallback profile in place.
 * Pass `api_key: ""` to keep the existing stored key (backend preserves it).
 */
export interface ProfileUpdate {
  index: number;
  name: string;
  base_url: string;
  api_key: string;
  model: string;
  enabled: boolean;
}

export function useUpdateProfile() {
  const qc = useQueryClient();
  return useMutation<{ status: string }, Error, ProfileUpdate>({
    mutationFn: ({ index, ...body }) =>
      apiFetch<{ status: string }>(`/api/config/profiles/${index}`, {
        method: "PUT",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["config"] });
    },
  });
}

/**
 * DELETE /api/config/profiles/{index} — remove a fallback profile by index.
 */
export function useDeleteProfile() {
  const qc = useQueryClient();
  return useMutation<{ status: string; remaining: number }, Error, number>({
    mutationFn: (index) =>
      apiFetch<{ status: string; remaining: number }>(
        `/api/config/profiles/${index}`,
        { method: "DELETE" },
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["config"] });
    },
  });
}

// ---------- Usage (Account page) ----------

/**
 * GET /api/usage/session — server-session aggregated token + cost totals.
 * Used by the Account page to surface "tokens used" stat. Read-only.
 */
export function useSessionUsage() {
  return useQuery<SessionUsage, Error>({
    queryKey: ["usage", "session"],
    queryFn: async () => {
      const raw = await apiFetch<unknown>("/api/usage/session");
      return sessionUsageSchema.parse(raw);
    },
    staleTime: 30_000,
    // Usage endpoint is RBAC-gated in production; soft-fail to zero totals.
    retry: false,
  });
}

export function filterAndSortStories(
  items: StorySummary[],
  filters: StoriesFilters
): StorySummary[] {
  const q = (filters.q ?? "").trim().toLowerCase();
  const list = q
    ? items.filter(
        (s) =>
          s.title.toLowerCase().includes(q) ||
          s.genre.toLowerCase().includes(q)
      )
    : items;
  const sort = filters.sort ?? "recent";
  const sorted = list.slice();
  if (sort === "title") {
    sorted.sort((a, b) => a.title.localeCompare(b.title, "vi"));
  } else if (sort === "length") {
    sorted.sort((a, b) => b.chapter_count - a.chapter_count);
  } else {
    sorted.sort((a, b) => (a.modified < b.modified ? 1 : -1));
  }
  return sorted;
}
