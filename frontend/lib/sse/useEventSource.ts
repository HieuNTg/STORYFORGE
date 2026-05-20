"use client";

/**
 * Skeleton hook per phase-01 spec. Real wiring (reconnect/backoff, sniffer
 * dispatch, message routing) lands in Phase 1 — this scaffold establishes the
 * signature and lifecycle (cleanup on unmount + url change) so Phase 1 code
 * has a stable import target.
 *
 *   useEventSource(url, { onMessage, onError?, eventTypes? }) → { readyState }
 *
 * `readyState` follows the standard EventSource constants
 * (0 CONNECTING, 1 OPEN, 2 CLOSED). A null `url` means "do not connect".
 */

import { useEffect, useRef, useState } from "react";

export interface UseEventSourceOptions {
  /** Default `message` handler. Fires for unnamed events. */
  onMessage: (ev: MessageEvent) => void;
  /** Optional error handler (network / parse / server-side). */
  onError?: (ev: Event) => void;
  /** Named SSE event types to subscribe to (in addition to default `message`). */
  eventTypes?: readonly string[];
}

export interface UseEventSourceResult {
  /** EventSource.readyState. `null` while idle (no url). */
  readyState: number | null;
}

export function useEventSource(
  url: string | null,
  opts: UseEventSourceOptions
): UseEventSourceResult {
  const [readyState, setReadyState] = useState<number | null>(null);
  // Keep latest callbacks in refs so re-renders don't tear down the stream.
  const onMessageRef = useRef(opts.onMessage);
  const onErrorRef = useRef(opts.onError);
  onMessageRef.current = opts.onMessage;
  onErrorRef.current = opts.onError;

  useEffect(() => {
    if (!url) {
      setReadyState(null);
      return;
    }

    const es = new EventSource(url, { withCredentials: false });
    setReadyState(es.readyState);

    const handleOpen = () => setReadyState(es.readyState);
    const handleMessage = (ev: MessageEvent) => onMessageRef.current?.(ev);
    const handleError = (ev: Event) => {
      setReadyState(es.readyState);
      onErrorRef.current?.(ev);
    };

    es.addEventListener("open", handleOpen);
    es.addEventListener("message", handleMessage);
    es.addEventListener("error", handleError);

    const named = opts.eventTypes ?? [];
    for (const type of named) {
      es.addEventListener(type, handleMessage as EventListener);
    }

    return () => {
      es.removeEventListener("open", handleOpen);
      es.removeEventListener("message", handleMessage);
      es.removeEventListener("error", handleError);
      for (const type of named) {
        es.removeEventListener(type, handleMessage as EventListener);
      }
      es.close();
      setReadyState(null);
    };
    // `eventTypes` is intentionally part of the effect deps; pass a stable
    // reference (e.g. memoised array) at call sites to avoid reconnect churn.
  }, [url, opts.eventTypes]);

  return { readyState };
}
