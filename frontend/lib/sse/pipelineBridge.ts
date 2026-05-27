"use client";

/**
 * pipelineBridge — dispatches SSE log events into the pipeline + theater stores.
 *
 * Backend frames are JSON objects emitted as `data: {type, data}\n\n`. The
 * frame `type` discriminates: `log` (free-form Vietnamese/English string),
 * `stream` (partial chapter text), `session`, `done`, `error`, `interrupted`.
 *
 * Sniffers run only against `log` payloads. Phase progression is derived from
 * the same string via `detectPhaseFromLog`.
 */

import { sniffChapterCompletion } from "@/lib/sse/sniffers";
import { usePipelineStore, detectPhaseFromLog } from "@/stores/pipeline-store";
import { useTheaterStore } from "@/stores/theater-store";

export type SseFrame =
  | { type: "session"; session_id?: string }
  | { type: "log"; data: string }
  | { type: "stream"; data: string }
  | { type: "done"; data: unknown }
  | { type: "error"; data: string }
  | { type: "interrupted"; data?: string };

export interface BridgeHandlers {
  /** Called for `stream` frames (partial chapter text). */
  onStream?: (partial: string) => void;
  /** Called for `done` frames; payload is whatever the backend serialised. */
  onDone?: (payload: unknown) => void;
  /** Called for `error` frames. */
  onError?: (msg: string) => void;
  /** Called when a chapter completion is sniffed; suitable for toast. */
  onChapterComplete?: (label: string) => void;
  /** Called when `interrupted` frames arrive. */
  onInterrupted?: (msg: string | null) => void;
}

/**
 * Apply a parsed SSE frame to the pipeline + theater stores.
 *
 * Stateless — reads the stores via `getState()` so it is safe to call from
 * within an effect or fetch callback.
 */
export function applySseFrame(frame: SseFrame, handlers?: BridgeHandlers): void {
  const pipeline = usePipelineStore.getState();
  const theater = useTheaterStore.getState();

  switch (frame.type) {
    case "session": {
      pipeline.setSessionId(frame.session_id ?? null);
      return;
    }
    case "log": {
      const msg = frame.data;
      if (typeof msg !== "string" || msg.length === 0) return;
      const nextPhase = detectPhaseFromLog(msg, pipeline.currentPhase);
      if (nextPhase !== pipeline.currentPhase) {
        pipeline.setCurrentPhase(nextPhase);
      }
      theater.applyLog(msg);
      const chapterLabel = sniffChapterCompletion(msg);
      if (chapterLabel && handlers?.onChapterComplete) {
        handlers.onChapterComplete(chapterLabel);
      }
      return;
    }
    case "stream": {
      // Feed partial chapter prose into the active author's bubble so the
      // "Hội thoại tác giả" panel shows real generated text, not just status
      // pings. Caller can still observe the raw frame via `onStream`.
      theater.applyStream(frame.data);
      handlers?.onStream?.(frame.data);
      return;
    }
    case "done": {
      // The store applies whatever it understands; rest is handed back to caller.
      theater.applyDone(
        (frame.data && typeof frame.data === "object"
          ? { data: (frame.data as Record<string, unknown>).data ?? frame.data }
          : { data: {} }) as Parameters<typeof theater.applyDone>[0]
      );
      pipeline.setStatus("done");
      pipeline.setCurrentPhase(pipeline.phases.length - 1);
      handlers?.onDone?.(frame.data);
      return;
    }
    case "error": {
      pipeline.pushError(frame.data || "Generation failed");
      pipeline.setStatus("error");
      handlers?.onError?.(frame.data || "Generation failed");
      return;
    }
    case "interrupted": {
      pipeline.setStatus("interrupted");
      handlers?.onInterrupted?.(frame.data ?? null);
      return;
    }
  }
}

/**
 * Convenience wrapper: parse a raw `data:` line text and apply.
 * Returns the parsed frame, or null if the line was not parsable.
 */
export function applySseEventToStores(
  event: MessageEvent | { data: string },
  handlers?: BridgeHandlers
): SseFrame | null {
  const raw = typeof event.data === "string" ? event.data : "";
  if (!raw) return null;
  let frame: SseFrame | null = null;
  try {
    frame = JSON.parse(raw) as SseFrame;
  } catch {
    return null;
  }
  if (!frame || typeof frame.type !== "string") return null;
  applySseFrame(frame, handlers);
  return frame;
}
