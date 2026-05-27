"use client";

/**
 * startedAtStore — sessionStorage helpers that persist a pipeline run's
 * wall-clock start time, keyed by session id.
 *
 * Why sessionStorage (not nuqs URL param):
 *   - The epoch ms is implementation detail, not user navigation intent —
 *     surfacing it in `?startedAt=…` clutters the URL bar and the user can
 *     accidentally edit it.
 *   - sessionStorage auto-clears when the tab closes, which matches the
 *     lifecycle of a single in-flight run; on full browser quit the run is
 *     already gone server-side too.
 *   - Decoupled from `?session=` rewrites, so the URL stays stable when the
 *     bridge updates the session id mid-flight.
 *
 * Used by `PipelineScreen.tsx` to recover the timer baseline after a reload
 * mid-run (the SSE stream resumes via `?session=<id>` but the React state
 * holding `startedAt` is gone).
 */

const PREFIX = "storyforge:pipeline:startedAt:";

function isBrowser(): boolean {
  return typeof window !== "undefined" && typeof window.sessionStorage !== "undefined";
}

function key(sessionId: string): string {
  return PREFIX + sessionId;
}

/** Save the epoch ms when a fresh run began. Silent no-op on SSR / blocked storage. */
export function saveStartedAt(sessionId: string, epochMs: number): void {
  if (!isBrowser() || !sessionId) return;
  try {
    window.sessionStorage.setItem(key(sessionId), String(epochMs));
  } catch {
    // QuotaExceededError / private mode — non-fatal.
  }
}

/**
 * Read the persisted start time for a session, or null when missing/invalid.
 * Tolerates corrupted entries (returns null instead of throwing).
 */
export function loadStartedAt(sessionId: string): number | null {
  if (!isBrowser() || !sessionId) return null;
  try {
    const raw = window.sessionStorage.getItem(key(sessionId));
    if (!raw) return null;
    const n = parseInt(raw, 10);
    return Number.isFinite(n) && n > 0 ? n : null;
  } catch {
    return null;
  }
}

/** Clear the persisted entry. Invoke on run done/error/interrupted. */
export function clearStartedAt(sessionId: string | null | undefined): void {
  if (!isBrowser() || !sessionId) return;
  try {
    window.sessionStorage.removeItem(key(sessionId));
  } catch {
    // ignore
  }
}
