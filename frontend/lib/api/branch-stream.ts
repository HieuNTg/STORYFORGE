"use client";

/**
 * branch-stream.ts — typed SSE wrapper for POST /api/branch/{sid}/choose/stream.
 *
 * Backend emits NDJSON-shaped data events with a `type` discriminator:
 *   { type: "chunk", text: "..." }      streaming LLM chunks
 *   { type: "complete", node: {...} }   final branch node
 *   { type: "error", message: "..." }   generation failure
 *
 * Per CLAUDE.md Rule 9 — tests must mock this via msw, not hit a real backend.
 */

import { fetchEventSource } from "@microsoft/fetch-event-source";

export type BranchStreamEvent =
  | { type: "chunk"; text: string }
  | { type: "complete"; node: Record<string, unknown>; generated?: boolean }
  | { type: "error"; message: string };

export interface BranchStreamHandlers {
  onChunk?: (text: string) => void;
  onComplete?: (node: Record<string, unknown>) => void;
  onError?: (message: string) => void;
  onOpen?: () => void;
  onClose?: () => void;
}

export interface BranchStreamRequest {
  sessionId: string;
  choiceIndex: number;
  signal?: AbortSignal;
}

function getCsrf(): string | null {
  if (typeof document === "undefined") return null;
  const m = document.cookie.match(/(?:^|; )csrf_token=([^;]*)/);
  return m ? decodeURIComponent(m[1]) : null;
}

class FatalStreamError extends Error {}

export async function streamBranchChoice(
  req: BranchStreamRequest,
  handlers: BranchStreamHandlers,
): Promise<void> {
  const base = process.env.NEXT_PUBLIC_API_BASE ?? "";
  const url = `${base}/api/branch/${encodeURIComponent(req.sessionId)}/choose/stream`;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Accept: "text/event-stream",
  };
  const csrf = getCsrf();
  if (csrf) headers["X-CSRF-Token"] = csrf;

  await fetchEventSource(url, {
    method: "POST",
    headers,
    credentials: "include",
    body: JSON.stringify({ choice_index: req.choiceIndex }),
    signal: req.signal,
    openWhenHidden: true,
    async onopen(res) {
      if (!res.ok) {
        throw new FatalStreamError(`stream open failed: ${res.status}`);
      }
      handlers.onOpen?.();
    },
    onmessage(ev) {
      if (!ev.data) return;
      let parsed: BranchStreamEvent | null = null;
      try {
        parsed = JSON.parse(ev.data) as BranchStreamEvent;
      } catch {
        return;
      }
      if (parsed.type === "chunk") handlers.onChunk?.(parsed.text);
      else if (parsed.type === "complete") handlers.onComplete?.(parsed.node);
      else if (parsed.type === "error") handlers.onError?.(parsed.message);
    },
    onclose() {
      handlers.onClose?.();
    },
    onerror(err) {
      // Always stop retry — choose() is non-idempotent, retrying would double-apply.
      handlers.onError?.(err instanceof Error ? err.message : String(err));
      throw err;
    },
  });
}
