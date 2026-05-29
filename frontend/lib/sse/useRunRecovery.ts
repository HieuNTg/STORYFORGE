"use client";

/**
 * useRunRecovery — re-attach the UI to a pipeline job whose SSE stream is gone.
 *
 * Why this exists:
 *   `usePostStream` only opens the `POST /api/pipeline/run` stream on a fresh
 *   submit (when `PipelineScreen` has a `pendingBody`). If the page is reloaded
 *   mid-run, or the stream drops (`ECONNRESET`), the component remounts with no
 *   body → no stream → the stepper sits at the default "Outline" phase and the
 *   "Hội thoại tác giả" panel stays empty even though the backend is still
 *   generating. The run itself survives in the job registry.
 *
 * What it does:
 *   When `enabled` and a `sessionId` is present (from `?session=` on reload),
 *   it polls `GET /api/pipeline/run/{id}?since=<cursor>` and replays each
 *   returned log line through the SAME `applySseFrame` bridge the live stream
 *   uses — so phase progression, author bubbles, quality, and partial chapters
 *   rebuild identically. It re-polls with `since = logs_count` so each request
 *   ships only the delta, and stops on a terminal status (firing the matching
 *   bridge frame so `done`/`error`/`interrupted` handlers run exactly as they
 *   would have for a live finish). A 404 (expired session) calls `onExpired`.
 *
 * Pure polling, no `EventSource`: after the original client disconnects the
 * backend stops feeding the progress queue but keeps appending to `job.logs`,
 * so polling the log tail is the only reliable recovery channel.
 */

import { useEffect, useLayoutEffect, useRef } from "react";
import { applySseFrame, type BridgeHandlers } from "@/lib/sse/pipelineBridge";
import { usePipelineStore } from "@/stores/pipeline-store";

/** Mirrors the JSON shape returned by `get_run_status` in pipeline_routes.py. */
interface RunStatusPayload {
  session_id: string;
  status: "pending" | "running" | "done" | "error" | "cancelled";
  logs?: string[];
  logs_count?: number;
  summary?: unknown;
  error?: string | null;
}

export interface UseRunRecoveryOptions {
  /** Session to recover (from `?session=`); null disables the hook. */
  sessionId: string | null;
  /**
   * Gate. Pass `false` while a fresh submit owns the live stream so recovery
   * never races the `POST /run` SSE connection.
   */
  enabled: boolean;
  /** Same handlers passed to the live bridge (onDone / onError / onChapterComplete…). */
  handlers?: BridgeHandlers;
  /** Fired on 404 — the session expired out of the registry; clear `?session=`. */
  onExpired?: () => void;
  /** Poll cadence in ms (default 1500). */
  pollIntervalMs?: number;
}

const DEFAULT_POLL_MS = 1500;
// Give up after this many consecutive transient (non-404) failures so a backend
// outage doesn't spin forever; surface it as an interruption.
const MAX_CONSECUTIVE_ERRORS = 5;

function joinUrl(base: string, path: string): string {
  if (!base) return path;
  if (path.startsWith("http://") || path.startsWith("https://")) return path;
  return base.replace(/\/+$/, "") + "/" + path.replace(/^\/+/, "");
}

function isTerminal(status: RunStatusPayload["status"]): boolean {
  return status === "done" || status === "error" || status === "cancelled";
}

export function useRunRecovery(opts: UseRunRecoveryOptions): void {
  const { sessionId, enabled } = opts;
  // Keep mutable callbacks/config in a ref so changing them never restarts the
  // poll loop (which is keyed only on sessionId + enabled). Synced in a layout
  // effect — React 19 forbids ref writes during render (matches usePostStream).
  const optsRef = useRef(opts);
  useLayoutEffect(() => {
    optsRef.current = opts;
  });

  useEffect(() => {
    if (!enabled || !sessionId) return;

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let cursor = 0;
    let consecutiveErrors = 0;
    const controller = new AbortController();

    // Reflect "we are actively recovering this session" immediately so the
    // timer baseline + session id are wired before the first poll resolves.
    // The first poll's status corrects this if the job already finished.
    const store = usePipelineStore.getState();
    store.setSessionId(sessionId);
    if (store.status === "idle") store.setStatus("running");

    const base = process.env.NEXT_PUBLIC_API_BASE ?? "";

    const schedule = () => {
      if (cancelled) return;
      const interval = optsRef.current.pollIntervalMs ?? DEFAULT_POLL_MS;
      timer = setTimeout(poll, interval);
    };

    const poll = async () => {
      if (cancelled) return;
      const url = joinUrl(
        base,
        `/api/pipeline/run/${encodeURIComponent(sessionId)}?since=${cursor}`,
      );
      let res: Response;
      try {
        res = await fetch(url, {
          method: "GET",
          credentials: "include",
          headers: { Accept: "application/json" },
          signal: controller.signal,
        });
      } catch {
        if (cancelled) return;
        if (++consecutiveErrors >= MAX_CONSECUTIVE_ERRORS) {
          applySseFrame({ type: "interrupted" }, optsRef.current.handlers);
          return;
        }
        schedule();
        return;
      }

      if (cancelled) return;

      if (res.status === 404) {
        // Session aged out of the registry — nothing left to recover.
        optsRef.current.onExpired?.();
        return;
      }
      if (!res.ok) {
        if (++consecutiveErrors >= MAX_CONSECUTIVE_ERRORS) {
          applySseFrame({ type: "interrupted" }, optsRef.current.handlers);
          return;
        }
        schedule();
        return;
      }

      consecutiveErrors = 0;
      let payload: RunStatusPayload;
      try {
        payload = (await res.json()) as RunStatusPayload;
      } catch {
        schedule();
        return;
      }
      if (cancelled) return;

      const handlers = optsRef.current.handlers;
      const lines = payload.logs ?? [];
      for (const line of lines) {
        applySseFrame({ type: "log", data: line }, handlers);
      }
      // Advance the cursor by the authoritative total when present so a clamped
      // (out-of-range) server response can't desync us.
      cursor =
        typeof payload.logs_count === "number"
          ? payload.logs_count
          : cursor + lines.length;

      if (isTerminal(payload.status)) {
        if (payload.status === "done") {
          applySseFrame({ type: "done", data: payload.summary }, handlers);
        } else if (payload.status === "error") {
          applySseFrame(
            { type: "error", data: payload.error || "Pipeline thất bại" },
            handlers,
          );
        } else {
          applySseFrame(
            { type: "interrupted", data: payload.error ?? undefined },
            handlers,
          );
        }
        return; // terminal → stop polling
      }

      schedule();
    };

    // Kick off immediately.
    void poll();

    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
      controller.abort();
    };
  }, [sessionId, enabled]);
}
