"use client";

/**
 * usePostStream — POST-body SSE hook backed by `@microsoft/fetch-event-source`.
 *
 * Why not `useEventSource`? The backend SSE entry points (`POST /api/pipeline/run`,
 * `/pipeline/continue`, …) require a JSON body, which native `EventSource` does
 * not support (R1.1 mitigation in phase-01 spec). `fetch-event-source` is the
 * canonical drop-in.
 *
 * Cleanup: aborts the in-flight stream on unmount or when `body` reference
 * changes. Callers should memoise `body` to avoid reconnect churn.
 */

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import {
  fetchEventSource,
  type EventSourceMessage,
} from "@microsoft/fetch-event-source";

export type StreamReadyState = "idle" | "connecting" | "open" | "closed" | "error";

export interface UsePostStreamOptions {
  /** Endpoint path (relative to NEXT_PUBLIC_API_BASE) or absolute URL. */
  url: string | null;
  /** JSON body. Pass the same reference between renders to avoid reconnects. */
  body: Record<string, unknown> | null;
  /** Fires for every `data:` frame. */
  onMessage: (event: EventSourceMessage) => void;
  /** Optional error callback. */
  onError?: (err: unknown) => void;
  /** Optional open callback (fires once on stream open). */
  onOpen?: () => void;
  /**
   * Optional close callback (fires when the server closes the stream
   * gracefully — i.e. NOT on error/abort). Lets callers detect a stream that
   * ended without a terminal application frame (e.g. backend restart, dropped
   * connection) so they can move their own state out of a "running" limbo.
   */
  onClose?: () => void;
}

export interface UsePostStreamResult {
  readyState: StreamReadyState;
  /** Manually abort the in-flight stream. */
  abort: () => void;
}

function joinUrl(base: string, path: string): string {
  if (!base) return path;
  if (path.startsWith("http://") || path.startsWith("https://")) return path;
  return base.replace(/\/+$/, "") + "/" + path.replace(/^\/+/, "");
}

function getCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(
    new RegExp("(?:^|; )" + name.replace(/([.$?*|{}()[\]\\/+^])/g, "\\$1") + "=([^;]*)")
  );
  return match ? decodeURIComponent(match[1]) : null;
}

export function usePostStream(opts: UsePostStreamOptions): UsePostStreamResult {
  const { url, body } = opts;
  const [readyState, setReadyState] = useState<StreamReadyState>("idle");
  const abortRef = useRef<AbortController | null>(null);
  const onMessageRef = useRef(opts.onMessage);
  const onErrorRef = useRef(opts.onError);
  const onOpenRef = useRef(opts.onOpen);
  const onCloseRef = useRef(opts.onClose);
  // Sync callback refs in a layout effect — React 19 forbids ref writes
  // during render and useEffect would lag the first paint by a tick.
  useLayoutEffect(() => {
    onMessageRef.current = opts.onMessage;
    onErrorRef.current = opts.onError;
    onOpenRef.current = opts.onOpen;
    onCloseRef.current = opts.onClose;
  });

  useEffect(() => {
    if (!url || !body) {
      return;
    }

    const controller = new AbortController();
    abortRef.current = controller;
    // Note: do not setReadyState("connecting") synchronously here — React
    // 19 disallows in-effect setState. The first transition is reported by
    // the async `onopen` callback below.

    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    };
    const csrf = getCookie("csrf_token");
    if (csrf) headers["X-CSRF-Token"] = csrf;

    const base = process.env.NEXT_PUBLIC_API_BASE ?? "";
    const fullUrl = joinUrl(base, url);

    fetchEventSource(fullUrl, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
      signal: controller.signal,
      credentials: "include",
      openWhenHidden: true,
      async onopen(res) {
        if (!res.ok) {
          setReadyState("error");
          throw new Error(`SSE ${res.status}`);
        }
        setReadyState("open");
        onOpenRef.current?.();
      },
      onmessage(ev) {
        onMessageRef.current?.(ev);
      },
      onclose() {
        setReadyState("closed");
        onCloseRef.current?.();
      },
      onerror(err) {
        setReadyState("error");
        onErrorRef.current?.(err);
        // Throw to stop automatic retry (we'd rather surface to caller).
        throw err;
      },
    }).catch((err) => {
      if (controller.signal.aborted) return;
      onErrorRef.current?.(err);
    });

    return () => {
      controller.abort();
      abortRef.current = null;
    };
  }, [url, body]);

  return {
    readyState,
    abort: () => {
      abortRef.current?.abort();
      abortRef.current = null;
    },
  };
}
