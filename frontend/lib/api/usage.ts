"use client";

/**
 * usage.ts — TanStack Query helpers for token / cost usage.
 *
 * Backend endpoints probed against api/usage_routes.py:
 *   GET /api/usage/session          → SessionSummary
 *   GET /api/usage/story/{filename} → per-checkpoint sidecar { events, totals }
 *
 * Daily breakdown: the backend does NOT expose a `/api/usage/daily` endpoint
 * today. The Usage page derives a daily chart from the per-story sidecars'
 * events when available; the page surfaces a "Backend endpoint pending"
 * banner when no breakdown can be computed.
 *
 * RBAC: production gates analytics under ACCESS_ANALYTICS. We `retry: false`
 * so a 403 fails fast without thrashing.
 */

import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api/client";

export interface UsageLayerBreakdown {
  tokens: number;
  cost_usd: number;
}

export interface SessionUsageSummary {
  call_count: number;
  total_prompt_tokens: number;
  total_completion_tokens: number;
  total_tokens: number;
  total_cost_usd: number;
  by_story: Record<string, UsageLayerBreakdown>;
  by_model: Record<string, UsageLayerBreakdown>;
}

export interface UsageEvent {
  at?: string;
  model?: string;
  prompt_tokens?: number;
  completion_tokens?: number;
  total_tokens?: number;
  cost_usd?: number;
  [k: string]: unknown;
}

export interface UsageSidecar {
  events: UsageEvent[];
  totals: {
    total_tokens: number;
    total_cost_usd: number;
    call_count: number;
  };
}

export function useUsageSession() {
  return useQuery<SessionUsageSummary, Error>({
    queryKey: ["usage", "session-full"],
    queryFn: () => apiFetch<SessionUsageSummary>("/api/usage/session"),
    staleTime: 60_000,
    retry: false,
  });
}

export function useUsageStorySidecar(filename: string | null) {
  return useQuery<UsageSidecar, Error>({
    queryKey: ["usage", "story", filename],
    queryFn: () =>
      apiFetch<UsageSidecar>(
        `/api/usage/story/${encodeURIComponent(filename!)}`,
      ),
    enabled: !!filename,
    staleTime: 60_000,
    retry: false,
  });
}

/** Reduce sidecar events into per-day token + cost totals (UTC date keys). */
export interface DailyPoint {
  day: string;
  tokens: number;
  cost: number;
}

export function eventsToDaily(events: UsageEvent[]): DailyPoint[] {
  const map = new Map<string, DailyPoint>();
  for (const e of events) {
    const ts = e.at ? Date.parse(e.at) : NaN;
    if (!Number.isFinite(ts)) continue;
    const day = new Date(ts).toISOString().slice(0, 10);
    const tokens = e.total_tokens ?? (e.prompt_tokens ?? 0) + (e.completion_tokens ?? 0);
    const cost = e.cost_usd ?? 0;
    const cur = map.get(day);
    if (cur) {
      cur.tokens += tokens;
      cur.cost += cost;
    } else {
      map.set(day, { day, tokens, cost });
    }
  }
  return Array.from(map.values()).sort((a, b) => (a.day < b.day ? -1 : 1));
}
