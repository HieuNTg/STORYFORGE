"use client";

/**
 * useBranchSession — composes branching queries + mutations + SSE choose stream.
 *
 * Returns a single facade so the page component can `const s = useBranchSession(id)`
 * and not juggle 8 separate hook calls. Internally it:
 *   - subscribes to current/tree/layout/analytics/bookmarks queries
 *   - exposes back/undo/redo/goto/addBookmark/deleteBookmark/gotoBookmark mutations
 *   - exposes `choose(idx)` (POST + invalidate) and `chooseStream(idx)` (SSE)
 *
 * Streaming path uses `usePostStream` on `/choose/stream`. Each `data:` frame is
 * parsed as JSON `{ type: 'chunk' | 'complete' | 'error', ... }`. Chunks append
 * to `branching-store.streamingText`. On `complete`, we invalidate the session.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { EventSourceMessage } from "@microsoft/fetch-event-source";
import { usePostStream } from "@/lib/sse/usePostStream";
import { useBranchingStore } from "@/stores/branching-store";
import {
  useBranchCurrent,
  useBranchTree,
  useBranchLayout,
  useBranchAnalytics,
  useBranchBookmarks,
  useBranchUndoRedoStatus,
  useChoose,
  useBack,
  useUndo,
  useRedo,
  useGotoNode,
  useAddBookmark,
  useDeleteBookmark,
  useGotoBookmark,
  useInvalidateBranchSession,
} from "@/lib/api/branching";

export function useBranchSession(sessionId: string | null) {
  const current = useBranchCurrent(sessionId);
  const tree = useBranchTree(sessionId);
  const layout = useBranchLayout(sessionId);
  const analytics = useBranchAnalytics(sessionId);
  const bookmarks = useBranchBookmarks(sessionId);
  const undoRedo = useBranchUndoRedoStatus(sessionId);

  const chooseMut = useChoose(sessionId);
  const backMut = useBack(sessionId);
  const undoMut = useUndo(sessionId);
  const redoMut = useRedo(sessionId);
  const gotoMut = useGotoNode(sessionId);
  const addBookmarkMut = useAddBookmark(sessionId);
  const delBookmarkMut = useDeleteBookmark(sessionId);
  const gotoBookmarkMut = useGotoBookmark(sessionId);
  const invalidate = useInvalidateBranchSession(sessionId);

  const setSession = useBranchingStore((s) => s.setSession);
  const startStream = useBranchingStore((s) => s.startStream);
  const appendStream = useBranchingStore((s) => s.appendStream);
  const endStream = useBranchingStore((s) => s.endStream);
  const setError = useBranchingStore((s) => s.setError);

  useEffect(() => {
    setSession(sessionId);
  }, [sessionId, setSession]);

  // ---- choose/stream wiring -----------------------------------------------
  // We only mount usePostStream when streamBody is non-null; clearing it on
  // completion aborts the in-flight fetch.
  const [streamBody, setStreamBody] = useState<Record<string, unknown> | null>(null);
  const lastChoiceRef = useRef<number | null>(null);

  const onMessage = useCallback(
    (ev: EventSourceMessage) => {
      if (!ev.data) return;
      let parsed: { type?: string; text?: string; node?: unknown; message?: string } | null = null;
      try {
        parsed = JSON.parse(ev.data);
      } catch {
        // Not JSON — treat raw payload as chunk.
        appendStream(ev.data);
        return;
      }
      if (!parsed) return;
      if (parsed.type === "chunk" && typeof parsed.text === "string") {
        appendStream(parsed.text);
      } else if (parsed.type === "complete") {
        endStream();
        setStreamBody(null);
        invalidate();
      } else if (parsed.type === "error") {
        setError(parsed.message ?? "stream_error");
        setStreamBody(null);
      }
    },
    [appendStream, endStream, invalidate, setError]
  );

  const onError = useCallback(
    (err: unknown) => {
      const msg = err instanceof Error ? err.message : "stream_error";
      setError(msg);
      setStreamBody(null);
    },
    [setError]
  );

  const onOpen = useCallback(() => {
    startStream();
  }, [startStream]);

  const streamUrl = useMemo(
    () => (sessionId && streamBody ? `/api/branch/${encodeURIComponent(sessionId)}/choose/stream` : null),
    [sessionId, streamBody]
  );

  usePostStream({
    url: streamUrl,
    body: streamBody,
    onMessage,
    onError,
    onOpen,
  });

  const chooseStream = useCallback(
    (choiceIndex: number) => {
      if (!sessionId) return;
      lastChoiceRef.current = choiceIndex;
      // New object reference forces the effect in usePostStream to remount.
      setStreamBody({ choice_index: choiceIndex });
    },
    [sessionId]
  );

  return {
    sessionId,
    current,
    tree,
    layout,
    analytics,
    bookmarks,
    undoRedo,
    choose: chooseMut,
    chooseStream,
    back: backMut,
    undo: undoMut,
    redo: redoMut,
    gotoNode: gotoMut,
    addBookmark: addBookmarkMut,
    deleteBookmark: delBookmarkMut,
    gotoBookmark: gotoBookmarkMut,
    invalidate,
  };
}
