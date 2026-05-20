"use client";

/**
 * branching-store — transient session state for Branching page.
 *
 * Holds per-session ephemeral data not owned by TanStack Query:
 *   - `streamingText` — accumulated SSE chunks during /choose/stream
 *   - `streaming` — true while a choose/stream is in flight
 *   - `lastError` — last error message for inline display
 *   - `selectedNodeId` — UI focus (also mirrored in nuqs ?node=)
 *
 * Cleared automatically when `sessionId` changes via `setSession(id)`.
 */

import { create } from "zustand";

export interface BranchingState {
  sessionId: string | null;
  streaming: boolean;
  streamingText: string;
  selectedNodeId: string | null;
  lastError: string | null;

  setSession(id: string | null): void;
  setSelected(id: string | null): void;
  startStream(): void;
  appendStream(chunk: string): void;
  endStream(): void;
  setError(msg: string | null): void;
  reset(): void;
}

export const useBranchingStore = create<BranchingState>((set, get) => ({
  sessionId: null,
  streaming: false,
  streamingText: "",
  selectedNodeId: null,
  lastError: null,

  setSession(id) {
    if (get().sessionId === id) return;
    set({
      sessionId: id,
      streaming: false,
      streamingText: "",
      selectedNodeId: null,
      lastError: null,
    });
  },
  setSelected(id) {
    set({ selectedNodeId: id });
  },
  startStream() {
    set({ streaming: true, streamingText: "", lastError: null });
  },
  appendStream(chunk) {
    set((s) => ({ streamingText: s.streamingText + chunk }));
  },
  endStream() {
    set({ streaming: false });
  },
  setError(msg) {
    set({ lastError: msg, streaming: false });
  },
  reset() {
    set({
      sessionId: null,
      streaming: false,
      streamingText: "",
      selectedNodeId: null,
      lastError: null,
    });
  },
}));
