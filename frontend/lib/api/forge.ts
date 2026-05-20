/**
 * Forge-from-Sentence typed client.
 *
 * - `forgeFromSentence` → sync POST, validated with zod.
 * - `forgeFromSentenceStream` → SSE wrapper via `@microsoft/fetch-event-source`.
 */
import { fetchEventSource } from "@microsoft/fetch-event-source";
import {
  forgeResponseSchema,
  type ForgeRequest,
  type ForgeResponse,
} from "@/types/story";
import { apiFetch } from "./client";

export async function forgeFromSentence(req: ForgeRequest): Promise<ForgeResponse> {
  const raw = await apiFetch<unknown>("/api/forge/sentence", {
    method: "POST",
    body: JSON.stringify(req),
  });
  return forgeResponseSchema.parse(raw);
}

export type ForgeStreamStage =
  | "planning"
  | "characters"
  | "chapter"
  | "choices";

export interface ForgeStreamHandlers {
  onStage?: (stage: ForgeStreamStage) => void;
  onFinal?: (response: ForgeResponse) => void;
  onError?: (err: Error) => void;
  signal?: AbortSignal;
}

/**
 * Streams `forge.stage` then `forge.final` (or `forge.error`).
 * Returns a Promise that resolves on `final`, rejects on `error` or abort.
 */
export function forgeFromSentenceStream(
  req: ForgeRequest,
  handlers: ForgeStreamHandlers = {},
): Promise<ForgeResponse> {
  const base = process.env.NEXT_PUBLIC_API_BASE ?? "";
  const url = (base ? base.replace(/\/+$/, "") : "") + "/api/forge/sentence/stream";

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Accept: "text/event-stream",
  };
  if (typeof document !== "undefined") {
    const m = document.cookie.match(/(?:^|; )csrf_token=([^;]*)/);
    if (m) headers["X-CSRF-Token"] = decodeURIComponent(m[1]);
  }

  return new Promise<ForgeResponse>((resolve, reject) => {
    let settled = false;
    fetchEventSource(url, {
      method: "POST",
      headers,
      body: JSON.stringify(req),
      credentials: "include",
      signal: handlers.signal,
      openWhenHidden: true,
      onopen: async (res) => {
        if (!res.ok) {
          const err = new Error(`forge stream failed: HTTP ${res.status}`);
          if (!settled) {
            settled = true;
            handlers.onError?.(err);
            reject(err);
          }
        }
      },
      onmessage: (msg) => {
        if (settled) return;
        try {
          const payload = msg.data ? JSON.parse(msg.data) : {};
          if (msg.event === "forge.stage" && payload?.stage) {
            handlers.onStage?.(payload.stage as ForgeStreamStage);
          } else if (msg.event === "forge.final") {
            const parsed = forgeResponseSchema.parse(payload);
            settled = true;
            handlers.onFinal?.(parsed);
            resolve(parsed);
          } else if (msg.event === "forge.error") {
            const err = new Error(payload?.message ?? "forge error");
            settled = true;
            handlers.onError?.(err);
            reject(err);
          }
        } catch (e) {
          settled = true;
          const err = e instanceof Error ? e : new Error(String(e));
          handlers.onError?.(err);
          reject(err);
        }
      },
      onerror: (err) => {
        if (settled) return;
        settled = true;
        const e = err instanceof Error ? err : new Error(String(err));
        handlers.onError?.(e);
        reject(e);
        throw e; // stop retries
      },
    });
  });
}
